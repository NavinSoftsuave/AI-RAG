"""Render captured traces as a readable worksheet for open-coding.

Prints each trace — question, retrieved chunks (source, score, snippet), and the
final answer — so every failure can be read and annotated by hand. This is the
input to the Week 5 error-analysis deliverable.

Run:  ./venv/bin/python -m eval.show_traces
"""

from .traces import TRACE_DIR, read_traces

TRACE_PATH = TRACE_DIR / "legal_traces.jsonl"


def main() -> None:
    traces = read_traces(TRACE_PATH)
    print(f"# {len(traces)} traces from {TRACE_PATH.name}\n")
    for t in traces:
        status = "ANSWERED" if t["answered"] else "REFUSED"
        print("=" * 78)
        print(f"TRACE {t['id']:>2}  [{t['kind']}]  ({status}, top_score={t['top_score']})")
        print(f"Q: {t['question']}")
        print(f"Expected: {t['expected']}")
        print("-" * 78)
        print("Retrieved:")
        for c in t["retrieved"]:
            snippet = c["text"][:80].replace("\n", " ")
            print(f"  #{c['rank']} {c['source']:32s} score={c['score']:.4f}  {snippet!r}")
        print("-" * 78)
        print("Answer:")
        for line in t["answer"].splitlines():
            print(f"  {line}")
        print()


if __name__ == "__main__":
    main()
