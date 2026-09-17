"""The regression check: per-mode counts before vs after, honestly.

A mitigation that drops your top mode while quietly creating a new one is not a
win, it is a trade you did not notice. This compares every mode in the taxonomy
across two arms — including modes that were zero in both, so "we checked it" is
visible rather than assumed — and names anything that got worse or appeared.

    ./venv/bin/python -m agent.regression baseline mitigated
"""

import json
import sys
from pathlib import Path

from .scoring import MODES

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def load(arm: str) -> dict:
    path = RUNS_DIR / f"{arm}.json"
    if not path.exists():
        raise SystemExit(f"no run recorded for arm {arm!r} — run the eval first")
    return json.loads(path.read_text(encoding="utf-8"))


def compare(before: dict, after: dict) -> dict:
    b, a = before["summary"], after["summary"]
    rows = []
    worsened, appeared = [], []
    for m in MODES:
        bc = b["mode_counts"].get(m, 0)
        ac = a["mode_counts"].get(m, 0)
        delta = ac - bc
        if delta > 0:
            (appeared if bc == 0 else worsened).append(f"{m} ({bc}->{ac})")
        rows.append({"mode": m, "before": bc, "after": ac, "delta": delta})

    # Per-case trajectory regressions: passed before, fails now.
    b_cases = {c["case"]: c["score"] for c in before["cases"]}
    regressed_cases = [
        c["case"] for c in after["cases"]
        if b_cases.get(c["case"], {}).get("trajectory_pass") and not c["score"]["trajectory_pass"]
    ]
    return {
        "rows": rows,
        "worsened": worsened,
        "appeared": appeared,
        "regressed_cases": regressed_cases,
        "checked": MODES,
        "price": {
            "cost_p50": (b["cost_p50"], a["cost_p50"]),
            "cost_max": (b["cost_max"], a["cost_max"]),
            "latency_p50": (b["latency_p50"], a["latency_p50"]),
            "latency_max": (b["latency_max"], a["latency_max"]),
            "steps_total": (
                sum(c["score"]["steps_taken"] for c in before["cases"]),
                sum(c["score"]["steps_taken"] for c in after["cases"]),
            ),
        },
        "rates": {
            "outcome": (b["outcome_pass_rate"], a["outcome_pass_rate"]),
            "trajectory": (b["trajectory_pass_rate"], a["trajectory_pass_rate"]),
            "gap": (b["gap"], a["gap"]),
        },
    }


def main() -> None:
    before_arm = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    after_arm = sys.argv[2] if len(sys.argv) > 2 else "mitigated"
    result = compare(load(before_arm), load(after_arm))

    print(f"\n=== per-mode regression: {before_arm} -> {after_arm} ===\n")
    print(f"| {'mode':<24} | before | after | delta |")
    print(f"|{'-'*26}|--------|-------|-------|")
    for r in result["rows"]:
        mark = "  <-- WORSE" if r["delta"] > 0 else ""
        print(f"| {r['mode']:<24} | {r['before']:^6} | {r['after']:^5} | {r['delta']:+d}    |{mark}")

    print("\nmodes checked:", len(result["checked"]))
    print("worsened     :", ", ".join(result["worsened"]) or "none")
    print("newly appeared:", ", ".join(result["appeared"]) or "none")
    print("cases that regressed on trajectory:",
          ", ".join(result["regressed_cases"]) or "none")

    p = result["price"]
    print("\n=== price paid ===")
    print(f"cost p50  : ${p['cost_p50'][0]:.5f} -> ${p['cost_p50'][1]:.5f} "
          f"({(p['cost_p50'][1]-p['cost_p50'][0])/max(p['cost_p50'][0],1e-9):+.1%})")
    print(f"cost max  : ${p['cost_max'][0]:.5f} -> ${p['cost_max'][1]:.5f} "
          f"({(p['cost_max'][1]-p['cost_max'][0])/max(p['cost_max'][0],1e-9):+.1%})")
    print(f"latency p50: {p['latency_p50'][0]:.0f} -> {p['latency_p50'][1]:.0f} ms")
    print(f"steps total: {p['steps_total'][0]} -> {p['steps_total'][1]}")

    r = result["rates"]
    print("\n=== rates ===")
    print(f"outcome pass    : {r['outcome'][0]:.0%} -> {r['outcome'][1]:.0%}")
    print(f"trajectory pass : {r['trajectory'][0]:.0%} -> {r['trajectory'][1]:.0%}")
    print(f"gap             : {r['gap'][0]:.0%} -> {r['gap'][1]:.0%}")

    (RUNS_DIR / f"regression_{before_arm}_to_{after_arm}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
