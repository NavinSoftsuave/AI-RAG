"""Week 9 · server one — the clause-search MCP server.

Wraps the four read-only tools from agent/tools.py (Week 8) as a real MCP
server using fastmcp. This is "your own clause-search server" the task refers
to: it is YOUR capability, exposed the standard way instead of being wired
into the agent's Python by hand.

Architectural rule enforced here (see task's "Common mistakes" #2 and #3):
  - No LLM call anywhere in this file. The server offers capabilities; the
    HOST (the agent process) is the only place a model is invoked. Grep this
    file for "generate(" or any LLM client construction — there is none.
  - Only genuinely MODEL-INVOKED actions are exposed as @mcp.tool. Nothing
    here is exposed as a resource, because nothing here is inert context the
    app should just attach — every one of these four requires the model to
    decide an argument (which document? which clause? which term?) before it
    can run, which is precisely what makes it a tool and not a resource.

Run standalone for a manual smoke test:
    ./venv/bin/python mcp_servers/clause_search_server.py

Run under the agent via mcp_config.json (stdio transport, spawned by the
client — see agent/mcp_client.py).
"""

from pathlib import Path

from fastmcp import FastMCP

# Reuse the exact Week-8 tool implementations — this server does not
# reimplement clause-search logic, it exposes the one that already exists.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import tools as T  # noqa: E402
from rag.store import VectorStore  # noqa: E402

mcp = FastMCP(
    name="clause-search",
    instructions=(
        "Read-only tools over a fixed corpus of 5 contracts (MSA, its "
        "Amendment No. 1, a mutual NDA, an employment agreement, and a "
        "commercial lease). Use list_documents first if you don't already "
        "know which document key to use."
    ),
)

# One shared store for the process lifetime — the server owns its own state,
# the same way any real MCP server would (a DB connection, an index, a cache).
_store = VectorStore()


@mcp.tool
def list_documents() -> str:
    """List every contract available, with the short key to use in other
    tools' `document` argument (e.g. "msa", "nda", "lease")."""
    return T.list_documents()


@mcp.tool
def search_contracts(query: str) -> str:
    """Search across every contract for text relevant to `query`, combining
    semantic and keyword matching. Returns up to 3 ranked snippets, each
    tagged with its source document and chunk index. Use this first when you
    don't know which document or clause number holds the answer."""
    return T.search_contracts(query, store=_store)


@mcp.tool
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
    return T.get_clause(document, clause)


@mcp.tool
def resolve_defined_term(term: str, document: str = "") -> str:
    """Return where a capitalised defined term (e.g. "Agreement",
    "Confidential Information", "Premises") is defined and by what text. If
    the term is used but never defined in the given document, says so and
    reports the incorporating language instead of failing — a later amendment
    that never redefines "Agreement" is still answerable by pointing at the
    contract it inherits the definition from."""
    return T.resolve_defined_term(term, document or None)


if __name__ == "__main__":
    # stdio transport: the client spawns this as a subprocess and talks
    # JSON-RPC over stdin/stdout. This is the transport used by
    # mcp_config.json below.
    mcp.run(show_banner=False)
