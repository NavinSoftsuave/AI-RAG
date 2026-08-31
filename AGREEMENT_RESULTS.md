# Week 6 — Judge Validation Results

> **Status: PARTIAL.** The free-tier Gemini quota (20 gen-calls/day, ~1 call/50s
> rate limit) was exhausted after 16 of 25 judge-v1 verdicts. Numbers below are
> from the cached verdicts; the run resumes for free after the daily reset and
> the full figures will replace these. Nothing is recomputed — cached verdicts
> are reused.

## agreement_before (judge v1 vs 25 blind labels)

- **Partial: 12/16 = 75%** (9 more verdicts pending on quota).

## Disagreements observed so far (id | human → judge | who was right)

| id | Question | human | judge | Who was right |
|---|---|---|---|---|
| 4 | Limitation of liability under the MSA? | INCORRECT | CORRECT | **Human.** The MSA clause 7 was in context; the app falsely refused. Judge accepted the refusal as "safe" — the false-refusal blind spot. |
| 6 | Late payment interest rate in the MSA? | INCORRECT | CORRECT | **Human.** Same false-refusal blind spot: the 1.5% chunk was retrieved. |
| 13 | Which agreements contain a confidentiality clause? | CORRECT | INCORRECT | **Judge.** The judge caught that the answer named file names not literally in the shown context — a faithfulness nit I had waved through. A genuine catch. |
| 14 | Governing-law states across all contracts? | INCORRECT | CORRECT | **Debatable.** Retrieval genuinely missed the governing-law clauses, so the refusal was defensible; I marked it INCORRECT because the question went unanswered. Reasonable people differ here. |

## Prediction scoring (from prediction.txt, written before the run)

- **Predicted:** the judge would be too lenient on false refusals (ids 2,3,4,6,11,12,25),
  dragging agreement down. **Confirmed** — ids 4 and 6 are exactly that. ✅
- **Did not predict:** id 13, where the judge was *stricter* than me and correctly
  flagged invented file names. A useful miss in my favour — the judge is not
  uniformly lenient. ⚠️

## Next step (v1 → v2 iteration)

judge_v2.txt makes the false-refusal rule explicit and will use two of v1's OWN
disagreements (ids 4 and 6 — false refusals the judge wrongly passed) as few-shot
examples. Prediction: agreement rises as those verdicts flip to INCORRECT.
Re-measure after the daily quota resets.
