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

import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

from .chunking import Chunk

# BGE-small: a compact, strong embedding model (top of the MTEB leaderboard for
# its size). Downloaded once on first run, then cached locally.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

DB_DIR = str(Path(__file__).resolve().parent.parent / "chroma_db")

# Reciprocal Rank Fusion constant. Standard default from the RRF paper; damps the
# influence of very high ranks so no single list dominates the fused order.
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens for BM25.

    Keeps intra-token punctuation like the hyphen in "err-4032" and the "@" in
    "admin@123" so exact codes/passwords stay searchable as whole terms.
    """
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
        # Lazily-built BM25 keyword index over the same chunks. Built on first
        # hybrid search and cached; invalidated whenever chunks change.
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
        self._bm25 = None  # keyword index is now stale; rebuild on next use.

    def search(
        self, question: str, top_k: int = 4, mode: str = "semantic"
    ) -> list[dict]:
        """Return the top_k chunks for a question.

        mode="semantic" (default): search by MEANING only — the original
            behaviour. This is the BEFORE baseline for the week's measurement.

        mode="hybrid": fuse semantic search with BM25 KEYWORD search using
            Reciprocal Rank Fusion. Catches exact terms (codes like ERR-4032,
            passwords like admin@123, IDs) that meaning-based search blurs, while
            keeping semantic's strength on paraphrased questions. This is the
            AFTER — the single change under test.

        Each result includes its text, source document, chunk index, and a
        score. For hybrid the score is the fused RRF score (higher = better);
        for semantic it is cosine similarity in [0, 1].
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

    def _ensure_bm25(self) -> None:
        """Build (or rebuild) the BM25 keyword index over all stored chunks."""
        if self._bm25 is not None:
            return
        data = self._collection.get(include=["documents"])
        self._bm25_ids = data["ids"]
        self._bm25_docs = data["documents"]
        tokenized = [_tokenize(doc) for doc in self._bm25_docs]
        # BM25Okapi needs at least one document; guard the empty-store case.
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def _hybrid_search(self, question: str, top_k: int) -> list[dict]:
        """Semantic + BM25, fused with Reciprocal Rank Fusion (RRF).

        RRF combines two ranked lists without needing their scores to be on the
        same scale: each list contributes 1 / (RRF_K + rank) to every item it
        ranks. A chunk that ranks well in EITHER list — or modestly in both —
        floats to the top. That is what lets a keyword-only match (exact code)
        and a meaning-only match (paraphrase) both survive fusion.
        """
        self._ensure_bm25()

        # Pull a wide candidate pool from each retriever so fusion has room to
        # work — not just the final top_k from either one alone.
        pool = max(top_k * 5, 20)

        # --- Semantic ranking (chunk id -> rank) ---
        sem = self._collection.query(query_texts=[question], n_results=pool)
        sem_ids = sem["ids"][0]

        # --- Keyword ranking (chunk id -> rank) ---
        kw_ids: list[str] = []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(_tokenize(question))
            order = sorted(
                range(len(scores)), key=lambda i: scores[i], reverse=True
            )
            kw_ids = [self._bm25_ids[i] for i in order[:pool] if scores[i] > 0]

        # --- Reciprocal Rank Fusion ---
        fused: dict[str, float] = {}
        for ranked in (sem_ids, kw_ids):
            for rank, cid in enumerate(ranked, start=1):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)

        top_ids = sorted(fused, key=lambda c: fused[c], reverse=True)[:top_k]

        # Hydrate the winning ids back into full hit dicts.
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
                    "score": fused[cid],  # fused RRF score (higher = better)
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
        self._bm25 = None
