"""One-command Week-6 eval: score every case and print pass rate BY MODE.

For each eval case it:
  1. gets the app's answer (retrieval + generation; generation is cached),
  2. runs the deterministic assertions (free, no LLM),
  3. checks the refuse/answer behaviour matches `should_answer`,
  4. runs the LLM judge on the single binary correctness criterion,
  5. a case PASSES when assertions hold, behaviour matches, and the judge says
     CORRECT.

Reporting is per-mode, never a single blended number — an average hides a
regression in one mode behind another.

Run:  ./venv/bin/python -m eval.run_eval_week6
"""

from collections import defaultdict
from pathlib import Path

from rag.answer import build_answer
from rag.chunking import chunk_text
from rag.llm import QuotaExceeded
from rag.loaders import load_file
from rag.store import VectorStore

from .assertions import run_assertions
from .evalset import CASES, modes
from .judge import judge

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
LEGAL_DOCS = [
    "sample_service_agreement.pdf", "sample_amendment.txt", "mutual_nda.txt",
    "employment_agreement.txt", "commercial_lease.txt",
]
MODE = "hybrid"
TOP_K = 4
JUDGE_VERSION = "v1"
# Use only cached judge verdicts so the eval runs offline with no quota spend.
CACHED_ONLY = True


def ingest(store: VectorStore) -> str:
    store.reset()
    corpus_parts = []
    for name in LEGAL_DOCS:
        text = load_file(DOCS_DIR / name)
        corpus_parts.append(text)
        store.add_chunks(chunk_text(text, source=name))
    return "\n".join(corpus_parts)


def main() -> None:
    store = VectorStore()
    corpus = ingest(store)

    per_mode = defaultdict(lambda: {"pass": 0, "total": 0})
    rows = []

    for case in CASES:
        hits = store.search(case.question, top_k=TOP_K, mode=MODE)
        answer = build_answer(case.question, hits)

        assertion_results = run_assertions(answer.text, corpus)
        assertions_ok = all(a.passed for a in assertion_results)
        behaviour_ok = answer.answered == case.should_answer

        context = "\n\n".join(h["text"] for h in hits)
        try:
            # cached_only: run fully offline off the LLM cache. To (re)compute
            # missing verdicts, run `python -m eval.validate_judge <version>`.
            verdict = judge(case.question, context, answer.text,
                            version=JUDGE_VERSION, cached_only=CACHED_ONLY)
            if verdict is None:
                judged_ok, judge_note = None, "(not yet judged)"
            else:
                judged_ok, judge_note = verdict.correct, verdict.reason
        except QuotaExceeded:
            judged_ok, judge_note = None, "(quota — not judged)"

        # A case is scored only once it has been judged. Un-judged cases (no
        # cached verdict yet) are counted as pending, NOT as failures — counting
        # them as fails would understate the pass rate and hide the real picture.
        if judged_ok is None:
            status = "pending"
            passed = False
        else:
            passed = assertions_ok and behaviour_ok and judged_ok
            status = "pass" if passed else "fail"
            per_mode[case.mode]["total"] += 1
            per_mode[case.mode]["pass"] += int(passed)
        rows.append((case, status, assertions_ok, behaviour_ok, judged_ok, judge_note))

    judged = sum(1 for r in rows if r[4] is not None)

    # --- report: pass rate BY MODE ---
    print("=" * 72)
    print(f"WEEK-6 EVAL — pass rate by mode (judge {JUDGE_VERSION}, n={len(CASES)}, "
          f"judged {judged}/{len(CASES)})")
    print("=" * 72)
    for m in modes():
        p, t = per_mode[m]["pass"], per_mode[m]["total"]
        rate = p / t if t else 0.0
        print(f"  {m:14s} {p:>2}/{t:<2}  {rate:5.0%}")
    total_pass = sum(v["pass"] for v in per_mode.values())
    total_scored = sum(v["total"] for v in per_mode.values())
    print("-" * 72)
    scored_rate = total_pass / total_scored if total_scored else 0.0
    print(f"  {'OVERALL':14s} {total_pass:>2}/{total_scored:<2}  {scored_rate:5.0%}  "
          f"(over judged cases)")
    if judged < len(CASES):
        print(f"  NOTE: {len(CASES) - judged} case(s) not yet judged (quota); "
              f"run `python -m eval.validate_judge {JUDGE_VERSION}` to fill.")
    print()

    # --- per-case detail ---
    for case, status, a_ok, b_ok, j_ok, note in rows:
        mark = {"pass": "PASS", "fail": "FAIL", "pending": "····"}[status]
        flags = f"assert={'ok' if a_ok else 'X'} behav={'ok' if b_ok else 'X'} judge={j_ok}"
        print(f"[{mark}] [{case.mode}] {flags}  {case.question[:52]}")


if __name__ == "__main__":
    main()
