"""Retrieval metrics — the numbers that prove a change helped.

All three answer "did the right document show up, and how high?":

  hit_rate@k  — fraction of questions where the correct document appears
                ANYWHERE in the top-k. This is the headline number the task asks
                for (hit-rate@3). Binary per question: found it or not.

  recall@k    — here each question has exactly one correct document, so recall@k
                equals hit_rate@k. Kept as a separate name because the concept
                generalises when a question has several correct documents.

  mrr         — Mean Reciprocal Rank. Rewards putting the right doc HIGHER, not
                just somewhere in the top-k. Rank 1 -> 1.0, rank 2 -> 0.5,
                rank 3 -> 0.33. Catches improvements that hit-rate can't see
                (e.g. reranking that lifts the right doc from #3 to #1).

A "ranking" here is the ordered list of source filenames retrieved for a
question, best first.
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


def aggregate(per_question: list[dict], k: int) -> dict:
    """Roll per-question results into hit-rate@k, recall@k and MRR."""
    n = len(per_question)
    if n == 0:
        return {"n": 0, "hit_rate": 0.0, "recall": 0.0, "mrr": 0.0}

    hits = sum(r["hit_at_k"] for r in per_question)
    mrr = sum(r["reciprocal_rank"] for r in per_question) / n
    return {
        "n": n,
        "k": k,
        "hit_rate": hits / n,   # hit-rate@k
        "recall": hits / n,     # == hit-rate@k for single-gold questions
        "mrr": mrr,
    }
