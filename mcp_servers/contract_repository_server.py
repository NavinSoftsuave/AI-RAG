"""Week 9 · server two — the contract-repository server.

Stands in for the "knowledge team's" third-party contract-repository MCP
server the task describes: lookup by contract id, its effective date, and its
amendment chain. Deliberately built as a SEPARATE, independent server —
different ID scheme, different data source (an in-memory registry keyed by
contract id, not the clause-search server's document keys), no import of
anything from mcp_servers/clause_search_server.py or agent/. That independence
is the point: bolting this on must be provable as config-only, and a server
that secretly shared code with server one would not prove that.

Same architectural rules as server one:
  - No LLM call anywhere in this file.
  - Every tool here needs a model-supplied argument (which contract id?) to
    run, so tools is the right choice, not resources.

Run standalone for a manual smoke test:
    ./venv/bin/python mcp_servers/contract_repository_server.py
"""

from fastmcp import FastMCP

mcp = FastMCP(
    name="contract-repository",
    instructions=(
        "Look up a contract by its repository id to get its effective date "
        "and amendment chain. Repository ids look like 'MSA-2025-0142', not "
        "the clause-search server's short keys (msa, nda, ...) — the two "
        "servers use different identifiers for the same underlying contracts."
    ),
)

# A tiny in-memory "repository" — the same 5 contracts server one serves, but
# addressed by the id scheme a real contract-management system would use, to
# make the two servers' independence concrete rather than asserted.
_REPOSITORY = {
    "MSA-2025-0142": {
        "title": "Master Services Agreement (Acme Corp / Globex Ltd)",
        "effective_date": "2025-01-15",
        "status": "active",
        "amendments": ["AMD-2025-0142-01"],
    },
    "AMD-2025-0142-01": {
        "title": "Amendment No. 1 to MSA-2025-0142",
        "effective_date": "2025-03-01",
        "status": "active",
        "amends": "MSA-2025-0142",
        "amendments": [],
    },
    "NDA-2025-0031": {
        "title": "Mutual Non-Disclosure Agreement (Northwind / Contoso)",
        "effective_date": "2025-02-01",
        "status": "active",
        "amendments": [],
    },
    "EMP-2025-0087": {
        "title": "Employment Agreement (Initech LLC / Peter Gibbons)",
        "effective_date": "2025-04-10",
        "status": "active",
        "amendments": [],
    },
    "LSE-2025-0055": {
        "title": "Commercial Lease Agreement (Wayne Enterprises / Oscorp)",
        "effective_date": "2025-06-01",
        "status": "active",
        "amendments": [],
    },
}


@mcp.tool
def lookup_contract(contract_id: str) -> str:
    """Look up a contract's title and status by its repository id
    (e.g. "MSA-2025-0142"). Use list_contract_ids if you don't know the id."""
    rec = _REPOSITORY.get(contract_id.strip().upper())
    if rec is None:
        return (
            f"no contract with id {contract_id!r} in the repository; "
            f"known ids: {sorted(_REPOSITORY)}"
        )
    return f"{contract_id}: {rec['title']} — status: {rec['status']}"


@mcp.tool
def get_effective_date(contract_id: str) -> str:
    """Return the effective date (YYYY-MM-DD) of a contract by repository id."""
    rec = _REPOSITORY.get(contract_id.strip().upper())
    if rec is None:
        return (
            f"no contract with id {contract_id!r} in the repository; "
            f"known ids: {sorted(_REPOSITORY)}"
        )
    return f"{contract_id} effective date: {rec['effective_date']}"


@mcp.tool
def get_amendment_chain(contract_id: str) -> str:
    """Return the full amendment chain for a contract by repository id: every
    amendment id that modifies it, in order, each with its own effective
    date. Use this before answering any question about current contract
    terms — a base agreement's terms may be superseded by a later amendment
    with a later effective date."""
    key = contract_id.strip().upper()
    rec = _REPOSITORY.get(key)
    if rec is None:
        return (
            f"no contract with id {contract_id!r} in the repository; "
            f"known ids: {sorted(_REPOSITORY)}"
        )
    chain = rec.get("amendments", [])
    if not chain:
        base = rec.get("amends")
        if base:
            return (
                f"{contract_id} is itself an amendment to {base} "
                f"(effective {rec['effective_date']}); it has no amendments "
                "of its own."
            )
        return f"{contract_id} has no amendments on file."
    lines = [f"{contract_id} amendment chain:"]
    for amd_id in chain:
        amd = _REPOSITORY.get(amd_id, {})
        lines.append(
            f"  {amd_id}: {amd.get('title', '(unknown)')} "
            f"— effective {amd.get('effective_date', '?')}"
        )
    return "\n".join(lines)


@mcp.tool
def list_contract_ids() -> str:
    """List every contract id in the repository, with its title."""
    return "\n".join(f"{cid}: {rec['title']}" for cid, rec in _REPOSITORY.items())


if __name__ == "__main__":
    mcp.run(show_banner=False)
