# docstring_prompt.md — Week 9 requirement 5, the docstring half

The task's topic list says it plainly: a tool's docstring is not documentation
for a human reading the source — over MCP it becomes the `description` field
in the server's `tools/list` response (see `wire_annotated.md`, exchange 3),
which is literally prompt text the model reads to decide whether and how to
call the tool. This file is the before/after of that rewrite for
`get_clause`, the tool this week's error-recovery rewrite also targets.

## Before (Week 8)

```python
def get_clause(document: str, clause: str) -> str:
    """Return the verbatim text of one numbered clause of one contract.

    Raises ToolError if the clause number does not exist in that document — this
    is what turns a hallucinated clause reference into a visible tool failure
    instead of a fluent-sounding answer.
    """
```

What this docstring told the model, as prompt text: what the tool returns on
success, and that it can fail — but nothing about HOW to call it correctly
(what format is `clause`? what are the valid values of `document`?) or what
to do if it fails. A model with no other guidance has to infer the calling
convention from the parameter names alone.

## After (Week 9)

```python
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
```

Three things were deliberately added, each written AS a prompt instruction
rather than as after-the-fact documentation:

1. **A worked example of the calling convention** — `get_clause("msa", "8")`
   — instead of leaving the model to guess argument formats from names.
2. **An explicit promise about what the error looks like and why it's worth
   reading** — "does not fail silently... tells you which other document to
   check next" — so the model is primed to treat a `ToolError` as
   information to act on, not a dead end.
3. **An explicit instruction on what to DO with that information** — "retry
   ... before giving up and answering 'I don't know'" — directly targeting
   the Week-8 failure mode of a quiet give-up on a technically-recoverable
   error.

See `error_before_after.md` for the model's actual behaviour change this
produced on a real failing call, and `mcp_servers/clause_search_server.py`
for the docstring as it now appears verbatim in the live `tools/list`
response (`wire.json`, exchange 3).
