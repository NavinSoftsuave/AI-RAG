"""Grounded answering: answer ONLY from retrieved chunks, or say "I don't know".

This is the "generation" half of Retrieval-Augmented Generation. We run fully
locally without an LLM, so the answer is EXTRACTIVE: we surface the sentence(s)
from the retrieved passage that best match the question, always with a citation
to the source document. If nothing retrieved is similar enough, we refuse
instead of guessing.

Because there is no LLM to rephrase, "extractive" means the answer is quoted
verbatim from the contract. We narrow a whole clause down to its most relevant
sentence so the answer is focused, and still show the full clause for context.

The refusal is the most important behaviour to demonstrate: a RAG system must
admit "the answer isn't in these documents" rather than invent one.
"""

import re
from dataclasses import dataclass

# If the best retrieved chunk is below this cosine similarity, we treat the
# question as unanswerable from the documents. BGE embeddings rarely score
# unrelated text below ~0.5, so we set the bar fairly high. Tune it against your
# own data: too low and it answers off-topic questions; too high and it refuses
# valid ones.
MIN_SIMILARITY = 0.60

# Words too common to help distinguish which sentence answers a question.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "of", "to",
    "in", "on", "for", "and", "or", "with", "by", "at", "as", "that", "this",
    "it", "its", "what", "which", "who", "how", "when", "where", "does", "do",
    "shall", "will", "may", "any", "all", "under", "from", "into",
}


@dataclass
class Answer:
    text: str
    sources: list[dict]   # the chunks we grounded on (source + score + text)
    answered: bool        # False => "I don't know"


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _best_sentences(question: str, passage: str, limit: int = 2) -> str:
    """Pick the sentence(s) in `passage` most relevant to `question`.

    Scoring is simple keyword overlap — enough to point at the answer line
    without an LLM. Ties keep original order so the quote reads naturally.
    """
    q_words = _keywords(question)
    sentences = re.split(r"(?<=[.;])\s+", passage)
    scored = []
    for i, sentence in enumerate(sentences):
        overlap = len(q_words & _keywords(sentence))
        scored.append((overlap, -i, sentence))

    # Keep only sentences that share at least one keyword with the question.
    relevant = [s for s in scored if s[0] > 0]
    if not relevant:
        # No keyword match inside the clause — fall back to the whole passage.
        return passage

    relevant.sort(reverse=True)
    chosen = relevant[:limit]
    # Restore reading order (by original index, which we stored negated).
    chosen.sort(key=lambda s: -s[1])
    return " ".join(s[2].strip() for s in chosen)


def build_answer(question: str, hits: list[dict]) -> Answer:
    if not hits or hits[0]["score"] < MIN_SIMILARITY:
        return Answer(
            text=(
                "I don't know — I couldn't find anything in the provided "
                "documents that answers this question."
            ),
            sources=hits[:1] if hits else [],
            answered=False,
        )

    # Retrieval isn't perfect: the clause that answers the question may be the
    # 2nd or 3rd hit, not the 1st (their similarity scores are often very
    # close). So among the top few retrieved chunks, pick the one whose best
    # sentence shares the most keywords with the question, and answer from that.
    q_words = _keywords(question)

    def clause_relevance(hit: dict) -> int:
        return len(q_words & _keywords(hit["text"]))

    candidates = hits[:3]
    best = max(candidates, key=clause_relevance)
    # If nothing shares a keyword, fall back to the top-scored chunk.
    if clause_relevance(best) == 0:
        best = hits[0]

    citation = f"{best['source']} (chunk {best['chunk_index']})"
    answer_line = _best_sentences(question, best["text"])

    text = f"{answer_line}\n\nSource: {citation}"
    # Put the chosen chunk first so the UI's "retrieved chunks" panel matches.
    ordered = [best] + [h for h in hits if h is not best]
    return Answer(text=text, sources=ordered, answered=True)
