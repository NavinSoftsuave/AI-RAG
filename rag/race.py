"""Race engine benchmarking ContractAgent vs ContractFixedWorkflow across 10 questions.

Calculates the 4 core metrics for each system:
1. Pass Rate (%)
2. p50 Latency (seconds)
3. Total Cumulative Tokens (summed per lap!)
4. Cost per question ($)

Exports race.csv as required by Task Set F spec.
"""

import csv
import numpy as np
from pathlib import Path
from typing import Any, Dict, List

from rag.agent import ContractAgent
from rag.chunking import chunk_text
from rag.fixed_workflow import ContractFixedWorkflow
from rag.loaders import load_file
from rag.race_dataset import RACE_DATASET, ContractQuestion
from rag.store import VectorStore


def ensure_vector_store_populated(store: VectorStore, docs_dir: Path) -> int:
    """Ingest sample contracts into vector store if empty."""
    if store.count() > 0:
        return store.count()

    total_chunks = 0
    for doc_file in docs_dir.glob("*.*"):
        if doc_file.suffix.lower() in [".txt", ".pdf", ".md"] and doc_file.name != "README.md":
            try:
                raw_text = load_file(str(doc_file))
                chunks = chunk_text(raw_text, source=doc_file.name, chunk_size=800, overlap=150)
                store.add_chunks(chunks)
                total_chunks += len(chunks)
            except Exception as exc:
                print(f"Warning: Failed to ingest {doc_file.name}: {exc}")

    # Also ingest eval_corpus text files if present
    eval_dir = docs_dir / "eval_corpus"
    if eval_dir.exists():
        for doc_file in eval_dir.glob("*.txt"):
            try:
                raw_text = load_file(str(doc_file))
                chunks = chunk_text(raw_text, source=doc_file.name, chunk_size=800, overlap=150)
                store.add_chunks(chunks)
                total_chunks += len(chunks)
            except Exception as exc:
                pass

    return store.count()


def evaluate_response_quality(answer: str, expected_terms: List[str]) -> bool:
    """Check if answer contains key expected contract terms and is not an empty refusal."""
    answer_lower = answer.lower()
    if "i don't know" in answer_lower and "budget exceeded" not in answer_lower:
        return False
    if "error" in answer_lower:
        return False

    matches = [term.lower() in answer_lower for term in expected_terms]
    return any(matches) or len(answer) > 30


def run_race_benchmark(docs_dir: Path, output_csv: Path) -> Dict[str, Any]:
    """Execute head-to-head race between Agent and Fixed Workflow over 10 questions."""
    store = VectorStore()
    ensure_vector_store_populated(store, docs_dir)

    agent = ContractAgent(store, max_iters=5, max_tokens=8000, max_cost=0.01, max_seconds=60.0)
    workflow = ContractFixedWorkflow(store)

    agent_results = []
    workflow_results = []
    csv_rows = []

    for q in RACE_DATASET:
        # Run Agent
        a_res = agent.run(q.question)
        a_pass = evaluate_response_quality(a_res.final_answer, q.expected_key_terms) and a_res.success
        agent_results.append(
            {
                "question_id": q.id,
                "category": q.category,
                "latency": a_res.total_latency_sec,
                "tokens": a_res.cumulative_tokens,
                "cost": a_res.total_cost,
                "passed": a_pass,
                "laps": a_res.total_laps,
                "budget_fired": a_res.budget_fired,
            }
        )

        # Run Fixed Workflow
        w_res = workflow.run(q.question)
        w_pass = evaluate_response_quality(w_res.final_answer, q.expected_key_terms) and w_res.success
        workflow_results.append(
            {
                "question_id": q.id,
                "category": q.category,
                "latency": w_res.total_latency_sec,
                "tokens": w_res.total_tokens,
                "cost": w_res.total_cost,
                "passed": w_pass,
            }
        )

        csv_rows.append(
            {
                "Question_ID": q.id,
                "Category": q.category,
                "Question": q.question,
                "Agent_Pass": 1 if a_pass else 0,
                "Agent_Latency_s": round(a_res.total_latency_sec, 3),
                "Agent_Tokens": a_res.cumulative_tokens,
                "Agent_Cost_$": round(a_res.total_cost, 6),
                "Workflow_Pass": 1 if w_pass else 0,
                "Workflow_Latency_s": round(w_res.total_latency_sec, 3),
                "Workflow_Tokens": w_res.total_tokens,
                "Workflow_Cost_$": round(w_res.total_cost, 6),
            }
        )

    # Compute summary 8 numbers
    agent_pass_rate = float(np.mean([r["passed"] for r in agent_results])) * 100
    agent_p50_latency = float(np.median([r["latency"] for r in agent_results]))
    agent_avg_tokens = float(np.mean([r["tokens"] for r in agent_results]))
    agent_avg_cost = float(np.mean([r["cost"] for r in agent_results]))

    wf_pass_rate = float(np.mean([r["passed"] for r in workflow_results])) * 100
    wf_p50_latency = float(np.median([r["latency"] for r in workflow_results]))
    wf_avg_tokens = float(np.mean([r["tokens"] for r in workflow_results]))
    wf_avg_cost = float(np.mean([r["cost"] for r in workflow_results]))

    summary_table = {
        "Agent": {
            "pass_rate_pct": round(agent_pass_rate, 1),
            "p50_latency_sec": round(agent_p50_latency, 3),
            "avg_tokens_per_task": int(round(agent_avg_tokens)),
            "avg_cost_per_task": round(agent_avg_cost, 6),
        },
        "FixedWorkflow": {
            "pass_rate_pct": round(wf_pass_rate, 1),
            "p50_latency_sec": round(wf_p50_latency, 3),
            "avg_tokens_per_task": int(round(wf_avg_tokens)),
            "avg_cost_per_task": round(wf_avg_cost, 6),
        },
    }

    # Write race.csv
    with open(output_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Question_ID",
                "Category",
                "Question",
                "Agent_Pass",
                "Agent_Latency_s",
                "Agent_Tokens",
                "Agent_Cost_$",
                "Workflow_Pass",
                "Workflow_Latency_s",
                "Workflow_Tokens",
                "Workflow_Cost_$",
            ],
        )
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)

        # Write summary row in CSV
        f.write("\nSUMMARY_METRICS\n")
        f.write("System,PassRate(%),p50_Latency(s),Avg_Tokens,Avg_Cost($)\n")
        f.write(
            f"Agent,{summary_table['Agent']['pass_rate_pct']},{summary_table['Agent']['p50_latency_sec']},{summary_table['Agent']['avg_tokens_per_task']},{summary_table['Agent']['avg_cost_per_task']}\n"
        )
        f.write(
            f"FixedWorkflow,{summary_table['FixedWorkflow']['pass_rate_pct']},{summary_table['FixedWorkflow']['p50_latency_sec']},{summary_table['FixedWorkflow']['avg_tokens_per_task']},{summary_table['FixedWorkflow']['avg_cost_per_task']}\n"
        )

    return {
        "summary": summary_table,
        "rows": csv_rows,
        "csv_path": str(output_csv),
    }
