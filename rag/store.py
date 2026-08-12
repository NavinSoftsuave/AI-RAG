"""The vector store: embed chunks and search them by meaning.

An EMBEDDING is a list of numbers (a vector) that captures the meaning of a
piece of text. Two texts about the same idea land close together in this number
space even if they share no keywords. That's the whole trick behind "search by
meaning instead of by keyword".

We use:
  - sentence-transformers (BGE model) to turn text -> vectors, fully locally.
  - Chroma to store those vectors and find the nearest ones to a question.

Chroma uses an HNSW index under the hood, which finds approximate nearest
neighbours fast without comparing against every chunk one by one.
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from .chunking import Chunk

# BGE-small: a compact, strong embedding model (top of the MTEB leaderboard for
# its size). Downloaded once on first run, then cached locally.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

DB_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")


class VectorStore:
    def __init__(self, collection_name: str = "contracts"):
        self._embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        self._client = chromadb.PersistentClient(path=DB_DIR)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedder,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Embed and store chunks. Ids are stable so re-ingesting overwrites."""
        if not chunks:
            return
        ids = [f"{c.source}::{c.chunk_index}" for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {"source": c.source, "chunk_index": c.chunk_index} for c in chunks
        ]
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, question: str, top_k: int = 4) -> list[dict]:
        """Return the top_k chunks most similar to the question.

        Each result includes its text, its source document, and a similarity
        score in [0, 1] (higher = closer) so we can decide whether the match is
        good enough to trust before letting the model answer.
        """
        result = self._collection.query(
            query_texts=[question],
            n_results=top_k,
        )
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        distances = result["distances"][0]

        hits = []
        for text, meta, distance in zip(docs, metas, distances):
            hits.append(
                {
                    "text": text,
                    "source": meta["source"],
                    "chunk_index": meta["chunk_index"],
                    # Chroma returns cosine DISTANCE; similarity = 1 - distance.
                    "score": 1.0 - distance,
                }
            )
        return hits

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        """Drop everything — used when you want to re-ingest from scratch."""
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            embedding_function=self._embedder,
            metadata={"hnsw:space": "cosine"},
        )
