"""Complete traces: one full record per request, enough to replay later.

A trace captures the whole pipeline for a single question — the question, the
retrieval mode, every retrieved chunk (source, index, score, text), the final
answer, and whether the app answered or refused. That is the raw material for
error analysis: you read the trace, not just the answer.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent.parent / "traces"


@dataclass
class RetrievedChunk:
    rank: int
    source: str
    chunk_index: int
    score: float
    text: str


@dataclass
class Trace:
    id: int
    question: str
    kind: str            # intended question type (lookup, conflict, ...)
    expected: str        # human note on a correct answer (reading aid only)
    mode: str            # retrieval mode used
    retrieved: list[RetrievedChunk]
    answer: str
    answered: bool       # did the app answer, or refuse?
    top_score: float


def write_traces(traces: list[Trace], path: Path) -> None:
    """Write traces as JSON Lines (one trace per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")


def read_traces(path: Path) -> list[dict]:
    """Read traces back as a list of dicts."""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
