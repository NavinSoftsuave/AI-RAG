"""Validate the LLM judge against blind human labels, and measure agreement.

Runs the judge (a given version) over the same 25 answers that were hand-labeled
in labels_25.json, then reports agreement as a percentage plus the specific
disagreements. Judge calls are cached, so re-runs are free.

Run:  ./venv/bin/python -m eval.validate_judge v1
      ./venv/bin/python -m eval.validate_judge v2
"""

import json
import sys
from pathlib import Path

from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.llm import QuotaExceeded
from rag.loaders import load_file
from rag.store import VectorStore

from .judge import judge

ROOT = Path(__file__).resolve().parent.parent
LABELS_PATH = ROOT / "labels_25.json"
DOCS_DIR = ROOT / "docs"
LEGAL_DOCS = [
    "sample_service_agreement.pdf", "sample_amendment.txt", "mutual_nda.txt",
    "employment_agreement.txt", "commercial_lease.txt",
]
MODE = "hybrid"
TOP_K = 4


def ingest(store: VectorStore) -> None:
    store.reset()
    for name in LEGAL_DOCS:
        store.add_chunks(chunk_text(load_file(DOCS_DIR / name), source=name))


def app_answer(store: VectorStore, question: str):
    """Reproduce the app's answer + the exact context it was judged on."""
    hits = store.search(question, top_k=TOP_K, mode=MODE)
    answer = build_answer(question, hits)
    context = "\n\n".join(h["text"] for h in hits)
    return answer.text, context


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]

    store = VectorStore()
    ingest(store)

    agree = 0
    disagreements = []
    for row in labels:
        # Regression id 25 replays the T2 question verbatim.
        question = row["question"].split(" [regression")[0]
        answer_text, context = app_answer(store, question)
        try:
            verdict = judge(question, context, answer_text, version=version)
        except QuotaExceeded:
            print(f"Quota exhausted at id {row['id']} — cached verdicts kept; "
                  f"re-run after reset to finish.")
            sys.exit(1)

        human = row["label"]
        model = "CORRECT" if verdict.correct else "INCORRECT"
        if human == model:
            agree += 1
        else:
            disagreements.append((row["id"], question, human, model, verdict.reason))

    n = len(labels)
    pct = agree / n * 100
    print("=" * 72)
    print(f"JUDGE {version} vs blind labels — agreement {agree}/{n} = {pct:.0f}%")
    print("=" * 72)
    if disagreements:
        print("Disagreements (id | human -> model | judge reason):")
        for cid, q, human, model, reason in disagreements:
            print(f"  [{cid}] {human} -> {model}  {q[:48]}")
            print(f"        judge: {reason[:80]}")
    else:
        print("No disagreements.")


if __name__ == "__main__":
    main()
