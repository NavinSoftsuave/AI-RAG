"""LLM-as-judge for the single binary correctness criterion.

The judge grades ONLY faithfulness+answers-the-question (see judge_v1.txt). The
mechanical criteria (clause exists, date parses, defined term known, figure
numeric) are handled by eval/assertions.py, NOT here — a lookup does that for
free. Judge calls are cached to disk via rag.llm.generate.
"""

from dataclasses import dataclass
from pathlib import Path

from rag.llm import _cache_path, generate

JUDGE_DIR = Path(__file__).resolve().parent


@dataclass
class Verdict:
    correct: bool
    reason: str
    raw: str


def load_prompt(version: str) -> str:
    """Load a judge prompt file, e.g. version='v1' -> judge_v1.txt."""
    return (JUDGE_DIR / f"judge_{version}.txt").read_text(encoding="utf-8")


def _build_prompt(question: str, context: str, answer: str, version: str) -> str:
    return (
        f"{load_prompt(version)}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"ANSWER:\n{answer}\n"
    )


def is_cached(question: str, context: str, answer: str, version: str = "v1") -> bool:
    return _cache_path(_build_prompt(question, context, answer, version)).exists()


def judge(
    question: str, context: str, answer: str, version: str = "v1",
    cached_only: bool = False,
) -> Verdict | None:
    """Grade one answer. Returns None when cached_only and no cached verdict
    exists (so the eval can run fully offline without spending quota)."""
    prompt = _build_prompt(question, context, answer, version)
    if cached_only and not _cache_path(prompt).exists():
        return None
    raw = generate(prompt).strip()
    first = raw.splitlines()[0].strip().upper() if raw else ""
    correct = first.startswith("CORRECT")
    reason = raw.splitlines()[1].strip() if len(raw.splitlines()) > 1 else ""
    return Verdict(correct=correct, reason=reason, raw=raw)
