# Week 4 · M2 — Debugging Retrieval: Findings

**Task:** Label failing questions as *wrong document fetched* vs *right document,
wrong answer*; make **one** change; prove it moved a number.

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
the originals from `RAG_Test_Documents_and_Questions.docx`; five are **distractors**
I added on purpose (a *travel* insurance policy, a *contractor* leave policy, a
device-credentials sheet, an error-code catalog, a vendor return policy). The
distractors share vocabulary with the originals — "deductible", "annual coverage
limit", "maternity leave", other `ERR-xxxx` codes, other `xxx@123` passwords — so
retrieval has to distinguish *which* document, not just *which topic*. Ground truth
(which document actually answers each question) lives in `eval/dataset.py`.

Documents are chunked small (~120 chars) so each fact is its own vector and
competes against the look-alike distractor facts — the realistic condition under
which semantic search starts picking the wrong document.

---

## The two kinds of failure

- **Wrong document fetched (retrieval failure).** The document that answers the
  question never reaches the top of the results. A smarter LLM cannot fix this —
  it never sees the right text. Fix retrieval.
- **Right document, wrong answer (generation failure).** The right document *is*
  retrieved, but the answer is still wrong. Fix the prompt/model, not retrieval.

The harness labels each miss automatically and prints the evidence (what it wanted,
what it got at rank 1, where the gold document actually ranked, and the offending
chunk text). Every failure on this dataset is the **retrieval** kind — see below.

---

## The number (before → after)

| Metric       | Before (semantic) | After (hybrid) | Δ         |
|--------------|-------------------|----------------|-----------|
| hit-rate@1   | 0.667 (67%)       | 0.733 (73%)    | **+0.067** |
| hit-rate@3   | 1.000 (100%)      | 1.000 (100%)   | +0.000    |
| MRR          | 0.833             | 0.867          | +0.033    |

**Reading this honestly:** on this corpus the gold *document* is small, so at least
one of its chunks always lands in the top 3 — **hit-rate@3 is saturated at 100% for
both modes; there is no @3 failure to buy back here.** The real retrieval failures
happen at **rank 1**: a near-identical *wrong* document outranks the right one. So
the buy-back is measured at **hit-rate@1 (67% → 73%)**, and MRR confirms the same
lift. hit-rate@3 is reported as the task specifies, with the caveat stated plainly.

---

## Failure labels, with evidence (before the change)

All five rank-1 misses are **WRONG_DOC (retrieval)** — the generator would be handed
the wrong document:

| Question | Wanted | Got at rank 1 | Gold rank |
|---|---|---|---|
| How many weeks of maternity leave…? | employee_leave_policy | **contractor_leave_terms** (12 wks) | 2 |
| Can fathers take leave after a child's birth? | employee_leave_policy | **contractor_leave_terms** | 2 |
| What is the deductible amount per claim? | insurance_policy (₹5,000) | **travel_insurance_policy** (₹2,500) | 2 |
| What is the annual coverage limit? | insurance_policy (₹5,00,000) | **travel_insurance_policy** (₹2,00,000) | 2 |
| How much insurance coverage is provided annually? | insurance_policy | **travel_insurance_policy** | 2 |

None are generation failures — retrieval is where the problem is, which is exactly
what hybrid search targets.

---

## What the change fixed — and what it did NOT

**Fixed by hybrid (1):**
- *"Can fathers take leave after a child's birth?"* — the correct employee-leave
  document moved from rank 2 to **rank 1**. Hybrid worked here because the query's
  keyword signal ("leave"/"paternity") pointed at the right document once BM25 got
  a vote.

**Still failing after hybrid (4):**
- The three insurance questions and the maternity-weeks question.
- **Why hybrid can't fix these:** the distractor document contains the *same*
  keywords as the gold document ("deductible", "annual coverage limit", "maternity
  leave"). BM25 sees an equal keyword match in both, so it can't break the tie
  either — and the wrong document keeps rank 1. This is the honest limit of hybrid:
  it helps when the right document has a **distinctive** term the distractor lacks;
  it does not help when both documents share the vocabulary.
- The right next step for these (a *second, separate* experiment) would be a
  **cross-encoder reranker**, which reads the query and chunk together and can tell
  "travel policy" from "health policy" where bag-of-words cannot.

**Newly broken by hybrid (0):** the change regressed nothing.

---

## Files

- `eval/dataset.py` — 15 questions + ground-truth document for each.
- `eval/metrics.py` — hit-rate@k, recall@k, MRR.
- `eval/run_eval.py` — the before/after harness (run this).
- `rag/store.py` — the one change: `search(..., mode="semantic"|"hybrid")`, BM25 +
  RRF fusion.
- `app.py` — inspection view (question | retrieved chunks | final answer) with a
  semantic/hybrid toggle to demo the difference live.
- `docs/eval_corpus/` — the 10 documents (5 original + 5 distractors).
