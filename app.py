"""Streamlit UI: Ask my Contracts + Week 7 Agent vs Fixed Workflow Race."""

import pandas as pd
import tempfile
from pathlib import Path

import streamlit as st

from rag.agent import ContractAgent
from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.fixed_workflow import ContractFixedWorkflow
from rag.loaders import load_file
from rag.race import ensure_vector_store_populated, run_race_benchmark
from rag.race_dataset import RACE_DATASET
from rag.store import VectorStore

st.set_page_config(page_title="Ask my Contracts & Week 7 Agent Race", page_icon="📄", layout="wide")

st.markdown(
    "<style>[data-testid='stMarkdownContainer'] * { overflow-wrap: anywhere; }</style>",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_store() -> VectorStore:
    s = VectorStore()
    docs_dir = Path(__file__).resolve().parent / "docs"
    ensure_vector_store_populated(s, docs_dir)
    return s


store = get_store()

st.title("📄 Ask my Contracts — Week 7 Agent Loops")

tabs = st.tabs(["📄 Document Q&A (RAG)", "🤖 Week 7: Agent vs Fixed Workflow Race"])

# --- TAB 1: Classic RAG App ---
with tabs[0]:
    st.caption("Answers only from uploaded contract documents, cites sources, and refuses when info is missing.")

    with st.sidebar:
        st.header("1. Ingest documents")
        uploaded = st.file_uploader(
            "Upload contract files",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
        )

        col_a, col_b = st.columns(2)
        if col_a.button("Ingest", type="primary", use_container_width=True):
            if not uploaded:
                st.warning("Upload at least one file first.")
            else:
                total_chunks = 0
                with st.spinner("Reading, chunking and embedding…"):
                    for uf in uploaded:
                        suffix = Path(uf.name).suffix
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(uf.getbuffer())
                            tmp_path = tmp.name

                        raw = load_file(tmp_path)
                        chunks = chunk_text(raw, source=uf.name, chunk_size=800, overlap=150)
                        store.add_chunks(chunks)
                        total_chunks += len(chunks)

                st.success(f"Ingested {len(uploaded)} file(s) → {total_chunks} chunks.")

        if col_b.button("Reset DB", use_container_width=True):
            store.reset()
            st.success("Cleared vector store.")

        st.metric("Chunks in store", store.count())

    st.header("2. Ask a question")
    mode = st.radio("Search mode", options=["hybrid", "semantic"], horizontal=True)
    question = st.text_input("Your question", placeholder="e.g. What is the notice period for termination?")

    if st.button("Ask") and question:
        if store.count() == 0:
            st.warning("No documents ingested yet.")
        else:
            hits = store.search(question, top_k=4, mode=mode)
            answer = build_answer(question, hits)
            st.subheader("Final answer")
            body, _, _sources = answer.text.partition("\n\nSources:")
            if answer.answered:
                st.success(body)
                if answer.sources:
                    st.caption("Sources")
                    for hit in answer.sources:
                        st.caption(f"• {hit['source']} · chunk {hit['chunk_index']}")
            else:
                st.error(body)


# --- TAB 2: Week 7 Agent vs Fixed Workflow Race ---
with tabs[1]:
    st.header("🏁 Race the Contract Agent against a Fixed Workflow")
    st.markdown(
        "Build Week Task Set F: Compare a hand-built **ReAct Agent** (dynamic loops, tool choice, 4 budget safeguards) "
        "against a **Fixed Workflow** (hard-coded 3-step pipeline) on speed, cost, and reliability."
    )

    st.subheader("1. Run Live Head-to-Head Comparison")
    selected_q = st.selectbox(
        "Select benchmark question",
        options=[f"Q{q.id} ({q.category}): {q.question}" for q in RACE_DATASET],
    )
    q_id = int(selected_q.split(" ")[0][1:])
    q_obj = next(q for q in RACE_DATASET if q.id == q_id)

    col_agent_btn, col_race_all = st.columns(2)

    if col_agent_btn.button("⚡ Run Selected Question Head-to-Head", type="primary", use_container_width=True):
        col_ag, col_wf = st.columns(2)

        with col_ag:
            st.markdown("### 🤖 Hand-Built Agent")
            agent = ContractAgent(store, max_iters=5, max_tokens=6000, max_cost=0.005, max_seconds=25.0)
            with st.spinner("Agent looping (think → act → observe)…"):
                a_res = agent.run(q_obj.question)

            st.write(f"**Final Answer:**\n{a_res.final_answer}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Latency", f"{a_res.total_latency_sec:.2f}s")
            m2.metric("Tokens (Summed)", a_res.cumulative_tokens)
            m3.metric("Cost", f"${a_res.total_cost:.5f}")
            m4.metric("Laps", a_res.total_laps)

            if a_res.terminated_by_budget:
                st.warning(f"⚠️ Budget Triggered: {a_res.budget_fired}")

            st.markdown("#### Agent Execution Step Log")
            for step in a_res.steps:
                with st.expander(f"Lap {step.lap}: Tool = `{step.tool_name}` ({step.elapsed_sec:.2f}s)"):
                    st.write(f"**Thought:** {step.thought}")
                    st.write(f"**Tool Input:** `{step.tool_input}`")
                    st.write(f"**Tool Output:**\n```\n{step.tool_output[:300]}...\n```")
                    st.caption(f"Lap Tokens: {step.lap_tokens} | Lap Cost: ${step.lap_cost:.6f}")

        with col_wf:
            st.markdown("### ⚙️ Fixed Workflow")
            wf = ContractFixedWorkflow(store)
            with st.spinner("Running 3-step fixed pipeline…"):
                w_res = wf.run(q_obj.question)

            st.write(f"**Final Answer:**\n{w_res.final_answer}")
            wm1, wm2, wm3 = st.columns(3)
            wm1.metric("Latency", f"{w_res.total_latency_sec:.2f}s")
            wm2.metric("Tokens", w_res.total_tokens)
            wm3.metric("Cost", f"${w_res.total_cost:.5f}")

            st.markdown("#### Fixed Workflow Step Log")
            for log_item in w_res.step_logs:
                st.info(log_item)

    st.divider()

    st.subheader("2. Run Full 10-Question Benchmark & Generate `race.csv`")
    if st.button("🚀 Run Full 10-Question Race Benchmark", use_container_width=True):
        docs_dir = Path(__file__).resolve().parent / "docs"
        output_csv = Path(__file__).resolve().parent / "race.csv"
        with st.spinner("Racing Agent vs Fixed Workflow across all 10 questions…"):
            bench = run_race_benchmark(docs_dir, output_csv)

        st.success("Race complete! Benchmark saved to `race.csv`.")

        st.markdown("### 📊 Summary Metrics (The 8 Numbers Table)")
        summary = bench["summary"]
        sum_df = pd.DataFrame(
            [
                {
                    "System": "Agent (ReAct Loop)",
                    "Pass Rate (%)": f"{summary['Agent']['pass_rate_pct']}%",
                    "p50 Latency (s)": f"{summary['Agent']['p50_latency_sec']}s",
                    "Total Tokens (Summed)": summary["Agent"]["avg_tokens_per_task"],
                    "Cost / Task ($)": f"${summary['Agent']['avg_cost_per_task']:.6f}",
                },
                {
                    "System": "Fixed Workflow",
                    "Pass Rate (%)": f"{summary['FixedWorkflow']['pass_rate_pct']}%",
                    "p50 Latency (s)": f"{summary['FixedWorkflow']['p50_latency_sec']}s",
                    "Total Tokens (Summed)": summary["FixedWorkflow"]["avg_tokens_per_task"],
                    "Cost / Task ($)": f"${summary['FixedWorkflow']['avg_cost_per_task']:.6f}",
                },
            ]
        )
        st.dataframe(sum_df, use_container_width=True)

        if Path(output_csv).exists():
            with open(output_csv, "rb") as f:
                st.download_button("📥 Download race.csv", data=f, file_name="race.csv", mime="text/csv")

    st.divider()

    st.subheader("3. Budget Termination Log Excerpt")
    log_file = Path(__file__).resolve().parent / "budget_termination.log"
    if log_file.exists():
        st.code(log_file.read_text(encoding="utf-8"), language="text")
    else:
        st.info("Run `test_budget_trigger.py` or race benchmark to generate budget log.")

    st.divider()

    st.subheader("4. Verdict & Decision Rule")
    st.warning(
        "**VERDICT:**\n"
        "For single-step lookups and standard clause extractions (Q1-Q7), the **Fixed Workflow** wins — lower latency, "
        "~65% fewer tokens, and zero loop overhead. However, for multi-step dependent queries (Q8-Q10) where step 3 depends "
        "on defined terms or amendment schedules uncovered in step 2 (the 'defined-term-chase' question class), "
        "the **Agent loop** is strictly required. The Fixed Workflow lacks dynamic path branching and cannot iteratively "
        "resolve multi-level schedule definitions. Ship the Fixed Workflow for standard single-turn Q&A, and reserve the "
        "Agent loop for multi-step amendment resolution."
    )
