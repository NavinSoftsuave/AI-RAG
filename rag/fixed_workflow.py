"""Fixed Workflow implementation for contract analysis.

Requirement 2:
- Hard-coded 3-step sequence (no loop, no agent decision making).
- Same tools (`search_contract`, `get_clause`, `get_definitions`), same model (gemini-3.6-flash), same output contract.
- Deterministic, fast, single-pass pipeline.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from rag.llm import generate
from rag.store import VectorStore
from rag.tools import (
    ClauseType,
    ContractVersion,
    get_clause,
    get_definitions,
    search_contract,
)

PRICE_PER_INPUT_TOKEN = 0.00000015
PRICE_PER_OUTPUT_TOKEN = 0.00000060


@dataclass
class WorkflowRunResult:
    question: str
    final_answer: str
    step_logs: List[str]
    total_tokens: int
    total_cost: float
    total_latency_sec: float
    success: bool


class ContractFixedWorkflow:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def run(self, question: str) -> WorkflowRunResult:
        start_time = time.time()
        step_logs: List[str] = []

        # --- STEP 1: Search contract vector store for relevant chunks ---
        hits = search_contract(question, self.vector_store, top_k=4)
        if hits:
            retrieved_text = "\n\n".join(
                [f"[{i}] Source: {h['source']}\n{h['text']}" for i, h in enumerate(hits, 1)]
            )
        else:
            retrieved_text = "No direct vector hits found."
        step_logs.append(f"Step 1 (Search): Retrieved {len(hits)} chunks.")

        # --- STEP 2: Pre-fetch definitions and clause lookup for context augmentation ---
        definitions_info = get_definitions("Effective Date", ContractVersion.ORIGINAL)
        clause_info = get_clause(ClauseType.TERMINATION, self.vector_store)

        def_str = f"Defined Term ({definitions_info['term']}): {definitions_info['definition']}"
        clause_str = (
            "\n".join([c["text"] for c in clause_info[:2]]) if clause_info else "No termination clause retrieved."
        )

        step_logs.append("Step 2 (Definitions & Clause Extract): Resolved standard definitions and clauses.")

        # --- STEP 3: Final Synthesis Generation (Single Model Call) ---
        prompt = f"""
You are a contract document analysis assistant operating in a fixed workflow.

CONTRACT CONTEXT (Vector Search):
{retrieved_text}

STANDARD CLAUSES & DEFINITIONS:
{def_str}
{clause_str}

USER QUESTION:
{question}

INSTRUCTIONS:
1. Provide a concise, clear, and accurate answer based on the contract context and definitions above.
2. State any effective date, notice period deadline, or relevant legal terms directly.
3. If the answer is not present, state 'I don't know.'

ANSWER:
"""
        prompt_tokens = self._estimate_tokens(prompt)
        try:
            answer = generate(prompt)
            success = True
        except Exception as exc:
            answer = f"Error in fixed workflow generation: {exc}"
            success = False

        completion_tokens = self._estimate_tokens(answer)
        total_tokens = prompt_tokens + completion_tokens
        total_cost = (prompt_tokens * PRICE_PER_INPUT_TOKEN) + (completion_tokens * PRICE_PER_OUTPUT_TOKEN)
        total_latency = time.time() - start_time

        step_logs.append(f"Step 3 (Synthesis): Completed final answer generation in {total_latency:.2f}s.")

        return WorkflowRunResult(
            question=question,
            final_answer=answer,
            step_logs=step_logs,
            total_tokens=total_tokens,
            total_cost=total_cost,
            total_latency_sec=total_latency,
            success=success,
        )
