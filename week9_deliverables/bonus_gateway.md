# Bonus — one gateway, audit logging, token-scoped denial

`mcp_servers/gateway_server.py` puts both servers behind one front door: the
agent connects to `contract-gateway` alone (see
`week9_deliverables/mcp_config.gateway.json`), and the gateway fans out to
`clause-search` and `contract-repository` — each still its own real, separate
subprocess — via `FastMCP.as_proxy(mcp_config.json)`. Middleware
(`AuditAndScopeMiddleware`, hooked on the `tools/call` stage) does the two
things the bonus asks for:

## 1. One audit line per `tools/call`

Every call — allowed or denied, from either backend server — appends one
JSON line to `audit.log`: timestamp, caller (token), tool name (including
the `as_proxy`-added server prefix, e.g. `contract-repository_lookup_contract`),
best-effort extracted contract id, the raw arguments, and the decision.

```
{"ts": "...", "caller": "readonly-no-amendments", "tool": "contract-repository_get_amendment_chain", "contract_id": "MSA-2025-0142", "arguments": {"contract_id": "MSA-2025-0142"}, "decision": "DENIED"}
{"ts": "...", "caller": "readonly-no-amendments", "tool": "contract-repository_lookup_contract",     "contract_id": "MSA-2025-0142", "arguments": {"contract_id": "MSA-2025-0142"}, "decision": "ALLOWED"}
```

## 2. Per-token tool scoping, denial reaching the model as a recoverable message

A token named `readonly-no-amendments` (set via `MCP_CALLER_TOKEN` in the
gateway subprocess's env — see `mcp_config.gateway.denied.json`) is denied
`get_amendment_chain` while `lookup_contract` / `get_effective_date` /
`list_contract_ids` still work. The denial is raised as a `fastmcp.ToolError`
from the middleware, which MCP surfaces as an ordinary `tools/call` response
with `isError: true` and a human-readable message — the SAME shape as any
other tool failure (see `wire_annotated.md` exchange 4) — not a broken
connection or an uncaught exception.

Direct client proof (`client.call_tool` returns `(ok, message)` cleanly):

```
get_amendment_chain (should be DENIED): ok= False
  message: access denied: token 'readonly-no-amendments' is not permitted to
  call 'contract-repository_get_amendment_chain'. Base contract lookup
  (lookup_contract, get_effective_date) is still permitted — use those
  instead if they answer the question.

lookup_contract (should be ALLOWED): ok= True
  message: MSA-2025-0142: Master Services Agreement (Acme Corp / Globex Ltd) — status: active
```

Full agent run (model in the loop) against the SAME denied token — see
`agent_denied_run.txt` for the complete captured trajectory and audit trail:
the model attempted `get_amendment_chain`, read the denial message, and
worked around it using the tools still permitted to it rather than giving up
or crashing.

## What this does and does not prove

It proves the denial path is recoverable (the model gets a message, not a
crash) and that the audit trail captures every call including denied ones.
It does NOT prove real authentication — `MCP_CALLER_TOKEN` here is an
unsigned environment variable the launcher sets, which is convenient for
demonstrating the *scoping and audit logic* end-to-end but is not what a real
deployment would trust as an identity. A real gateway would authenticate the
caller (FastMCP ships OAuth/bearer-token providers for exactly this) before
this middleware ever runs — that piece is out of scope for this exercise but
is the honest gap to name.
