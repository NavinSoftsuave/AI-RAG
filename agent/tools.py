"""The contract agent's tool surface.

Four tools, each a plain Python function with a JSON-ish signature the model is
told about. Every call is recorded (name, args, result summary, latency) so the
trajectory eval can score the PATH, not just the final answer.

Design note on least privilege (Week-8 topic): every tool here is read-only over
a fixed whitelist of documents in docs/. There is no write, no shell, no network.
`get_clause` and `resolve_defined_term` cannot reach outside DOCS_DIR because the
document name is resolved through DOC_REGISTRY, never joined from model output.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from rag.loaders import load_file

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# Whitelist: the model can only ever name one of these keys. Anything else is a
# hard error the agent sees as a tool failure, not a path it can traverse.
DOC_REGISTRY = {
    "msa": "sample_service_agreement.pdf",
    "amendment": "sample_amendment.txt",
    "nda": "mutual_nda.txt",
    "employment": "employment_agreement.txt",
    "lease": "commercial_lease.txt",
}

DOC_TITLES = {
    "msa": "Master Services Agreement (Acme Corp / Globex Ltd), dated January 15, 2025",
    "amendment": "Amendment No. 1 to the Master Services Agreement, dated March 1, 2025",
    "nda": "Mutual Non-Disclosure Agreement (Northwind / Contoso), dated February 1, 2025",
    "employment": "Employment Agreement (Initech LLC / Peter Gibbons), dated April 10, 2025",
    "lease": "Commercial Lease Agreement (Wayne Enterprises / Oscorp), dated June 1, 2025",
}


class ToolError(RuntimeError):
    """A tool was called with arguments that do not resolve to real contract text."""


@dataclass
class ToolCall:
    """One step of the trajectory."""
    name: str
    args: dict
    ok: bool
    result: str
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class ToolLog:
    calls: list[ToolCall] = field(default_factory=list)

    def record(self, call: ToolCall) -> None:
        self.calls.append(call)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.calls]


_doc_cache: dict[str, str] = {}


def _doc_text(doc: str) -> str:
    """Load a whitelisted document's text (cached)."""
    key = doc.strip().lower()
    if key not in DOC_REGISTRY:
        raise ToolError(
            f"unknown document {doc!r}; valid documents are {sorted(DOC_REGISTRY)}"
        )
    if key not in _doc_cache:
        _doc_cache[key] = " ".join(load_file(DOCS_DIR / DOC_REGISTRY[key]).split())
    return _doc_cache[key]


# --- tool 1: list_documents ---------------------------------------------------

def list_documents() -> str:
    """Return the contracts available, with their short keys."""
    return "\n".join(f"{key}: {DOC_TITLES[key]}" for key in DOC_REGISTRY)


# --- tool 2: search_contracts -------------------------------------------------

def search_contracts(query: str, store=None, top_k: int = 3) -> str:
    """Semantic/keyword search across every contract. Returns ranked snippets."""
    if not query or not query.strip():
        raise ToolError("query must be a non-empty string")
    if store is None:
        raise ToolError("search index unavailable")
    hits = store.search(query, top_k=top_k, mode="hybrid")
    if not hits:
        return "No matching contract text found."
    parts = []
    for i, h in enumerate(hits, start=1):
        snippet = h["text"][:600]
        parts.append(f"[{i}] {h['source']} (chunk {h['chunk_index']})\n{snippet}")
    return "\n\n".join(parts)


# --- tool 3: get_clause -------------------------------------------------------

_CLAUSE_SPLIT_RE = re.compile(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z][A-Z])")


def _clauses(doc: str) -> dict[str, tuple[str, str]]:
    """Map clause number -> (heading, body) for a whitelisted document."""
    text = _doc_text(doc)
    marks = [(m.group(1), m.start(1)) for m in _CLAUSE_SPLIT_RE.finditer(text)]
    out: dict[str, tuple[str, str]] = {}
    for i, (num, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        body = text[start:end].strip()
        heading = body.split(".", 1)[1].strip()[:60] if "." in body else ""
        out[num] = (heading, body)
    return out


# Week 9 requirement 5: which document a base agreement's amendment lives in,
# so a missing-clause error can point somewhere real instead of just failing.
# (Kept tiny and explicit rather than inferred, since guessing an amendment
# relationship from filenames alone is exactly the kind of fluent fiction this
# tool exists to prevent.)
_AMENDS = {"msa": "amendment"}  # msa's terms may be superseded by "amendment"


def get_clause(document: str, clause: str) -> str:
    """Return the verbatim text of one numbered clause of one contract.

    Ask for a clause the way a lawyer would cite it: the short document key
    (see list_documents) and the clause number as printed in that contract,
    e.g. get_clause("msa", "8"). Every clause returned is grounded, verbatim
    text — never a summary or a paraphrase — so you can quote it directly.

    If the clause number does not exist in that document, this does not fail
    silently: it tells you every clause number that DOES exist there, and — if
    the document is a base agreement with a known amendment — tells you which
    other document to check next, the way a human paralegal would say "that's
    not in the MSA, but check the amendment" instead of just "not found".
    Read that message and retry with a real clause number or the suggested
    document before giving up and answering "I don't know".
    """
    clause_no = str(clause).strip().lstrip("Ss").lstrip("ection ").strip()
    clause_no = re.sub(r"^(?:Section|Clause)\s*", "", str(clause).strip(), flags=re.I)
    clause_no = clause_no.split(".")[0].strip()
    doc_key = document.strip().lower()
    table = _clauses(document)
    if clause_no not in table:
        available = sorted(table, key=int)
        span = (
            f"clauses run {available[0]}-{available[-1]}"
            if len(available) > 1 else f"only clause {available[0]} exists"
        ) if available else "no numbered clauses were found at all"
        amendment_hint = ""
        amends_key = _AMENDS.get(doc_key)
        if amends_key and amends_key in DOC_REGISTRY:
            amendment_hint = f"; see {amends_key} ({DOC_TITLES[amends_key]})"
        raise ToolError(
            f"no clause {clause!r} in {DOC_TITLES.get(doc_key, document)} — "
            f"{span}{amendment_hint}"
        )
    heading, body = table[clause_no]
    return f"{DOC_TITLES[doc_key]}\nClause {clause_no}. {heading}\n\n{body}"


# --- tool 4: resolve_defined_term --------------------------------------------

def resolve_defined_term(term: str, document: str | None = None) -> str:
    """Return where a capitalised defined term is defined, and by what text.

    A defined term is one introduced in quotes, e.g. ("Agreement"). This is the
    step the agent skips when it answers a termination question without ever
    establishing WHICH agreement "this Agreement" refers to.
    """
    term = str(term).strip().strip('"').strip("'")
    if not term:
        raise ToolError("term must be a non-empty string")

    docs = [document.strip().lower()] if document else list(DOC_REGISTRY)
    if document and docs[0] not in DOC_REGISTRY:
        raise ToolError(
            f"unknown document {document!r}; valid documents are {sorted(DOC_REGISTRY)}"
        )

    found = []
    t = re.escape(term)
    # Three ways a contract introduces a defined term, most explicit first:
    #   '"X" means ...'  |  '... (the "X") ...'  |  '... "X" does not include ...'
    means = re.compile(r'[^.]*"' + t + r'"\s+(?:means|shall mean|includes)[^.]*\.', re.I)
    parenthetical = re.compile(
        r'[^.]*\(\s*(?:the\s+|each,\s+an?\s+|an?\s+)?"' + t + r'"\s*\)[^.]*\.', re.I)
    scoped = re.compile(r'[^.]*"?' + t + r'"?\s+does not include[^.]*\.', re.I)
    for key in docs:
        text = _doc_text(key)
        for rx in (means, parenthetical, scoped):
            m = rx.search(text)
            if m:
                found.append(f"{key} [defined]: {m.group(0).strip()}")
                break

    if found:
        return "\n".join(found)

    # The term is used but never defined here. For a contract agent that is a
    # real and important finding (e.g. Amendment No. 1 says "this Agreement"
    # without defining it — it inherits the definition from the base MSA), so we
    # report the incorporating language rather than failing.
    incorporation = []
    use_rx = re.compile(r'[^.]*\bthis ' + re.escape(term) + r'\b[^.]*\.', re.I)
    for key in docs:
        m = use_rx.search(_doc_text(key))
        if m:
            incorporation.append(f"{key} [used, not defined here]: {m.group(0).strip()}")

    if incorporation:
        return (
            f'"{term}" is NOT defined in ' + (document or "these documents") +
            "; it is used as an inherited/incorporated term:\n" +
            "\n".join(incorporation)
        )

    raise ToolError(
        f'"{term}" is not a defined term in '
        f'{document or "any contract in the corpus"}'
    )
