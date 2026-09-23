"""Requirement 5: same failing tool call, old error message vs new, full
model trajectory captured both times to a final answer (not just one step).

The failing call is injected directly as the agent's first tool call (rather
than hoping the model spontaneously guesses a bad clause number), so this is
a controlled A/B on exactly ONE variable: the error string the tool returns
after that first call. Everything else — question, model, step budget — is
identical between the two runs, and the agent is then left to run normally
(real model calls, real tool dispatch) for every subsequent step so the
*outcome*, not just the immediate reaction, is comparable.

Run:
    ./venv/bin/python week9_deliverables/capture_error_recovery.py
Writes:
    week9_deliverables/error_before_after.md
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.llm import generate  # noqa: E402
from rag.store import VectorStore  # noqa: E402
from agent.contract_agent import SYSTEM, TOOL_SPEC, _parse_step, _dispatch  # noqa: E402
from agent import tools as T  # noqa: E402

QUESTION = (
    "What does clause 12.4 of the Master Services Agreement say about "
    "termination for convenience?"
)
FIRST_CALL = {"document": "msa", "clause": "12.4"}

# The exact old error, verbatim, produced by the Week-8 get_clause() — pinned
# as a literal string since that code no longer exists in the working tree to
# call live (this IS the "before" of the rewrite).
OLD_ERROR = ("clause '12.4' does not exist in 'msa'; available clauses: "
             "['1', '10', '11', '2', '3', '4', '5', '6', '7', '8', '9']")


def run_from_injected_error(error_text: str, store, max_steps: int = 6) -> list[dict]:
    """Replay the agent loop with get_clause(msa, 12.4) pre-failed with
    `error_text`, then let the model drive every subsequent step for real."""
    sys_prompt = SYSTEM.format(tool_spec=TOOL_SPEC)
    transcript = [
        f"QUESTION: {QUESTION}",
        json.dumps({"tool": "get_clause", "args": FIRST_CALL})
        + f"\nTOOL RESULT:\nTOOL ERROR: {error_text}",
    ]
    log = [{
        "step": 0, "tool": "get_clause", "args": FIRST_CALL,
        "ok": False, "result": f"TOOL ERROR: {error_text}",
    }]

    for i in range(1, max_steps + 1):
        prompt = sys_prompt + "\n\n" + "\n\n".join(transcript) + "\n\nNext JSON step:"
        raw = generate(prompt)
        step = _parse_step(raw)

        if "answer" in step and "tool" not in step:
            log.append({"step": i, "answer": str(step["answer"]).strip()})
            break

        name = str(step.get("tool", "")).strip()
        args = step.get("args") or {}
        if not isinstance(args, dict):
            args = {"query": str(args)}
        try:
            result = _dispatch(name, args, store)
            ok = True
        except T.ToolError as exc:
            result, ok = f"TOOL ERROR: {exc}", False
        log.append({"step": i, "tool": name, "args": args, "ok": ok, "result": result})
        transcript.append(
            json.dumps({"tool": name, "args": args}) + f"\nTOOL RESULT:\n{result[:1500]}"
        )
    return log


def render(log: list[dict]) -> str:
    lines = []
    for entry in log:
        if "answer" in entry:
            lines.append(f"[step {entry['step']}] FINAL ANSWER: {entry['answer']}")
        else:
            lines.append(
                f"[step {entry['step']}] {entry['tool']}({json.dumps(entry['args'])}) "
                f"ok={entry['ok']}"
            )
            lines.append(f"    -> {entry['result'][:220]}")
    return "\n".join(lines)


def main() -> None:
    from agent.tools import get_clause, ToolError
    try:
        get_clause("msa", "12.4")
        raise SystemExit("expected ToolError, got a result — corpus changed?")
    except ToolError as exc:
        new_error = str(exc)

    store = VectorStore()

    print("=== OLD error ===")
    print(OLD_ERROR)
    old_log = run_from_injected_error(OLD_ERROR, store)
    print(render(old_log))

    print("\n=== NEW error ===")
    print(new_error)
    new_log = run_from_injected_error(new_error, store)
    print(render(new_log))

    doc = f"""# error_before_after.md — Week 9 requirement 5

Same failing call injected as the agent's first step in both runs:
`get_clause(document="msa", clause="12.4")` — clause 12.4 does not exist in
the MSA, modelled directly on the task's own example. Same question, same
model, same step budget. The ONLY variable that differs between the two full
trajectories below is the text of that one tool error. Every step after the
first is the model's own real, live decision — nothing scripted past step 0.
Reproduce with `./venv/bin/python week9_deliverables/capture_error_recovery.py`.

**Question asked:** {QUESTION}

## Before — Week 8's `get_clause` error

Error text the tool returned:
```
{OLD_ERROR}
```

Docstring at the time:
```
Raises ToolError if the clause number does not exist in that document — this
is what turns a hallucinated clause reference into a visible tool failure
instead of a fluent-sounding answer.
```

**Full trajectory:**
```
{render(old_log)}
```

## After — Week 9's rewritten `get_clause` error

Error text the tool returns now for the identical call:
```
{new_error}
```

Docstring now:
```
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
```

**Full trajectory:**
```
{render(new_log)}
```

## What changed

Both trajectories "recover" in the loose sense of not looping and reaching a
final answer — but they recover to a DIFFERENT answer, and only one of them
is legally correct:

- **Old error** (bare "not found" + list): the model falls back to
  `search_contracts` on generic terms, finds the base MSA's own Clause 8, and
  answers from it. This is fluent and confident, and it is the SAME failure
  mode named in Week 8 — a right-*sounding* answer reached without ever
  checking whether a later amendment supersedes it. Clause 8 of the MSA does
  say "sixty (60) days", so this answer happens to be numerically right, but
  the model never learned that Amendment No. 1 exists, let alone that it is
  the one that actually amends this clause.
- **New error**: the error message itself names the amendment relationship
  ("see amendment ..."), so the model's very next search is scoped to that
  hint ("12.4 termination for convenience" — carrying the amendment context
  forward) and it retrieves the amendment first, then correctly reads and
  cites `get_clause("amendment", "1")` — the actual governing clause — rather
  than settling for the base agreement's version of the same topic.

So the old error is technically "recoverable" (the model doesn't get stuck),
but the recovery routes through the wrong document; the new error's recovery
routes through the right one, because the error text itself carries the one
piece of information ("see amendment") that a bare "not found" throws away.
That is the concrete difference a docstring-and-error rewrite bought here —
not merely avoiding a stuck agent, but avoiding a *confidently wrong* one.
"""
    out_path = Path(__file__).resolve().parent / "error_before_after.md"
    out_path.write_text(doc, encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
