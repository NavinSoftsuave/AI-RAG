# Annotated wire capture — clause-search MCP server

Source: [`wire.json`](./wire.json), captured by `capture_wire.py` by spawning
`mcp_servers/clause_search_server.py` as a subprocess and speaking raw,
newline-delimited JSON-RPC 2.0 directly over its stdin/stdout — no MCP SDK
client library used for this capture, so every byte below is exactly what
crossed the wire, not a re-serialization of a parsed SDK object.

Four exchanges: `initialize` → `notifications/initialized` → `tools/list` →
`tools/call`. Every top-level field of every message is annotated below.

---

## Exchange 1 — `initialize`

**Sent** (client → server, request id `1`):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": { "name": "week9-wire-capture", "version": "0.1.0" }
  }
}
```

| Field | What it is |
|---|---|
| `jsonrpc` | Protocol marker — every MCP message is a JSON-RPC 2.0 envelope. Always the literal string `"2.0"`. |
| `id` | Correlates this request with its response. The server's reply below carries the same `id: 1` back so the client can match request↔response over one shared stdio pipe (no other framing). |
| `method` | `"initialize"` — the first message of every MCP session, always. Nothing else may be sent before it. |
| `params.protocolVersion` | The MCP protocol version the client speaks, so client and server can agree on a shared version before anything else happens. |
| `params.capabilities` | What the CLIENT supports (empty here — this capture script is a bare client with no sampling/roots/elicitation support). |
| `params.clientInfo` | Free-form identification of the client — name/version, purely descriptive, not authentication. |

**Received** (server → client, matching `id: 1`):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": { "...": "server capability flags" },
    "serverInfo": { "name": "clause-search", "version": "2.14.7" },
    "instructions": "Read-only tools over a fixed corpus of 5 contracts..."
  }
}
```

| Field | What it is |
|---|---|
| `result.protocolVersion` | The server confirming (or negotiating down to) a protocol version both sides can speak. |
| `result.capabilities` | What the SERVER supports: `tools.listChanged: true` (it can notify on tool-list changes), `resources`/`prompts` flags (both false here — this server exposes no resources or prompts, only tools), `tasks` (long-running call support). |
| `result.serverInfo.name` | `"clause-search"` — this is literally the `name=` I passed to `FastMCP(...)` in the server file. Note this is NOT the model's name — no model is involved anywhere in this exchange. |
| `result.serverInfo.version` | The **fastmcp library's** version (2.14.7), not my server's own version — fastmcp reports its own version here by default. |
| `result.instructions` | The `instructions=` string from `FastMCP(...)` — server-level guidance shown to whatever host connects, independent of any one tool. |

---

## Exchange 2 — `notifications/initialized`

**Sent** (client → server, no `id` — this is a *notification*, not a request):
```json
{ "jsonrpc": "2.0", "method": "notifications/initialized" }
```

| Field | What it is |
|---|---|
| `method` | `"notifications/initialized"` — the client telling the server "handshake complete, you may now expect normal requests." |
| (no `id`) | Notifications never carry an `id` and never get a response — that's the syntactic difference between a JSON-RPC *request* and a *notification*. `received` is `null` in wire.json for exactly this reason: nothing comes back. |

---

## Exchange 3 — `tools/list`

**Sent** (request id `2`):
```json
{ "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {} }
```

**Received** (id `2`, abbreviated — see `wire.json` for the full 4-tool array):
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      { "name": "list_documents", "description": "...", "inputSchema": {...} },
      { "name": "search_contracts", "description": "...", "inputSchema": {...} },
      { "name": "get_clause", "description": "...", "inputSchema": {...} },
      { "name": "resolve_defined_term", "description": "...", "inputSchema": {...} }
    ]
  }
}
```

| Field | What it is |
|---|---|
| `method` | `"tools/list"` — THIS is discovery. The client asks "what can you do?"; nothing is hard-coded on the client side. |
| `result.tools[]` | One entry per `@mcp.tool`-decorated function in the server file — four here, matching the four functions in `mcp_servers/clause_search_server.py`. |
| `tools[].name` | The exact Python function name (`get_clause`, etc.) — this is the string the model will later put in `tool_name` when it wants to call it. |
| `tools[].description` | **The tool's docstring, verbatim.** This is literally what a Python docstring is doing on the wire — it is not documentation for a human reading the source, it is the prompt text the model sees to decide whether and how to call this tool. See `docstring_prompt.md` for why this matters. |
| `tools[].inputSchema` | JSON Schema auto-generated by fastmcp from the function's type-hinted parameters (`document: str`, `clause: str`) — this is what lets the model know it must supply `document` and `clause` as strings, without any hand-written schema. |
| `tools[].outputSchema` | fastmcp's auto-generated wrapper schema for a plain-string return value — not written by hand either. |

**This message is the entire proof of "discovery instead of hard-coding".**
`agent/mcp_client.py`'s `MCPToolClient.connect()` populates its `self.tools`
dict directly from this response's `tools[]` array — nothing about tool
names, argument names, or count is written anywhere in the agent's Python.

---

## Exchange 4 — `tools/call`

**Sent** (request id `3`):
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_clause",
    "arguments": { "document": "msa", "clause": "8" }
  }
}
```

| Field | What it is |
|---|---|
| `method` | `"tools/call"` — the standard MCP method for actually invoking a tool (as opposed to `tools/list`, which only discovers). |
| `params.name` | Which discovered tool to run — `"get_clause"`, taken verbatim from a `tools/list` entry's `name`. |
| `params.arguments` | The actual argument values — `document="msa"`, `clause="8"` — supplied by whatever decided to make this call (in the full agent, the model; in this standalone capture script, hand-written to prove the wire format). |

**Received** (id `3`):
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [ { "type": "text", "text": "Master Services Agreement...(60) days' prior written notice..." } ],
    "structuredContent": { "result": "...same text..." },
    "isError": false
  }
}
```

| Field | What it is |
|---|---|
| `result.content` | A list of content blocks — here one `{"type": "text", "text": ...}` block, the tool's actual return value as a string. MCP content can also be images/resources, but this tool returns plain text. |
| `result.structuredContent` | fastmcp's auto-wrapped structured/typed version of the same return value, matching `outputSchema` above — provided so a client that wants typed data doesn't have to parse `content[0].text` itself. |
| `result.isError` | `false` here — this is the field a client checks to distinguish a **tool-level failure** (clause not found, bad argument — reported as `isError: true` with an error message in `content`, but still a normal JSON-RPC response) from a **transport-level failure** (the process died, malformed JSON — which would show up as a JSON-RPC `error` object instead of `result`, or no response at all). This distinction is exactly what makes the Week-9 recoverable-error rewrite (see `error_before_after.md`) work: a bad clause number comes back as `isError: true` with a human-readable message in `content[0].text`, not a broken pipe. Exchange 5 below is the same call with a clause number that does not exist, to show this in practice rather than just assert it. |

---

## Exchange 5 — `tools/call`, the failing case

**Sent** (id `4`, same tool, a clause number that does not exist):
```json
{
  "jsonrpc": "2.0", "id": 4, "method": "tools/call",
  "params": { "name": "get_clause", "arguments": { "document": "msa", "clause": "99" } }
}
```

**Received** (id `4`):
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [ { "type": "text", "text": "no clause '99' in Master Services Agreement (Acme Corp / Globex Ltd), dated January 15, 2025 — clauses run 1-11; see amendment (Amendment No. 1 to the Master Services Agreement, dated March 1, 2025)" } ],
    "isError": true
  }
}
```

This is the same shape as exchange 4 in every field EXCEPT: `isError` is now
`true`, and there is no `structuredContent` (fastmcp only attaches that
wrapper to a successful, schema-conforming result). The `content[0].text`
is exactly the Week-9 rewritten error message — the same string
`agent/tools.py::get_clause` raises as a `ToolError`, re-raised here as
`fastmcp.exceptions.ToolError` so it surfaces this cleanly (see the `_clean`
wrapper in `mcp_servers/clause_search_server.py`) rather than as an
unhandled-exception traceback with an `"Error calling tool '...'"` prefix,
which is what a bare `RuntimeError` produces by default. Both are equally
*recoverable* at the protocol level (`isError: true` either way, connection
stays open) — this fix is about the message being exactly what the tool
author wrote, with nothing added or lost in translation.

---

## Where the model call happens, and where it does not (one line)

**The model is called exactly once per agent step, entirely inside the host
process (`agent/contract_agent.py`'s `run_agent`, via `rag/llm.py:generate()`
→ the Gemini API) — never inside `mcp_servers/clause_search_server.py`, which
contains zero LLM client code and only ever returns plain Python string
computations over `tools/call`.**
