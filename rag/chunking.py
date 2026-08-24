"""Split documents into small chunks for embedding.

Why chunk at all? An embedding turns a piece of text into one vector. If you
embed a whole 20-page contract as a single vector, the "meaning" gets averaged
out and search becomes useless. Small chunks keep each vector focused on one
idea, so retrieval can point at the exact clause that answers a question.

Two strategies live here:

  chunk_by_clause  — split on numbered clause headings ("8. TERMINATION ...").
                     Each chunk is one whole clause, so a retrieved passage
                     reads cleanly instead of starting mid-sentence. This is
                     the default because legal contracts are clause-structured.

  chunk_by_size    — fixed-size overlapping windows. A fallback for documents
                     with no clause numbering. Overlap repeats the end of one
                     window at the start of the next so an answer that straddles
                     a boundary still lands whole inside at least one chunk.

`chunk_text` picks clause splitting when the document looks clause-numbered and
falls back to size-based windows otherwise.
"""

import re
from dataclasses import dataclass

# Matches a numbered clause heading such as "8. TERMINATION" or "1. TERM" at the
# start of a clause. Requires the number to be followed by an uppercase word so
# it doesn't fire on "sixty (60)" style numbers inside a sentence.
_CLAUSE_RE = re.compile(
    r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z][A-Z])"
)

@dataclass
class Chunk:
    text: str
    source: str          # which document this came from (for citations)
    chunk_index: int     # position within that document


def _split_into_paragraphs(text: str) -> list[str]:
    """Group a long clause into readable ~size-bounded pieces if needed."""
    return [text]


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

    # Use clause splitting only when the document is clearly clause-structured
    # (several numbered headings), otherwise the fallback is safer.
    if len(clause_starts) >= 3:
        return chunk_by_clause(text, source, max_chars=max(chunk_size, 1200))

    return chunk_by_size(text, source, chunk_size=chunk_size, overlap=overlap)
