"""Ask questions from the terminal, interactively.

    ./venv/bin/python ask_cli.py

Type a question and press Enter. Type 'quit' to exit. Assumes you've already
ingested documents (via the app, ingest_cli.py, or test_rag.py).
"""

from rag.answer import build_answer
from rag.store import VectorStore


def main() -> None:
    store = VectorStore()
    if store.count() == 0:
        print("No documents ingested yet. Run:")
        print("  ./venv/bin/python ingest_cli.py docs/ --reset")
        return

    print(f"Ready. {store.count()} chunks in the store. Type a question "
          "('quit' to exit).\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in {"quit", "exit"}:
            break

        hits = store.search(question, top_k=4)
        answer = build_answer(question, hits)
        print(f"\nAI: {answer.text}\n")
        print(f"    (top similarity: {hits[0]['score']:.3f})\n")


if __name__ == "__main__":
    main()
