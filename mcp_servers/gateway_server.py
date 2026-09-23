"""Week 9 bonus — one gateway in front of both servers.

The agent connects to ONE front door (this process); the gateway fans out to
clause-search and contract-repository (each still a separate subprocess,
unchanged, addressed via mcp_config.json exactly as agent/mcp_client.py
already does directly). Middleware here adds two things neither backend
server has any business doing itself:

  1. AUDIT LOGGING — one line per tools/call, appended to audit.log, with
     caller (a token/identity string from FastMCP's per-request Context),
     tool name, and any contract id found in the arguments — regardless of
     which backend server actually served the call.

  2. TOKEN SCOPING — a token may be denied specific tools. The denial is
     raised as a fastmcp ToolError, which the MCP layer surfaces as a normal
     tools/call response with isError: true (see wire_annotated.md exchange
     4) — i.e. a RECOVERABLE message the model reads and can act on ("try a
     different tool" / "tell the user this lookup isn't permitted"), not an
     uncaught exception that kills the connection.

No LLM call anywhere in this file either — same rule as the two backend
servers. The gateway is plumbing, not a second place the model runs.

Run standalone:
    ./venv/bin/python mcp_servers/gateway_server.py
"""

import json
import re
import time
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "audit.log"

# Which token is making this call. In a real deployment this comes off the
# transport (a bearer token / mTLS identity / OAuth claim via FastMCP's auth
# providers); for this exercise it's read from an env var the launcher sets,
# which is exactly as much plumbing as the scoping logic below actually needs
# to be provable end to end without standing up a full auth server.
import os

CALLER_TOKEN = os.environ.get("MCP_CALLER_TOKEN", "anonymous")

# Per-token tool denial list — the bonus's "scope a token so the
# amendment-chain tool is denied while base contract lookup still works".
TOKEN_DENIED_TOOLS: dict[str, set[str]] = {
    "readonly-no-amendments": {"get_amendment_chain"},
}

_CONTRACT_ID_RE = re.compile(r"[A-Z]{2,4}-\d{4}-\d{3,4}")


def _find_contract_id(arguments: dict) -> str:
    """Best-effort extraction of a contract id from call arguments, for the
    audit line — checks the obvious key first, falls back to a pattern scan
    so a differently-named argument (or a clause-search `document` key that
    isn't a repository id at all) still gets SOMETHING logged."""
    if not arguments:
        return "-"
    if "contract_id" in arguments:
        return str(arguments["contract_id"])
    for v in arguments.values():
        m = _CONTRACT_ID_RE.search(str(v))
        if m:
            return m.group(0)
    return "-"


def _is_denied(called_name: str, denied: set[str]) -> bool:
    """Match a denied tool name against the name actually called, tolerating
    the server-name prefix FastMCP.as_proxy adds when fanning out multiple
    servers (e.g. "get_amendment_chain" denies both that bare name AND
    "contract-repository_get_amendment_chain")."""
    return any(
        called_name == d or called_name.endswith("_" + d) for d in denied
    )


class AuditAndScopeMiddleware(Middleware):
    """One audit line per tools/call; denies tools not in this token's scope."""

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        arguments = context.message.arguments or {}
        denied = TOKEN_DENIED_TOOLS.get(CALLER_TOKEN, set())

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "caller": CALLER_TOKEN,
            "tool": name,
            "contract_id": _find_contract_id(arguments),
            "arguments": arguments,
        }

        if _is_denied(name, denied):
            record["decision"] = "DENIED"
            _write_audit_line(record)
            # A fastmcp ToolError here becomes a normal (isError: true)
            # tools/call RESPONSE, not a dropped connection — the model sees
            # a message it can act on, exactly like any other tool failure.
            raise ToolError(
                f"access denied: token {CALLER_TOKEN!r} is not permitted to "
                f"call {name!r}. Base contract lookup (lookup_contract, "
                "get_effective_date) is still permitted — use those instead "
                "if they answer the question."
            )

        record["decision"] = "ALLOWED"
        _write_audit_line(record)
        return await call_next(context)


def _write_audit_line(record: dict) -> None:
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def build_gateway() -> FastMCP:
    """Build the gateway as an in-process PROXY over BOTH stdio subprocesses
    named in mcp_config.json — the agent talks to this one object; it fans
    out to two real, separately-running server processes underneath."""
    config = json.loads((ROOT / "mcp_config.json").read_text(encoding="utf-8"))
    gateway = FastMCP.as_proxy(config, name="contract-gateway")
    gateway.add_middleware(AuditAndScopeMiddleware())
    return gateway


mcp = build_gateway()


if __name__ == "__main__":
    mcp.run(show_banner=False)
