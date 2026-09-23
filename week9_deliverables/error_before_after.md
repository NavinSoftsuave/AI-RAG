# error_before_after.md — Week 9 requirement 5

Same failing call injected as the agent's first step in both runs:
`get_clause(document="msa", clause="12.4")` — clause 12.4 does not exist in
the MSA, modelled directly on the task's own example. Same question, same
model, same step budget. The ONLY variable that differs between the two full
trajectories below is the text of that one tool error. Every step after the
first is the model's own real, live decision — nothing scripted past step 0.
Reproduce with `./venv/bin/python week9_deliverables/capture_error_recovery.py`.

**Question asked:** What does clause 12.4 of the Master Services Agreement say about termination for convenience?

## Before — Week 8's `get_clause` error

Error text the tool returned:
```
clause '12.4' does not exist in 'msa'; available clauses: ['1', '10', '11', '2', '3', '4', '5', '6', '7', '8', '9']
```

Docstring at the time:
```
Raises ToolError if the clause number does not exist in that document — this
is what turns a hallucinated clause reference into a visible tool failure
instead of a fluent-sounding answer.
```

**Full trajectory:**
```
[step 0] get_clause({"document": "msa", "clause": "12.4"}) ok=False
    -> TOOL ERROR: clause '12.4' does not exist in 'msa'; available clauses: ['1', '10', '11', '2', '3', '4', '5', '6', '7', '8', '9']
[step 1] search_contracts({"query": "termination for convenience Master Services Agreement"}) ok=True
    -> [1] sample_service_agreement.pdf (chunk 8)
8. TERMINATION Either party may terminate this Agreement for convenience upon sixty (60) days' prior written notice. Either party may terminate immediately upon written notice i
[step 2] get_clause({"clause": "8", "document": "msa"}) ok=True
    -> Master Services Agreement (Acme Corp / Globex Ltd), dated January 15, 2025
Clause 8. TERMINATION Either party may terminate this Agreement for co

8. TERMINATION Either party may terminate this Agreement for convenience 
[step 3] FINAL ANSWER: Clause 12.4 does not exist in the Master Services Agreement (the agreement only contains Clauses 1 through 11). Termination for convenience is instead governed by Clause 8 of the Master Services Agreement, which states: "Either party may terminate this Agreement for convenience upon sixty (60) days' prior written notice."
```

## After — Week 9's rewritten `get_clause` error

Error text the tool returns now for the identical call:
```
no clause '12.4' in Master Services Agreement (Acme Corp / Globex Ltd), dated January 15, 2025 — clauses run 1-11; see amendment (Amendment No. 1 to the Master Services Agreement, dated March 1, 2025)
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
[step 0] get_clause({"document": "msa", "clause": "12.4"}) ok=False
    -> TOOL ERROR: no clause '12.4' in Master Services Agreement (Acme Corp / Globex Ltd), dated January 15, 2025 — clauses run 1-11; see amendment (Amendment No. 1 to the Master Services Agreement, dated March 1, 2025)
[step 1] search_contracts({"query": "12.4 termination for convenience"}) ok=True
    -> [1] sample_amendment.txt (chunk 1)
1. TERMINATION. Either party may terminate this Agreement for convenience by providing sixty (60) days prior written notice to the other party. In the event of a material breach, the no
[step 2] get_clause({"clause": "1", "document": "amendment"}) ok=True
    -> Amendment No. 1 to the Master Services Agreement, dated March 1, 2025
Clause 1. TERMINATION. Either party may terminate this Agreement for c

1. TERMINATION. Either party may terminate this Agreement for convenience by p
[step 3] FINAL ANSWER: Clause 12.4 does not exist in the Master Services Agreement (the clauses run 1–11). However, Clause 1 of Amendment No. 1 to the Master Services Agreement provides that either party may terminate the Agreement for convenience by providing sixty (60) days prior written notice to the other party.
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
