# Week 5 · M3 — Error Analysis: Reading Traces (Track F, Legal Contracts)

**Deliverable:** ~20 real traces read, one honest note per failure (written before
grouping), grouped into named problem types, ranked by frequency × severity, with
one chosen fix target and a written prediction.

**How the traces were produced (fair, not cherry-picked):** a fixed set of 24
legal questions (`eval/questions_legal.py`) spanning lookups, exact values,
cross-document conflicts, multi-doc, out-of-scope, and ambiguous phrasing, run
through the real app pipeline (hybrid retrieval + Gemini generation) and captured
verbatim to `traces/legal_traces.jsonl`. Every question written up-front was run;
none were dropped. Reproduce: `./venv/bin/python -m eval.run_traces`, read with
`./venv/bin/python -m eval.show_traces`.

**Headline:** 12 answered / 12 refused out of 24. Many refusals are **false
refusals** — the correct clause was retrieved and the app still said "I don't
know."

---

## 1. Open-coded notes (one honest sentence per failure, written before grouping)

Only the failing/weak traces are noted. Answered-correctly traces (1, 5, 7, 8, 9,
10, 15, 16, 17, 18, 23) are omitted here.

- **T2 — "What law governs the MSA?"** → REFUSED. The MSA chunk *and* an NDA
  governing-law chunk were retrieved; the model refused instead of reading
  Delaware off the text. **False refusal on a plainly answerable question.**
- **T3 — "How long does confidentiality survive termination of the MSA?"** →
  REFUSED. The MSA confidentiality chunk (rank 1) literally contains "five (5)
  years". **False refusal; answer was in the top chunk.**
- **T4 — "Limitation of liability under the MSA?"** → REFUSED. MSA clause 7 was
  rank 1. **False refusal; answer present.**
- **T6 — "Late payment interest rate in the MSA?"** → REFUSED. The MSA fees chunk
  (1.5%/month) was retrieved at rank 2; the amendment's payment chunk outranked
  it. **False refusal; the number was retrieved but not surfaced.**
- **T11 — "Days to pay an undisputed invoice?"** → REFUSED. Both the MSA (30 days)
  and the amendment (45 days) chunks were retrieved; the model refused rather than
  resolve the conflict. **False refusal on a conflict it should have handled.**
- **T12 — "Current payment terms with Globex?"** → REFUSED. The amended 45-day
  term was rank 1. **False refusal; the governing (amended) value was right there.**
- **T14 — "Governing-law states across all contracts?"** → REFUSED. Retrieval
  pulled the wrong chunks (IP, entire-agreement, warranties) — the governing-law
  clauses were NOT retrieved. **Genuine retrieval miss on a multi-doc question.**
- **T22 — "Termination notice period?" (ambiguous)** → REFUSED. Ambiguous across
  three contracts; refusing is defensible but a *scoped* answer ("depends on which
  contract; here they are…") would be better. **Weak, not wrong.**
- **T24 — "Is the agreement still valid?" (ambiguous)** → REFUSED. Genuinely
  under-specified; refusing is the correct, safe behaviour. **Not a failure.**

Two answered traces are worth a note:
- **T13 — "Which agreements contain a confidentiality clause?"** → ANSWERED but
  imprecise: it cited the NDA's "Section 4. TERM" as the confidentiality source
  when the NDA's confidentiality lives in clause 3 (Obligations). **Right docs,
  slightly wrong clause citation.**
- **T23 — "What happens if payment is late?"** → ANSWERED well, correctly scoped
  per contract. Model example of the good behaviour T22 lacked.

---

## 2. Named problem types (a stranger would understand these)

| # | Problem name | What it is | Trace IDs |
|---|---|---|---|
| **P1** | **False refusal (right chunk, "I don't know")** | The answering clause is retrieved in the top-k, but the model refuses anyway. | T2, T3, T4, T6, T11, T12 |
| **P2** | **Conflict not resolved** | Both the base clause and its amendment are retrieved; the model refuses instead of stating the governing (amended) value. | T11, T12 |
| **P3** | **Multi-doc retrieval miss** | A question needing one fact from each of several contracts retrieves the wrong chunks; the answering clauses never reach the model. | T14 |
| **P4** | **Weak-but-safe on ambiguous** | For under-specified questions the app refuses outright instead of scoping ("depends which contract; here they are"). | T22 |
| **P5** | **Imprecise citation** | Right documents, but the cited clause number/heading is wrong. | T13 |

(P2 overlaps P1 — the two conflict cases are *also* false refusals — but P2 is
called out separately because its fix is different: it needs conflict-handling in
the prompt, not just permission to answer.)

---

## 3. Ranking (frequency × severity)

Severity for a **legal** app: a false refusal wastes the lawyer's time (medium);
a confidently *wrong* answer about a right/obligation is dangerous (high); a
missed retrieval is invisible and unfixable by the model (high).

| Rank | Problem | Frequency | Severity | Why this rank |
|---|---|---|---|---|
| **1** | **P1 False refusal** | 6/24 (25%) | Medium–High | Most frequent by far; makes the app look broken on trivially answerable questions and erodes trust. Cheapest to fix (prompt). |
| **2** | **P2 Conflict not resolved** | 2/24 | High | Low frequency but high stakes — reporting a superseded term (or none) about payment/termination is exactly the "unsupported claim about a termination right" the brief warns about. |
| **3** | **P3 Multi-doc retrieval miss** | 1/24 | High | Model can't fix it (text never retrieved); needs a retrieval change. Rare here but structurally serious. |
| **4** | **P4 Weak-but-safe ambiguous** | 1/24 | Low | Refusing is defensible; upgrading to a scoped answer is polish. |
| **5** | **P5 Imprecise citation** | 1/24 | Low–Medium | Right substance, wrong pin-cite; matters for a legal audience but the answer isn't wrong. |

---

## 4. Chosen fix target + written prediction

**Target: P1 — False refusal (right chunk, "I don't know").**
It is the most frequent problem (6/24), it directly undermines trust, and the
evidence points at a single cause: the generation prompt in `rag/llm.py` is
*over-strict*. It says "If ONLY PART of the question can be answered, respond: I
don't know" and repeats "I don't know" instructions three times, pushing the model
to refuse whenever the retrieved context isn't a perfect, self-contained match —
even when the answer is plainly present (T2's Delaware, T3's five years).

**Prediction (written before the fix):** Softening the prompt — remove the
"answer only if the WHOLE question is covered" rule and the redundant refusal
instructions, keep one clear "refuse only if the answer is truly absent" rule —
will convert most of the six false refusals (T2, T3, T4, T6) into correct answers,
**without** turning the genuine out-of-scope refusals (T19, T20, T21) into
hallucinations. I expect the conflict cases (T11, T12) to *partially* improve but
maybe not fully, because resolving base-vs-amendment needs more than permission to
answer. I do **not** expect P3 (T14) to change — that is a retrieval miss the
prompt can't touch.

*(This prediction is scored against the actual outcome in the Week 6 work, where
the prompt change becomes a measured before/after.)*
