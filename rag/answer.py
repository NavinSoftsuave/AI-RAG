from dataclasses import dataclass

from .llm import generate_answer

MIN_SIMILARITY = 0.55
MAX_CONTEXT_CHUNKS = 3


@dataclass
class Answer:
    text: str
    sources: list[dict]
    answered: bool


def _refusal(reason: str) -> Answer:
    return Answer(text=f"I don't know — {reason}", sources=[], answered=False)


def _build_context(hits: list[dict]) -> str:
    parts = [
        f"[DOCUMENT {i}]\n"
        f"Source document: {hit['source']}\n"
        f"Chunk: {hit['chunk_index']}\n"
        f"Similarity: {hit['score']:.3f}\n\n"
        f"Contract text:\n{hit['text']}"
        for i, hit in enumerate(hits, start=1)
    ]
    return "\n\n".join(parts)


def build_answer(question: str, hits: list[dict]) -> Answer:
    """Generate an answer grounded only in the retrieved chunks, or refuse."""
    if not hits:
        return _refusal("I couldn't find relevant information in the provided documents.")

    # Gate on cosine (same [0, 1] scale in both modes); the hybrid `score` is an
    # RRF value on a different scale and can't be compared to MIN_SIMILARITY.
    relevant = [h for h in hits if h.get("cosine", h["score"]) >= MIN_SIMILARITY]
    if not relevant:
        return _refusal("I couldn't find relevant information in the provided documents.")

    candidates = relevant[:MAX_CONTEXT_CHUNKS]

    try:
        answer_text = generate_answer(
            question=question, context=_build_context(candidates)
        ).strip()
    except Exception as exc:
        return Answer(text=f"Unable to generate an answer: {exc}", sources=[], answered=False)

    if answer_text.lower() == "i don't know.":
        return _refusal(
            "the provided documents do not contain enough information to answer this question."
        )

    citations = "\n".join(
        f"- {hit['source']} (chunk {hit['chunk_index']})" for hit in candidates
    )
    return Answer(
        text=f"{answer_text}\n\nSources:\n{citations}",
        sources=candidates,
        answered=True,
    )
