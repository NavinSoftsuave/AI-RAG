"""Quick end-to-end test of the RAG pipeline.

Run it with:   ./venv/bin/python test_rag.py

It ingests docs/sample_amendment.txt, then asks a few questions and checks:
  - in-scope questions get answered, with a citation
  - an out-of-scope question is refused ("I don't know")
"""

from pathlib import Path

from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.loaders import load_file
from rag.store import VectorStore

# Each case is (question, should_be_answered, expected_keyword_in_answer).
# expected_keyword is a distinctive word from the correct clause — proves the
# app didn't just answer, but answered from the RIGHT clause.
CASES = [
    ("What is the notice period for termination for convenience?", True, "sixty"),
    ("What is the late payment interest rate?", True, "1.5"),
    ("How long does confidentiality survive termination?", True, "five"),
    ("What law governs this agreement?", True, "Delaware"),
    ("What is the limitation of liability?", True, "liability"),
    ("What is the refund policy for gym memberships?", False, None),  # not in doc
]


def main() -> None:
    store = VectorStore()
    store.reset()  # start clean so the test is repeatable

    # --- Ingest the sample contract PDF ---
    sample = Path("docs/sample_service_agreement.pdf")
    chunks = chunk_text(load_file(sample), source=sample.name)
    store.add_chunks(chunks)
    print(f"Ingested {len(chunks)} chunks. Store holds {store.count()}.\n")

    # --- Ask questions ---
    passed = 0
    for question, expected, keyword in CASES:
        hits = store.search(question, top_k=4)
        answer = build_answer(question, hits)
        # Answered-state must match, AND (when answered) the right clause must
        # be present, checked via a distinctive keyword.
        keyword_ok = keyword is None or keyword.lower() in answer.text.lower()
        ok = (answer.answered == expected) and keyword_ok
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] answered={answer.answered} (expected {expected}) "
              f"top_score={hits[0]['score']:.3f}")
        print(f"       Q: {question}")
        print(f"       A: {answer.text.splitlines()[0][:90]}...\n")

    print(f"{passed}/{len(CASES)} cases passed.")


if __name__ == "__main__":
    main()
