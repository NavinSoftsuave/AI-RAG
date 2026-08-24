"""Generate complete traces for error analysis (Week 5 · M3).

Ingests the legal-contracts corpus, runs every question in `questions_legal.py`
through the full pipeline WITH live generation, and writes one complete trace per
question to traces/legal_traces.jsonl.

Run:  ./venv/bin/python -m eval.run_traces

Requires GEMINI_API_KEY in .env — these are real answers, which is the point.
"""

import sys
import time
from pathlib import Path

from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.llm import QuotaExceeded
from rag.loaders import load_file
from rag.store import VectorStore

from .questions_legal import QUESTIONS
from .traces import TRACE_DIR, RetrievedChunk, Trace, write_traces

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
# The legal-contracts corpus (skip the eval_corpus HR/IT distractors).
LEGAL_DOCS = [
    "sample_service_agreement.pdf",
    "sample_amendment.txt",
    "mutual_nda.txt",
    "employment_agreement.txt",
    "commercial_lease.txt",
]
MODE = "hybrid"   # the app's default retrieval mode
TOP_K = 4
OUT_PATH = TRACE_DIR / "legal_traces.jsonl"

# Pace calls under the free-tier per-minute limit, and retry a transient 429.
REQUEST_DELAY_S = 4.0
MAX_RETRIES = 2
RETRY_WAIT_S = 50.0


def answer_with_retry(question: str, hits: list[dict]):
    """Call build_answer, retrying a transient (per-minute) quota 429. A quota
    error that survives the retries is treated as the daily cap and re-raised."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return build_answer(question, hits)
        except QuotaExceeded:
            if attempt == MAX_RETRIES:
                raise
            print(f"    429 quota — waiting {RETRY_WAIT_S:.0f}s and retrying…")
            time.sleep(RETRY_WAIT_S)


def ingest(store: VectorStore) -> None:
    store.reset()
    total = 0
    for name in LEGAL_DOCS:
        path = DOCS_DIR / name
        chunks = chunk_text(load_file(path), source=name)
        store.add_chunks(chunks)
        total += len(chunks)
    print(f"Ingested {len(LEGAL_DOCS)} legal docs -> {total} chunks.\n")


def main() -> None:
    store = VectorStore()
    ingest(store)

    traces: list[Trace] = []
    for i, q in enumerate(QUESTIONS, start=1):
        hits = store.search(q.text, top_k=TOP_K, mode=MODE)
        try:
            answer = answer_with_retry(q.text, hits)
        except QuotaExceeded:
            print(
                f"\nDaily Gemini quota exhausted at question {i}. "
                f"No junk traces written; re-run after the quota resets "
                f"(Pacific midnight)."
            )
            sys.exit(1)

        retrieved = [
            RetrievedChunk(
                rank=r,
                source=h["source"],
                chunk_index=h["chunk_index"],
                score=round(float(h["score"]), 4),
                text=h["text"],
            )
            for r, h in enumerate(hits, start=1)
        ]
        traces.append(
            Trace(
                id=i,
                question=q.text,
                kind=q.kind,
                expected=q.expected,
                mode=MODE,
                retrieved=retrieved,
                answer=answer.text,
                answered=answer.answered,
                top_score=round(float(hits[0]["score"]), 4) if hits else 0.0,
            )
        )
        status = "ANSWERED" if answer.answered else "REFUSED"
        print(f"[{i:2}/{len(QUESTIONS)}] {status:8} | {q.text[:60]}")
        if i < len(QUESTIONS):
            time.sleep(REQUEST_DELAY_S)

    write_traces(traces, OUT_PATH)
    print(f"\nWrote {len(traces)} traces to {OUT_PATH}")


if __name__ == "__main__":
    main()
