"""trajectory_eval.py — score the contract agent's PATH, not just its answer.

Run:
    ./venv/bin/python -m agent.trajectory_eval                 # baseline
    ./venv/bin/python -m agent.trajectory_eval --arm mitigated # after the fix
    ./venv/bin/python -m agent.trajectory_eval --report        # print the report

Every run writes its per-case trajectories and scores to runs/<arm>.json so the
before -> after comparison is made from recorded data, never from memory.
"""

import argparse
import json
from pathlib import Path

from rag.store import VectorStore

from .cases import CASES
from .contract_agent import run_agent, trajectory_to_dict
from .mitigation import ARMS
from .scoring import MODES, aggregate, score

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def run_arm(arm: str = "baseline") -> dict:
    """Run all 10 cases under one arm and persist the trajectories + scores."""
    if arm not in ARMS:
        raise SystemExit(f"unknown arm {arm!r}; choose from {sorted(ARMS)}")
    config = ARMS[arm]
    store = VectorStore()

    records = []
    scores = []
    for case in CASES:
        traj = run_agent(
            case.question, store, case_id=case.id,
            max_steps=config.get("max_steps", 8),
            system=config.get("system"),
            tool_spec=config.get("tool_spec"),
            sanitize=config.get("sanitize"),
            output_guardrail=config.get("output_guardrail"),
        )
        s = score(traj, case)
        scores.append(s)
        records.append({
            "case": case.id,
            "mode": case.mode,
            "question": case.question,
            "trajectory": trajectory_to_dict(traj),
            "score": s.__dict__,
        })

    summary = aggregate(scores)
    out = {"arm": arm, "summary": summary, "cases": records}
    RUNS_DIR.mkdir(exist_ok=True)
    (RUNS_DIR / f"{arm}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def _fmt_table(rows: list[list[str]], head: list[str]) -> str:
    widths = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(head)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    body = ["| " + " | ".join(str(r[i]).ljust(widths[i]) for i in range(len(head))) + " |"
            for r in rows]
    return "\n".join([line, sep] + body)


def print_arm(out: dict) -> None:
    s = out["summary"]
    inc = s.get("incomplete", [])
    print(f"\n=== ARM: {out['arm']} ({s['n']} cases scored"
          + (f", {len(inc)} not run) ===" if inc else ") ==="))
    if inc:
        print(f"    not run (daily API budget exhausted): {', '.join(inc)}\n")
    else:
        print()
    rows = []
    for c in out["cases"]:
        sc = c["score"]
        if not sc.get("complete", True):
            rows.append([c["case"], sc["mode"], "-", "-", "-", "-", "-", "-",
                         "-", "NOT RUN (no API budget)"])
            continue
        rows.append([
            c["case"], sc["mode"],
            "PASS" if sc["outcome_pass"] else "FAIL",
            "PASS" if sc["trajectory_pass"] else "FAIL",
            f"{sc['tool_choice_accuracy']:.2f}",
            f"{sc['argument_validity']:.2f}",
            f"{sc['step_efficiency']:.2f}",
            f"{sc['steps_taken']}/{sc['steps_needed']}",
            f"{sc['cost_usd']:.5f}",
            ",".join(sc["failure_modes"]) or "-",
        ])
    print(_fmt_table(rows, ["case", "mode", "outcome", "traj", "tool-acc",
                            "arg-val", "step-eff", "steps", "cost$", "modes"]))
    print(f"\ntool-choice accuracy : {s['tool_choice_accuracy']:.3f}")
    print(f"argument validity    : {s['argument_validity']:.3f}")
    print(f"step efficiency      : {s['step_efficiency']:.3f}")
    print(f"cost per question    : p50 ${s['cost_p50']:.5f}  max ${s['cost_max']:.5f}"
          f"   (mean ${s['cost_mean']:.5f} — shown only to prove it hides the max)")
    print(f"latency per question : p50 {s['latency_p50']:.0f} ms  max {s['latency_max']:.0f} ms")
    print(f"\noutcome pass rate    : {s['outcome_pass_rate']:.0%}")
    print(f"trajectory pass rate : {s['trajectory_pass_rate']:.0%}")
    print(f"OUTCOME-TRAJECTORY GAP: {s['gap']:.0%}")
    print("\nfailure modes:")
    for m in MODES:
        print(f"  {m:24} {s['mode_counts'].get(m, 0)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="baseline", choices=sorted(ARMS))
    ap.add_argument("--all", action="store_true", help="run every arm in order")
    args = ap.parse_args()

    arms = sorted(ARMS) if args.all else [args.arm]
    for arm in arms:
        print_arm(run_arm(arm))


if __name__ == "__main__":
    main()
