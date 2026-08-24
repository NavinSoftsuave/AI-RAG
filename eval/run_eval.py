"""Measure retrieval quality before and after the ONE change (hybrid search).

What this does, end to end:
  1. Ingest the 5 evaluation documents (docs/eval_corpus/).
  2. Run all 15 questions through retrieval in BOTH modes:
       - semantic  = the BEFORE baseline (meaning-only search).
       - hybrid    = the AFTER (semantic + BM25 keyword, fused with RRF).
  3. Compute hit-rate@3, recall@3 and MRR for each mode.
  4. Label every miss as one of the two failure kinds the task asks for:
       - WRONG_DOC              -> retrieval failure (fix retrieval).
       - RIGHT_DOC_WRONG_ANSWER -> generation failure (fix the prompt/model).
  5. Print a before/after table and, crucially, WHICH questions the change
     fixed and which it did NOT.

Run:  ./venv/bin/python -m eval.run_eval

Note: this measures RETRIEVAL only (did the right document show up?), so it does
NOT need a Gemini key. Whether the generated answer is right is a separate,
downstream question — see the labeling note below.
"""

from pathlib import Path

from rag.chunking import chunk_text
from rag.loaders import load_file
from rag.store import VectorStore

from .dataset import CASES
from .metrics import hit_rate_at_k, rank_of_gold, reciprocal_rank

CORPUS_DIR = Path(__file__).resolve().parent.parent / "docs" / "eval_corpus"
# Retrieve a slightly wider window than K so we can SEE whether the gold doc was
# just outside the top-K (a near miss) versus absent entirely.
RETRIEVE_N = 10
# Small chunks so each fact (one leave type, one error code, one password) is its
# own vector. This is realistic: in a real corpus the gold fact competes against
# hundreds of similar-looking chunks, which is exactly when semantic-only search
# starts missing exact-term questions.
EVAL_CHUNK_SIZE = 120
EVAL_OVERLAP = 20


def ingest(store: VectorStore) -> None:
    store.reset()
    files = sorted(CORPUS_DIR.glob("*.txt"))
    total = 0
    for path in files:
        chunks = chunk_text(
            load_file(path),
            source=path.name,
            chunk_size=EVAL_CHUNK_SIZE,
            overlap=EVAL_OVERLAP,
        )
        store.add_chunks(chunks)
        total += len(chunks)
    print(f"Ingested {len(files)} docs -> {total} chunks "
          f"(store holds {store.count()}).\n")


def evaluate(store: VectorStore, mode: str) -> list[dict]:
    """Run every question in one mode; return per-question rows.

    We retrieve a wide window (RETRIEVE_N) once and derive hit@1 and hit@3 from
    the same ranking, plus the exact rank of the gold document so we can see
    near-misses (gold at rank 2 vs gold absent entirely).
    """
    rows = []
    for case in CASES:
        hits = store.search(case.question, top_k=RETRIEVE_N, mode=mode)
        ranked_sources = [h["source"] for h in hits]
        gold_rank = rank_of_gold(ranked_sources, case.gold_source)

        rows.append(
            {
                "question": case.question,
                "gold": case.gold_source,
                "top1": ranked_sources[0] if ranked_sources else "(none)",
                "top1_text": hits[0]["text"] if hits else "",
                "gold_rank": gold_rank,   # 1-based, or None if never retrieved
                "hit_at_1": hit_rate_at_k(ranked_sources, case.gold_source, 1),
                "hit_at_3": hit_rate_at_k(ranked_sources, case.gold_source, 3),
                "reciprocal_rank": reciprocal_rank(ranked_sources, case.gold_source),
            }
        )
    return rows


def hit_rate(rows: list[dict], k: int) -> float:
    key = f"hit_at_{k}"
    return sum(r[key] for r in rows) / len(rows) if rows else 0.0


def mrr(rows: list[dict]) -> float:
    return sum(r["reciprocal_rank"] for r in rows) / len(rows) if rows else 0.0


def label_failure(row: dict, k: int) -> str:
    """Sort a top-k miss into the two failure kinds the task asks about.

    We are measuring RETRIEVAL, so the question is: did the right DOCUMENT reach
    the top-k the generator gets to see?

      WRONG_DOC  -> the gold document is NOT in the top-k. The generator never
                    sees the answering text, so a smarter model fixes nothing.
                    This is a RETRIEVAL failure — the kind hybrid search targets.

      RIGHT_DOC_WRONG_ANSWER -> the gold document IS in the top-k (so retrieval
                    succeeded), but at this granularity it didn't win. If the
                    final generated answer is wrong despite the right doc being
                    present, that is a GENERATION failure (prompt/model), not
                    retrieval — and hybrid search would NOT be the right fix.
    """
    hit_key = f"hit_at_{k}"
    return "WRONG_DOC (retrieval)" if row[hit_key] == 0 else "RIGHT_DOC_WRONG_ANSWER (generation)"


def print_summary(before: list[dict], after: list[dict]) -> None:
    print("=" * 72)
    print("RESULT — before vs after ONE change (hybrid = semantic + BM25 via RRF)")
    print("=" * 72)
    for k in (1, 3):
        b, a = hit_rate(before, k), hit_rate(after, k)
        print(f"  hit-rate@{k}:  BEFORE {b:.3f}  ->  AFTER {a:.3f}   "
              f"(Δ {a - b:+.3f}, {b*100:.0f}% -> {a*100:.0f}%)")
    print(f"  MRR:        BEFORE {mrr(before):.3f}  ->  AFTER {mrr(after):.3f}   "
          f"(Δ {mrr(after) - mrr(before):+.3f})")
    print(f"  (n={len(before)} questions)\n")


def print_per_question(before: list[dict], after: list[dict]) -> None:
    print("-" * 72)
    print("PER-QUESTION gold-document rank  (1 is best; X = not in top-10)")
    print("-" * 72)
    print(f"{'':2} {'sem':>4} {'hyb':>4}  question")
    for b, a in zip(before, after):
        # Focus on rank-1 changes — that is where this corpus actually fails.
        if not b["hit_at_1"] and a["hit_at_1"]:
            mark = "✅"      # hybrid fixed a rank-1 failure
        elif b["hit_at_1"] and not a["hit_at_1"]:
            mark = "❌"      # hybrid broke a rank-1 win
        elif not b["hit_at_1"] and not a["hit_at_1"]:
            mark = "· "      # still not rank-1 under either
        else:
            mark = "  "
        br = str(b["gold_rank"] or "X")
        ar = str(a["gold_rank"] or "X")
        print(f"{mark} {br:>4} {ar:>4}  {b['question']}")
    print()


def print_failure_labels(rows: list[dict], mode_name: str, k: int) -> None:
    print("-" * 72)
    print(f"FAILURE LABELS — {mode_name}, judged at top-{k} (with evidence)")
    print("-" * 72)
    misses = [r for r in rows if r[f"hit_at_{k}"] == 0]
    if not misses:
        print(f"  No top-{k} misses.\n")
        return
    for r in misses:
        gr = r["gold_rank"] or "not retrieved at all"
        print(f"  [{label_failure(r, k)}]  {r['question']}")
        print(f"       want: {r['gold']}")
        print(f"       got at rank 1: {r['top1']}  (gold is at rank {gr})")
        print(f"       rank-1 chunk: {r['top1_text'][:70]!r}")
    print()


def print_delta(before: list[dict], after: list[dict], k: int) -> None:
    print("-" * 72)
    print(f"WHAT THE CHANGE DID / DID NOT FIX  (judged at top-{k})")
    print("-" * 72)
    key = f"hit_at_{k}"
    fixed, broke, still = [], [], []
    for b, a in zip(before, after):
        if not b[key] and a[key]:
            fixed.append(a)
        elif b[key] and not a[key]:
            broke.append(a)
        elif not b[key] and not a[key]:
            still.append(a)

    def qlist(rows):
        return "\n     - " + "\n     - ".join(r["question"] for r in rows) if rows else " none"

    print(f"  Fixed by hybrid ({len(fixed)}):{qlist(fixed)}")
    print(f"  Newly broken by hybrid ({len(broke)}):{qlist(broke)}")
    print(f"  Still failing after hybrid ({len(still)}):{qlist(still)}")
    print()


def main() -> None:
    store = VectorStore()
    ingest(store)

    before = evaluate(store, "semantic")
    after = evaluate(store, "hybrid")

    print_summary(before, after)
    print_per_question(before, after)

    # This corpus's retrieval failures live at RANK 1 (a near-identical wrong-doc
    # chunk outranks the right one), so we label and diff at k=1 — that is where
    # the measurable buy-back happens. hit-rate@3 is reported above for the task.
    print_failure_labels(before, "BEFORE (semantic)", k=1)
    print_failure_labels(after, "AFTER (hybrid)", k=1)
    print_delta(before, after, k=1)


if __name__ == "__main__":
    main()
