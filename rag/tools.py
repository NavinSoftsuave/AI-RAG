"""Tool definitions for contract analysis agent and fixed workflow.

Requirement 1:
- 3 distinct tools with non-overlapping descriptions.
- Tool 3 (`get_definitions`) uses an Enum for contract-version parameter.
- Each tool performs exactly one job.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from rag.store import VectorStore


class ContractVersion(str, Enum):
    ORIGINAL = "ORIGINAL"
    AMENDMENT_V1 = "AMENDMENT_V1"
    AMENDMENT_V2 = "AMENDMENT_V2"


class ClauseType(str, Enum):
    TERMINATION = "TERMINATION"
    NOTICE_PERIOD = "NOTICE_PERIOD"
    LIABILITY = "LIABILITY"
    PAYMENT_TERMS = "PAYMENT_TERMS"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    GOVERNING_LAW = "GOVERNING_LAW"


# Defined terms dictionary mapping (term, version) to definitions
DEFINITIONS_DATABASE: Dict[tuple[str, str], str] = {
    ("Effective Date", ContractVersion.ORIGINAL): (
        "Effective Date means July 1, 2025 as set forth in Section 1 of Commercial Lease Agreement."
    ),
    ("Effective Date", ContractVersion.AMENDMENT_V1): (
        "Effective Date under Amendment No. 1 means March 1, 2025."
    ),
    ("Effective Date", ContractVersion.AMENDMENT_V2): (
        "Effective Date under Amendment No. 2 means April 10, 2025."
    ),
    ("Notice Period", ContractVersion.ORIGINAL): (
        "Notice Period means thirty (30) days written notice prior to termination without cause."
    ),
    ("Notice Period", ContractVersion.AMENDMENT_V1): (
        "Notice Period under Amendment No. 1 means sixty (60) days prior written notice for convenience."
    ),
    ("Notice Period", ContractVersion.AMENDMENT_V2): (
        "Notice Period under Amendment No. 2 means two (2) weeks during probationary period."
    ),
    ("Confidential Information", ContractVersion.ORIGINAL): (
        "Confidential Information means any non-public information disclosed by one Party to the other, marked confidential or reasonably understood as confidential."
    ),
    ("Permitted Purpose", ContractVersion.ORIGINAL): (
        "Permitted Purpose means evaluating a potential business relationship between Disclosing and Receiving Parties."
    ),
    ("Cure Period", ContractVersion.AMENDMENT_V1): (
        "Cure Period means thirty (30) days following written notice of material breach."
    ),
}


def search_contract(query: str, vector_store: VectorStore, top_k: int = 4) -> List[Dict[str, Any]]:
    """Searches the vector store for contract text chunks matching semantic keywords or search queries."""
    if vector_store.count() == 0:
        return []
    return vector_store.search(query, top_k=top_k, mode="hybrid")


def get_clause(clause_type: ClauseType, vector_store: VectorStore) -> List[Dict[str, Any]]:
    """Extracts specific standardized clause content from contract text given a standard clause type."""
    query = clause_type.value.replace("_", " ").title() + " clause"
    if vector_store.count() == 0:
        return []
    return vector_store.search(query, top_k=3, mode="hybrid")


def get_definitions(term_name: str, version: ContractVersion) -> Dict[str, Any]:
    """Retrieves exact legal definitions or defined terms from the contract schedule or agreement version."""
    key = (term_name.strip(), version)
    definition = DEFINITIONS_DATABASE.get(key)
    if not definition:
        for (t, v), val in DEFINITIONS_DATABASE.items():
            if t.lower() == term_name.strip().lower() and v == version:
                return {"term": t, "version": v.value, "definition": val, "found": True}
        return {
            "term": term_name,
            "version": version.value,
            "definition": f"Definition for '{term_name}' in version '{version.value}' not found in schedule.",
            "found": False,
        }
    return {
        "term": term_name,
        "version": version.value,
        "definition": definition,
        "found": True,
    }
