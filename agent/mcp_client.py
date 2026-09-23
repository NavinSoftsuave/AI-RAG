"""Week 9 — the generic multi-server MCP client the agent runs on.

This module is the ONLY place that knows how to talk MCP. It:
  1. reads mcp_config.json,
  2. spawns every configured server over stdio and does the JSON-RPC
     initialize handshake,
  3. calls tools/list on each and merges the results into one flat tool
     table, keyed by tool name -> which server owns it,
  4. exposes one generic `call_tool(name, args)` that dispatches to whichever
     server actually owns that tool name.

Nothing here is specific to "clause-search" or "contract-repository" — it
would work identically for any MCP server, which is the whole point: the
agent (contract_agent.py) calls tools through this client without knowing or
caring how many servers are configured or what they're named. Adding a
second server to mcp_config.json changes ZERO lines in this file and ZERO
lines in contract_agent.py — see agent_diff.txt.
"""

import asyncio
import json
import queue
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG_PATH = Path(__file__).resolve().parent.parent / "mcp_config.json"


@dataclass
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict
    server: str  # which configured server this tool came from


class MCPToolClient:
    """Connects to every server in mcp_config.json, discovers their tools via
    tools/list, and dispatches tools/call generically by tool name.

    Usage (see agent/contract_agent.py):
        client = MCPToolClient()
        await client.connect()
        tools = client.tools                       # discovered, not hard-coded
        result = await client.call_tool(name, args)  # routed by name
        await client.close()
    """

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or CONFIG_PATH
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}  # server name -> session
        self.tools: dict[str, DiscoveredTool] = {}      # tool name -> tool
        self.raw_exchanges: list[dict] = []             # for wire.json capture

    async def connect(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        for server_name, spec in config.get("mcpServers", {}).items():
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env"),
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))

            init_result = await session.initialize()
            self.raw_exchanges.append({
                "server": server_name,
                "direction": "initialize",
                "result": _to_jsonable(init_result),
            })

            self._sessions[server_name] = session

            listed = await session.list_tools()
            self.raw_exchanges.append({
                "server": server_name,
                "direction": "tools/list",
                "result": _to_jsonable(listed),
            })
            for tool in listed.tools:
                if tool.name in self.tools:
                    raise RuntimeError(
                        f"tool name collision: {tool.name!r} offered by both "
                        f"{self.tools[tool.name].server!r} and {server_name!r}"
                    )
                self.tools[tool.name] = DiscoveredTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server=server_name,
                )

    async def call_tool(self, name: str, args: dict) -> tuple[bool, str]:
        """Dispatch a tools/call to whichever server owns `name`.

        Returns (ok, text). Never raises for a normal tool-level error — MCP
        surfaces that as isError on the result, which is translated to
        ok=False here so the agent can treat it exactly like any other tool
        failure, recoverable-message included.
        """
        tool = self.tools.get(name)
        if tool is None:
            return False, (
                f"unknown tool {name!r}; discovered tools are "
                f"{sorted(self.tools)}"
            )
        session = self._sessions[tool.server]
        result = await session.call_tool(name, args)
        self.raw_exchanges.append({
            "server": tool.server,
            "direction": "tools/call",
            "request": {"name": name, "arguments": args},
            "result": _to_jsonable(result),
        })
        text_parts = [c.text for c in result.content if hasattr(c, "text")]
        text = "\n".join(text_parts) if text_parts else str(result.content)
        return (not result.isError), text

    async def close(self) -> None:
        await self._stack.aclose()

    # --- sync convenience wrapper -------------------------------------------
    # contract_agent.py's run_agent() is synchronous (Week-8 design). Rather
    # than making the whole Week-8 eval pipeline async (which WOULD touch
    # contract_agent.py), this offers a blocking facade backed by one event
    # loop the caller owns for the life of a session.


class SyncMCPToolClient:
    """Blocking wrapper around MCPToolClient for the synchronous agent loop.

    This is what contract_agent.py actually imports. It exists so the
    Week-8 agent loop's signature (and every line of its logic) never has to
    change to become async just to speak MCP — the sync/async boundary is
    fully absorbed here, one layer below the agent.

    Implementation note: anyio (which the MCP SDK's stdio transport is built
    on) ties a TaskGroup's cancel scope to the asyncio Task it was entered
    in. Calling connect()/call_tool()/close() as separate top-level
    loop.run_until_complete() calls each creates a NEW Task, so the
    AsyncExitStack's context managers (opened inside one Task) break when
    torn down from another — "Attempted to exit cancel scope in a different
    task than it was entered in". The fix is to run the client's entire
    session — connect, every call, and close — inside ONE coroutine that
    never returns until close is requested, on a dedicated background
    thread's event loop, bridged to synchronous calls via a queue.
    """

    def __init__(self, config_path: Path | None = None):
        self._client = MCPToolClient(config_path)
        self._loop = asyncio.new_event_loop()
        self._request_q: "queue.Queue[tuple[str, tuple, queue.Queue]]" = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise self._startup_error

    _startup_error: Exception | None = None

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._session())

    async def _session(self) -> None:
        try:
            await self._client.connect()
        except Exception as exc:  # noqa: BLE001 — surfaced on the main thread
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()

        while True:
            method, args, reply_q = await self._loop.run_in_executor(
                None, self._request_q.get)
            if method == "_close":
                await self._client.close()
                reply_q.put((None, None))
                return
            try:
                result = await getattr(self._client, method)(*args)
                reply_q.put((result, None))
            except Exception as exc:  # noqa: BLE001 — relayed to the caller
                reply_q.put((None, exc))

    def _call(self, method: str, *args):
        reply_q: "queue.Queue[tuple]" = queue.Queue()
        self._request_q.put((method, args, reply_q))
        result, exc = reply_q.get()
        if exc is not None:
            raise exc
        return result

    @property
    def tools(self) -> dict[str, DiscoveredTool]:
        return self._client.tools

    @property
    def raw_exchanges(self) -> list[dict]:
        return self._client.raw_exchanges

    def call_tool(self, name: str, args: dict) -> tuple[bool, str]:
        return self._call("call_tool", name, args)

    def close(self) -> None:
        self._call("_close")
        self._thread.join(timeout=5)
        self._loop.close()


def _to_jsonable(obj):
    """Best-effort conversion of MCP SDK result objects to plain JSON for the
    wire-capture log — pydantic models expose model_dump()."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj
