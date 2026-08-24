"""Retrieval metrics over a ranking (ordered source filenames, best first).

  hit_rate@k  — is the correct document anywhere in the top-k? (headline metric)
  mrr         — Mean Reciprocal Rank; rewards ranking the right document higher.
"""


def rank_of_gold(ranked_sources: list[str], gold_source: str) -> int | None:
    """1-based position of the gold document, or None if absent."""
    for i, source in enumerate(ranked_sources, start=1):
        if source == gold_source:
            return i
    return None


def hit_rate_at_k(ranked_sources: list[str], gold_source: str, k: int) -> int:
    """1 if the gold document is in the top-k, else 0."""
    rank = rank_of_gold(ranked_sources[:k], gold_source)
    return 1 if rank is not None else 0


def reciprocal_rank(ranked_sources: list[str], gold_source: str) -> float:
    rank = rank_of_gold(ranked_sources, gold_source)
    return 1.0 / rank if rank is not None else 0.0
