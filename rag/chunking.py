"""Split documents into chunks for embedding.

``chunk_text`` splits on numbered clause headings when a document is
clause-structured (contracts) and falls back to fixed-size overlapping windows
otherwise.
"""

import re
from dataclasses import dataclass

# Numbered clause heading, e.g. "8. TERMINATION". Requires an uppercase word
# after the number so it doesn't fire on "sixty (60)" inside a sentence.
_CLAUSE_RE = re.compile(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z][A-Z])")


@dataclass
class Chunk:
    text: str
    source: str          # source document, for citations
    chunk_index: int     # position within the document


def chunk_by_clause(
    text: str,
    source: str,
    max_chars: int = 1200,
) -> list[Chunk]:
    """Split on numbered clause headings; keep each clause as one chunk.

    If a single clause is longer than max_chars it is further split on sentence
    boundaries so no one chunk becomes unwieldy for the embedder.
    """
    text = " ".join(text.split())
    if not text:
        return []

    # Find where each numbered clause begins.
    starts = [m.start(1) for m in _CLAUSE_RE.finditer(text)]
    if not starts:
        return []

    # Everything before the first numbered clause is the title/preamble.
    segments: list[str] = []
    if starts[0] > 0:
        segments.append(text[: starts[0]].strip())
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        segments.append(text[start:end].strip())

    chunks: list[Chunk] = []
    index = 0
    for segment in segments:
        if not segment:
            continue
        for piece in _cap_length(segment, max_chars):
            chunks.append(Chunk(text=piece, source=source, chunk_index=index))
            index += 1
    return chunks


def _cap_length(segment: str, max_chars: int) -> list[str]:
    """Split an over-long clause on sentence boundaries, keeping the heading."""
    if len(segment) <= max_chars:
        return [segment]

    sentences = re.split(r"(?<=\.)\s+", segment)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current.strip())
    return pieces


def chunk_by_size(
    text: str,
    source: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[Chunk]:
    """Fixed-size overlapping windows, ending on sentence boundaries when close."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = " ".join(text.split())
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size
        window = text[start:end]

        if end < len(text):
            last_period = window.rfind(". ")
            if last_period > chunk_size // 2:
                window = window[: last_period + 1]
                end = start + last_period + 1

        chunk = window.strip()
        if chunk:
            chunks.append(Chunk(text=chunk, source=source, chunk_index=index))
            index += 1

        start = end - overlap if end - overlap > start else end

    return chunks


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[Chunk]:
    """Chunk a document, preferring clause-aware splitting for contracts.

    If the text has at least a few numbered clause headings, split on those so
    each chunk is a whole clause. Otherwise fall back to fixed-size windows.
    """
    normalised = " ".join(text.split())
    clause_starts = list(_CLAUSE_RE.finditer(normalised))

    # Only clause-split when several numbered headings are present.
    if len(clause_starts) >= 3:
        return chunk_by_clause(text, source, max_chars=max(chunk_size, 1200))

    return chunk_by_size(text, source, chunk_size=chunk_size, overlap=overlap)
