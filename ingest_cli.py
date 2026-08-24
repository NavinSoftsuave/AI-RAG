"""Ingest a folder of documents from the command line.

    python ingest_cli.py docs/ --chunk-size 800 --overlap 150
"""

import argparse
from pathlib import Path

from rag.chunking import chunk_text
from rag.loaders import load_file
from rag.store import VectorStore

SUPPORTED = {".pdf", ".txt", ".md"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the RAG store.")
    parser.add_argument("folder", help="Folder containing documents to ingest.")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=150)
    parser.add_argument("--reset", action="store_true", help="Clear the store first.")
    args = parser.parse_args()

    store = VectorStore()
    if args.reset:
        store.reset()
        print("Cleared existing store.")

    folder = Path(args.folder)
    files = [p for p in folder.rglob("*") if p.suffix.lower() in SUPPORTED
             and p.name != "README.md"]
    if not files:
        print(f"No supported documents found in {folder}/ ({SUPPORTED}).")
        return

    total = 0
    for path in files:
        raw = load_file(path)
        chunks = chunk_text(
            raw, source=path.name,
            chunk_size=args.chunk_size, overlap=args.overlap,
        )
        store.add_chunks(chunks)
        total += len(chunks)
        print(f"  {path.name}: {len(chunks)} chunks")

    print(f"\nIngested {len(files)} file(s) → {total} chunks. "
          f"Store now holds {store.count()} chunks.")


if __name__ == "__main__":
    main()
