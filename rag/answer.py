from dataclasses import dataclass

from .llm import generate_answer


MIN_SIMILARITY = 0.55


@dataclass
class Answer:
    text: str
    sources: list[dict]
    answered: bool


def build_answer(question: str, hits: list[dict]) -> Answer:
    """Generate a grounded answer from retrieved contract chunks."""

    # ---------------------------------------------------------
    # STEP 1: No retrieval results
    # ---------------------------------------------------------

    if not hits:
        return Answer(
            text=(
                "I don't know — I couldn't find relevant information "
                "in the provided documents."
            ),
            sources=[],
            answered=False,
        )

    # ---------------------------------------------------------
    # STEP 2: Filter weak retrieval results
    # ---------------------------------------------------------

    relevant_hits = [
        hit for hit in hits
        if hit["score"] >= MIN_SIMILARITY
    ]

    if not relevant_hits:
        return Answer(
            text=(
                "I don't know — I couldn't find relevant information "
                "in the provided documents."
            ),
            sources=[],
            answered=False,
        )

    # ---------------------------------------------------------
    # STEP 3: Use only the best relevant chunks
    # ---------------------------------------------------------

    candidates = relevant_hits[:3]

    # ---------------------------------------------------------
    # STEP 4: Build context
    # ---------------------------------------------------------

    context_parts = []

    for i, hit in enumerate(candidates, start=1):
        context_parts.append(
            f"""
[DOCUMENT {i}]
Source document: {hit['source']}
Chunk: {hit['chunk_index']}
Similarity: {hit['score']:.3f}

Contract text:
{hit['text']}
"""
        )

    context = "\n".join(context_parts)

    # ---------------------------------------------------------
    # STEP 5: Ask Gemini
    # ---------------------------------------------------------

    try:
        answer_text = generate_answer(
            question=question,
            context=context,
        )

    except Exception as exc:
        return Answer(
            text=f"Unable to generate an answer: {exc}",
            sources=[],
            answered=False,
        )

    answer_text = answer_text.strip()

    # ---------------------------------------------------------
    # STEP 6: Gemini says it doesn't know
    # ---------------------------------------------------------

    if answer_text.lower() == "i don't know.":
        return Answer(
            text=(
                "I don't know — the provided documents do not contain "
                "enough information to answer this question."
            ),
            sources=[],
            answered=False,
        )

    # ---------------------------------------------------------
    # STEP 7: Add citations only for an actual answer
    # ---------------------------------------------------------

    citations = "\n".join(
        f"- {hit['source']} (chunk {hit['chunk_index']})"
        for hit in candidates
    )

    text = (
        f"{answer_text}\n\n"
        f"Sources:\n{citations}"
    )

    return Answer(
        text=text,
        sources=candidates,
        answered=True,
    )