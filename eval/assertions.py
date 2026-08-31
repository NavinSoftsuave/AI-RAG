"""Deterministic assertions — the checks a lookup can do for free.

The Week-6 rubric is explicit: never pay a model to verify something a rule can
check. These four assertions are pulled OUT of the LLM judge and run as plain
Python over the answer text and the source contracts:

  1. clause_refs_exist    — every clause reference (e.g. "7.2", "Section 8")
                            cited in the answer actually exists in some contract.
  2. dates_parseable      — any date mentioned in the answer parses as a real date.
  3. defined_terms_known  — every capitalised quoted-style defined term used in the
                            answer appears as a defined term in a contract.
  4. notice_periods_numeric — a notice/period answer contains a numeric figure
                            (a "30 days" answer must actually carry a number).

Each returns an AssertionResult(name, passed, detail). They never call an LLM.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rag.loaders import load_file

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
LEGAL_DOCS = [
    "sample_service_agreement.pdf",
    "sample_amendment.txt",
    "mutual_nda.txt",
    "employment_agreement.txt",
    "commercial_lease.txt",
]


@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: str


def _corpus_text() -> str:
    return "\n".join(load_file(DOCS_DIR / name) for name in LEGAL_DOCS)


# --- 1. clause references -----------------------------------------------------

_CLAUSE_REF_RE = re.compile(r"\b(?:Section|Clause)\s+(\d{1,2})(?:\.\d{1,2})?\b", re.I)
_CLAUSE_HEADING_RE = re.compile(r"(?:^|\s)(\d{1,2})\.\s+[A-Z]")


def clause_refs_exist(answer: str, corpus: str) -> AssertionResult:
    """Every 'Section N' / 'Clause N' cited in the answer maps to a real clause
    heading in the corpus."""
    refs = {m.group(1) for m in _CLAUSE_REF_RE.finditer(answer)}
    if not refs:
        return AssertionResult("clause_refs_exist", True, "no clause references cited")
    existing = {m.group(1) for m in _CLAUSE_HEADING_RE.finditer(corpus)}
    missing = sorted(refs - existing)
    return AssertionResult(
        "clause_refs_exist",
        not missing,
        "all cited clauses exist" if not missing else f"missing clauses: {missing}",
    )


# --- 2. dates -----------------------------------------------------------------

_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}\b"
)


def dates_parseable(answer: str, corpus: str) -> AssertionResult:
    """Any 'Month DD, YYYY' date in the answer parses as a real calendar date."""
    matches = list(_DATE_RE.finditer(answer))
    if not matches:
        return AssertionResult("dates_parseable", True, "no dates in answer")
    bad = []
    for m in matches:
        try:
            datetime.strptime(m.group(0), "%B %d, %Y")
        except ValueError:
            bad.append(m.group(0))
    return AssertionResult(
        "dates_parseable",
        not bad,
        "all dates parse" if not bad else f"unparseable dates: {bad}",
    )


# --- 3. defined terms ---------------------------------------------------------

_QUOTED_TERM_RE = re.compile(r'"([A-Z][A-Za-z ]{1,30})"')


def defined_terms_known(answer: str, corpus: str) -> AssertionResult:
    """Every quoted defined term used in the answer is defined somewhere in the
    corpus (i.e. appears quoted there too)."""
    used = {m.group(1) for m in _QUOTED_TERM_RE.finditer(answer)}
    if not used:
        return AssertionResult("defined_terms_known", True, "no defined terms quoted")
    defined = {m.group(1) for m in _QUOTED_TERM_RE.finditer(corpus)}
    unknown = sorted(used - defined)
    return AssertionResult(
        "defined_terms_known",
        not unknown,
        "all defined terms known" if not unknown else f"undefined terms: {unknown}",
    )


# --- 4. notice periods --------------------------------------------------------

_NUMBER_RE = re.compile(r"\b\d+\b|\b(?:one|two|three|five|ten|thirty|sixty|ninety)\b", re.I)


def notice_period_numeric(answer: str, corpus: str) -> AssertionResult:
    """An answer about a notice period / term / deadline must contain a number."""
    trigger = re.search(r"notice period|days'? (?:notice|prior)|within \w+ days|term of",
                        answer, re.I)
    if not trigger:
        return AssertionResult("notice_period_numeric", True, "not a notice-period answer")
    has_number = bool(_NUMBER_RE.search(answer))
    return AssertionResult(
        "notice_period_numeric",
        has_number,
        "numeric figure present" if has_number else "notice period stated with no number",
    )


ALL_ASSERTIONS = [
    clause_refs_exist,
    dates_parseable,
    defined_terms_known,
    notice_period_numeric,
]


def run_assertions(answer: str, corpus: str | None = None) -> list[AssertionResult]:
    """Run every deterministic assertion against an answer. No LLM calls."""
    corpus = corpus if corpus is not None else _corpus_text()
    return [check(answer, corpus) for check in ALL_ASSERTIONS]
