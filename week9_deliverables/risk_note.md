# risk_note.md — contract-repository MCP server, 5-line supply-chain risk note

**Who wrote it:** Not us — the task frames it as the knowledge team's own third-party server; treat it as vendor code we did not audit line-by-line, even though our stand-in implementation is fastmcp with an in-memory dict for this exercise.
**What it can reach:** Every contract's id, effective date, and full amendment chain across the whole repository — not scoped to the one deal our agent is working on, so one compromised call can enumerate the entire portfolio, NDA-covered agreements included.
**What it logs:** Unknown from our side — a third-party server's logging is opaque to us by default; assume it logs every `contract_id` argument it receives (i.e. which contracts we're actively interested in) unless the vendor states otherwise in writing.
**What a stolen token could do:** Read the effective date and amendment history of any contract in the repository, including ones outside this engagement, and correlate our lookup patterns to infer what deals we're reviewing and when.
**Ship or don't:** Ship, but scoped — connect it read-only, restrict it to the contract ids this engagement actually needs (bonus challenge's per-tool token scoping), and log our own `tools/call` audit trail independent of whatever the vendor logs, so we have a record even if theirs is unavailable or untrustworthy.
