"""Vector store: embed chunks with a local BGE model and retrieve them with
Chroma (semantic) and BM25 (keyword), optionally fused via Reciprocal Rank
Fusion.
"""

import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from .chunking import Chunk

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DB_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")

# RRF constant from the original paper; damps the weight of top ranks.
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    """Lowercase tokens for BM25, preserving codes like ``err-4032`` and
    ``admin@123`` as whole terms."""
    return re.findall(r"[a-z0-9][a-z0-9@._-]*", text.lower())


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
        # BM25 index, built lazily on first hybrid search and invalidated on ingest.
        self._bm25 = None
        self._bm25_ids: list[str] = []

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
        self._bm25 = None  # invalidate keyword index

    def search(
        self, question: str, top_k: int = 4, mode: str = "semantic"
    ) -> list[dict]:
        """Return the top_k chunks for a question.

        ``mode="semantic"`` ranks by embedding similarity; ``mode="hybrid"``
        fuses semantic and BM25 keyword rankings with RRF to also catch exact
        terms (codes, passwords, IDs) that embeddings blur.

        Each hit has ``text``, ``source``, ``chunk_index``, ``score`` (cosine in
        semantic mode, RRF in hybrid), and ``cosine`` (similarity in [0, 1] for
        both modes).
        """
        if mode == "semantic":
            return self._semantic_search(question, top_k)
        if mode == "hybrid":
            return self._hybrid_search(question, top_k)
        raise ValueError(f"unknown search mode: {mode!r}")

    def _semantic_search(self, question: str, top_k: int) -> list[dict]:
        result = self._collection.query(
            query_texts=[question],
            n_results=top_k,
        )
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        distances = result["distances"][0]

        hits = []
        for text, meta, distance in zip(docs, metas, distances):
            similarity = 1.0 - distance  # Chroma returns cosine DISTANCE.
            hits.append(
                {
                    "text": text,
                    "source": meta["source"],
                    "chunk_index": meta["chunk_index"],
                    "score": similarity,
                    # Same [0, 1] scale in both modes so answer.py can threshold
                    # consistently (the hybrid `score` is an RRF value, not a
                    # similarity).
                    "cosine": similarity,
                }
            )
        return hits

    def _ensure_bm25(self) -> None:
        """Build (or rebuild) the BM25 keyword index over all stored chunks."""
        if self._bm25 is not None:
            return
        data = self._collection.get(include=["documents"])
        self._bm25_ids = data["ids"]
        self._bm25_docs = data["documents"]
        tokenized = [_tokenize(doc) for doc in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def _hybrid_search(self, question: str, top_k: int) -> list[dict]:
        """Fuse semantic and BM25 rankings with RRF.

        Each list contributes ``1 / (RRF_K + rank)`` per item, so a chunk ranked
        well in either list rises to the top without the two score scales needing
        to be comparable.
        """
        self._ensure_bm25()

        # Retrieve a wide candidate pool so fusion has room to reorder.
        pool = max(top_k * 5, 20)

        sem = self._collection.query(query_texts=[question], n_results=pool)
        sem_ids = sem["ids"][0]
        # Retain cosine similarity to attach a comparable relevance score below.
        sem_cosine = {
            cid: 1.0 - dist
            for cid, dist in zip(sem_ids, sem["distances"][0])
        }

        kw_ids: list[str] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(_tokenize(question))
            order = sorted(
                range(len(scores)), key=lambda i: scores[i], reverse=True
            )
            kw_ids = [self._bm25_ids[i] for i in order[:pool] if scores[i] > 0]

        fused: dict[str, float] = {}
        for ranked in (sem_ids, kw_ids):
            for rank, cid in enumerate(ranked, start=1):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)

        top_ids = sorted(fused, key=lambda c: fused[c], reverse=True)[:top_k]

        got = self._collection.get(ids=top_ids, include=["documents", "metadatas"])
        by_id = {
            cid: (doc, meta)
            for cid, doc, meta in zip(
                got["ids"], got["documents"], got["metadatas"]
            )
        }
        hits = []
        for cid in top_ids:
            doc, meta = by_id[cid]
            hits.append(
                {
                    "text": doc,
                    "source": meta["source"],
                    "chunk_index": meta["chunk_index"],
                    "score": fused[cid],  # RRF score (higher = better)
                    # Keyword-only winners default to 0.0; the LLM still guards
                    # grounding, so a strong exact-term match isn't dropped here.
                    "cosine": sem_cosine.get(cid, 0.0),
                }
            )
        return hits

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        """Drop the collection and start fresh."""
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            embedding_function=self._embedder,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25 = None
