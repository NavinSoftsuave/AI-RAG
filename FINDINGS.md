# Week 4 · M2 — Debugging Retrieval: Findings

**Task:** Label failing questions as *wrong document fetched* vs *right document,
wrong answer*; make **one** change; prove it bought back **hit-rate@3** with a
before/after number; and note what the change did **not** fix.

**The one change:** added **hybrid search** — keyword search (BM25) fused with the
existing semantic search using **Reciprocal Rank Fusion (RRF)**. Nothing else was
changed, so any movement in the number is attributable to this alone.

**How to reproduce**

```bash
./venv/bin/python -m eval.run_eval
```

This ingests the evaluation corpus, runs all 15 questions through retrieval twice
(semantic-only = *before*, hybrid = *after*), and prints the numbers, the failure
labels, and what the change did / did not fix.

---

## The dataset

15 questions over a 10-document corpus (`docs/eval_corpus/`). Five documents are
the originals; five are **distractors** added on purpose (a *travel* insurance
policy, a *contractor* leave policy, a device-credentials sheet, an error-code
catalog, a vendor return policy). The distractors share vocabulary with the
originals — "deductible", "annual coverage limit", "maternity leave", other
`ERR-xxxx` codes, other `xxx@123` passwords — so retrieval has to distinguish
*which* document, not just *which topic*. Ground truth (which document actually
answers each question) lives in `eval/dataset.py`.

Documents are chunked small (~120 chars) so each fact is its own vector and
competes against the look-alike distractor facts — the realistic condition under
which semantic search starts picking the wrong document.

**One distractor is deliberately large.** The IT error-code catalog
(`it_error_catalog.txt`) holds ~18 look-alike `ERR-xxxx` entries plus a block of
generic "account locked after failed login attempts" prose. That volume of
semantically near-identical text is what pushes a gold answer *out of the top-3*
under semantic-only search — creating a real **@3** failure to buy back, not just
an @1 one.

---

## The two kinds of failure

- **Wrong document fetched (retrieval failure).** The document that answers the
  question never reaches the top of the results. A smarter LLM cannot fix this —
  it never sees the right text. Fix retrieval.
- **Right document, wrong answer (generation failure).** The right document *is*
  retrieved, but the answer is still wrong. Fix the prompt/model, not retrieval.

The harness labels each miss automatically and prints the evidence (what it wanted,
what it got at rank 1, where the gold document actually ranked, and the offending
chunk text). Every failure on this dataset is the **retrieval** kind.

---

## The number (before → after)

| Metric       | Before (semantic) | After (hybrid) | Δ         |
|--------------|-------------------|----------------|-----------|
| **hit-rate@3** | **0.933 (93%)**  | **1.000 (100%)** | **+0.067** |
| hit-rate@1   | 0.600 (60%)       | 0.667 (67%)    | +0.067    |
| MRR          | 0.780             | 0.822          | +0.042    |

**The headline buy-back is at hit-rate@3 (93% → 100%).** It is driven by one
question:

> *"What happens after five failed login attempts?"*

Under semantic-only the gold document (`it_support_guide.txt`) sits at **rank 5** —
buried below five near-identical "account locked" chunks from the error-code
catalog, so it misses the top-3. Hybrid lifts it to **rank 3**, back inside the
window. hit-rate@1 and MRR move by the same lift, confirming the same story from
two other angles.

---

## Why hybrid fixed exactly this one — with evidence

The gold chunk is the only one in the whole corpus that contains the exact word
**"five"** ("locked after **five** failed login attempts"). The distractor catalog
only ever says "repeated" / "too many" / "several". So:

- **Semantic** blurs "five failed login attempts" into the general *idea* of an
  account lockout, and the catalog's many lockout chunks win on meaning → gold
  drops to rank 5.
- **BM25** keys on the literal token `five` and ranks the gold chunk **#1**
  (BM25 score 8.31 vs the next chunk's 8.22).
- **RRF** fuses the two lists; the gold chunk ranks well in the keyword list and
  modestly in the semantic list, so it floats to **rank 3** — a top-3 hit.

This is the exact case hybrid is *for*: an answer that hinges on an **exact term
the distractor lacks**, which meaning-based search alone cannot separate.

---

## What the change did NOT fix (4 still failing at rank 1)

Hybrid bought back @3 but left four rank-1 misses in place:

| Question | Wanted | Got at rank 1 | Gold rank (hybrid) |
|---|---|---|---|
| How many weeks of maternity leave…? | employee_leave_policy | contractor_leave_terms | 2 |
| What is the deductible amount per claim? | insurance_policy | travel_insurance_policy | 2 |
| What is the annual coverage limit? | insurance_policy | travel_insurance_policy | 2 |
| How much insurance coverage is provided annually? | insurance_policy | travel_insurance_policy | 2 |

**Why hybrid can't fix these:** the distractor document contains the *same*
keywords as the gold document ("deductible", "annual coverage limit", "maternity
leave"). BM25 sees an equal keyword match in both, so it can't break the tie
either — and the wrong document keeps rank 1. This is the honest limit of hybrid:
it helps when the right document has a **distinctive** term the distractor lacks
(the "five" case above); it does **not** help when both documents share the
vocabulary.

The right next step for these (a *second, separate* experiment) would be a
**cross-encoder reranker**, which reads the query and chunk together and can tell
"health policy" from "travel policy" where bag-of-words cannot.

**Newly broken by hybrid: 0.** The change regressed nothing.

---

## Files

- `eval/dataset.py` — 15 questions + ground-truth document for each.
- `eval/metrics.py` — hit-rate@k, recall@k, MRR.
- `eval/run_eval.py` — the before/after harness (run this).
- `rag/store.py` — the one change: `search(..., mode="semantic"|"hybrid")`, BM25 +
  RRF fusion.
- `app.py` — inspection view (question | retrieved chunks | final answer) with a
  semantic/hybrid toggle to demo the difference live.
- `docs/eval_corpus/` — the 10 documents (5 original + 5 distractors), with the IT
  error-code catalog enlarged so the @3 failure is real.
