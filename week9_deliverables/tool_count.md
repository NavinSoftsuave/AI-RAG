# Tool count — before and after, from `tools/list`

Both counts below are taken directly from a live `tools/list` response via
`agent/mcp_client.py` (which populates its tool table only from that
response — see `wire_annotated.md` exchange 3), not from source code or
notes. Reproduce with:

```
# before (server one only, commit ac30491's mcp_config.json)
./venv/bin/python -c "
from agent.mcp_client import SyncMCPToolClient
c = SyncMCPToolClient(config_path='week9_deliverables/mcp_config.before.json')
print(sorted(c.tools)); c.close()"

# after (current mcp_config.json, server one + two)
./venv/bin/python -c "
from agent.mcp_client import SyncMCPToolClient
c = SyncMCPToolClient()
print(sorted(c.tools)); c.close()"
```

## N = 4 -> M = 8

### Before (server one — `clause-search` — only)

| # | tool name | server |
|---|---|---|
| 1 | `get_clause` | clause-search |
| 2 | `list_documents` | clause-search |
| 3 | `resolve_defined_term` | clause-search |
| 4 | `search_contracts` | clause-search |

### After (server one `clause-search` + server two `contract-repository`)

| # | tool name | server |
|---|---|---|
| 1 | `get_amendment_chain` | contract-repository *(new)* |
| 2 | `get_clause` | clause-search |
| 3 | `get_effective_date` | contract-repository *(new)* |
| 4 | `list_contract_ids` | contract-repository *(new)* |
| 5 | `list_documents` | clause-search |
| 6 | `lookup_contract` | contract-repository *(new)* |
| 7 | `resolve_defined_term` | clause-search |
| 8 | `search_contracts` | clause-search |

**4 tools before -> 8 tools after.** The 4 new tools are exactly the 4
`@mcp.tool`-decorated functions in `mcp_servers/contract_repository_server.py`
— nothing more, nothing less, and nothing hand-added to any list in the
agent's Python (`agent/mcp_client.py`'s `self.tools` dict is populated
entirely inside `MCPToolClient.connect()`'s loop over each server's
`tools/list` response — see the source for the exact code path).
