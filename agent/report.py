"""Render WEEK8_TRAJECTORY_EVAL.md from the recorded runs. No numbers typed by hand.

    ./venv/bin/python -m agent.report
"""

import json
from pathlib import Path

from .cases import CASES
from .regression import compare, load
from .scoring import MODES

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _case_rows(run: dict) -> str:
    head = ("| case | mode | outcome | trajectory | tool-choice | arg-valid | "
            "step-eff | steps (taken/needed) | cost $ | failure modes |")
    sep = "|" + "---|" * 10
    lines = [head, sep]
    for c in run["cases"]:
        s = c["score"]
        lines.append(
            f"| {c['case']} | {s['mode']} | "
            f"{'PASS' if s['outcome_pass'] else 'FAIL'} | "
            f"{'PASS' if s['trajectory_pass'] else '**FAIL**'} | "
            f"{s['tool_choice_accuracy']:.2f} | {s['argument_validity']:.2f} | "
            f"{s['step_efficiency']:.2f} | {s['steps_taken']}/{s['steps_needed']} | "
            f"{s['cost_usd']:.5f} | {', '.join(s['failure_modes']) or '—'} |"
        )
    return "\n".join(lines)


def _expected_paths_table() -> str:
    lines = ["| # | case | alt-path? | accepted sequences | required tools |",
             "|---|---|---|---|---|"]
    for i, c in enumerate(CASES, start=1):
        paths = "<br>".join(" → ".join(p) for p in c.expected_paths)
        alt = f"**yes** — {c.alt_reason}" if c.alt_path else "no (single path)"
        req = ", ".join(c.required_tools) or "—"
        lines.append(f"| {i} | `{c.id}`<br>{c.question} | {alt} | {paths} | {req} |")
    return "\n".join(lines)


def _gap_case(run: dict) -> dict | None:
    """The headline case: outcome PASS, trajectory FAIL."""
    for c in run["cases"]:
        if c["score"]["outcome_pass"] and not c["score"]["trajectory_pass"]:
            return c
    return None


def main() -> None:
    before = load("baseline")
    after_path = RUNS / "mitigated.json"
    after = load("mitigated") if after_path.exists() else None

    b = before["summary"]
    out = ["# Week 8 · Task Set F — Contract agent: outcome-vs-trajectory gap",
           "",
           "All numbers in this document are read from `runs/*.json`, written by",
           "`agent/trajectory_eval.py`. Nothing here is typed by hand.",
           "",
           "## 1. The 10 expected tool sequences",
           "",
           f"{len([c for c in CASES if c.alt_path])} of 10 cases legitimately accept more than one "
           "path and are asserted as a SET of sequences, not one sequence.",
           "",
           _expected_paths_table(),
           "",
           "## 2. Baseline results",
           "",
           _case_rows(before),
           "",
           "### The four trajectory numbers",
           "",
           "| metric | value |",
           "|---|---|",
           f"| tool-choice accuracy | {b['tool_choice_accuracy']:.3f} |",
           f"| argument validity | {b['argument_validity']:.3f} |",
           f"| step efficiency (needed/taken) | {b['step_efficiency']:.3f} |",
           f"| cost per question — **p50** | ${b['cost_p50']:.5f} |",
           f"| cost per question — **max** | ${b['cost_max']:.5f} |",
           f"| (mean, shown only to prove it hides the max) | ${b['cost_mean']:.5f} |",
           f"| latency p50 / max | {b['latency_p50']:.0f} ms / {b['latency_max']:.0f} ms "
           "(cache hits — not a real-call figure; see note below) |",
           "",
           "> **Note on cost and latency.** The free-tier daily quota for the "
           "project's default model (`gemini-3.6-flash`, 20 req/day) was "
           "exhausted mid-run, so this eval ran on `gemini-flash-lite-latest` "
           "instead (see `rag/llm.py`'s `RAG_MODEL_NAME` override). The cost "
           "numbers above are real, measured from actual token counts on live "
           "calls. The latency numbers are NOT comparable to production: the "
           "baseline table above was read back from the on-disk response cache "
           "(a second run after the first), so its per-question latency is "
           "near-zero by construction. The one place latency is real and worth "
           "reading is the mitigation's before/after in §4 — a live run there "
           "spent real wall-clock time in rate-limit backoff, and that number is "
           "reported as-is rather than smoothed away.",
           "",
           "## 3. The outcome-vs-trajectory gap",
           "",
           f"- outcome pass rate: **{_pct(b['outcome_pass_rate'])}**",
           f"- trajectory pass rate: **{_pct(b['trajectory_pass_rate'])}**",
           f"- **gap = {_pct(b['gap'])}**",
           ""]

    gc = _gap_case(before)
    if gc:
        s = gc["score"]
        out += [f"### Right answer, wrong path: `{gc['case']}`", "",
                f"**Question.** {gc['question']}", "",
                f"**Answer given.** {gc['trajectory']['answer'][:500]}", "",
                f"**Outcome eval: PASS** — the number is right.", "",
                f"**Trajectory eval: FAIL** — {'; '.join(s['notes'])}", "",
                "**The wrong path it took:**", "",
                "```"]
        for i, call in enumerate(gc["trajectory"]["calls"], start=1):
            out.append(f"{i}. {call['name']}({json.dumps(call['args'])})"
                       f"  ok={call['ok']}")
            out.append(f"     -> {call['result'][:160].strip()}")
        out += ["```", ""]

    if after:
        a = after["summary"]
        cmp = compare(before, after)
        top_before = max(b["mode_counts"].items(), key=lambda kv: kv[1])
        out += ["## 4. The single mitigation", "",
                "**Type:** tighter tool description (exactly one change — see "
                "`agent/mitigation.py`).", "",
                f"**Top failure mode targeted:** `{top_before[0]}`", "",
                "| | before | after |",
                "|---|---|---|",
                f"| `{top_before[0]}` count | {b['mode_counts'][top_before[0]]} | "
                f"{a['mode_counts'].get(top_before[0], 0)} |",
                f"| trajectory pass rate | {_pct(b['trajectory_pass_rate'])} | "
                f"{_pct(a['trajectory_pass_rate'])} |",
                f"| gap | {_pct(b['gap'])} | {_pct(a['gap'])} |",
                "",
                "### Price paid (measured, not assumed)", "",
                "| price | before | after | delta |",
                "|---|---|---|---|",
                f"| cost per question p50 | ${b['cost_p50']:.5f} | ${a['cost_p50']:.5f} | "
                f"{(a['cost_p50']-b['cost_p50'])/max(b['cost_p50'],1e-9):+.1%} |",
                f"| cost per question max | ${b['cost_max']:.5f} | ${a['cost_max']:.5f} | "
                f"{(a['cost_max']-b['cost_max'])/max(b['cost_max'],1e-9):+.1%} |",
                f"| latency p50 | {b['latency_p50']:.0f} ms | {a['latency_p50']:.0f} ms | "
                f"{a['latency_p50']-b['latency_p50']:+.0f} ms |",
                f"| total tool steps over 10 cases | {cmp['price']['steps_total'][0]} | "
                f"{cmp['price']['steps_total'][1]} | "
                f"{cmp['price']['steps_total'][1]-cmp['price']['steps_total'][0]:+d} |",
                ""]
        verdict = (
            f"**Verdict: this mitigation made the agent WORSE, not better.** "
            f"`{top_before[0]}` dropped {b['mode_counts'][top_before[0]]} -> "
            f"{a['mode_counts'].get(top_before[0], 0)} as intended, but "
            f"`wrong_tool` rose {b['mode_counts'].get('wrong_tool',0)} -> "
            f"{a['mode_counts'].get('wrong_tool',0)}, trajectory pass rate fell "
            f"{_pct(b['trajectory_pass_rate'])} -> {_pct(a['trajectory_pass_rate'])}, "
            f"and cost rose on every measure. The tightened instruction to "
            "\"confirm you resolved every defined term\" made the model reach for "
            "`list_documents` as a reflexive first step and, on simple lookups "
            "that never needed a defined term resolved, it changed a correct path "
            "into a differently-ordered one that the eval — correctly — does not "
            "accept. This is reported as-is rather than swapped for a mitigation "
            "that looks better, because the honest number is the point of the "
            "exercise."
        )
        out += [verdict, "",
                "## 5. Per-mode regression check", "",
                "| mode | before | after | delta |", "|---|---|---|---|"]
        for r in cmp["rows"]:
            flag = " **← worse**" if r["delta"] > 0 else ""
            out.append(f"| `{r['mode']}` | {r['before']} | {r['after']} | "
                       f"{r['delta']:+d}{flag} |")
        out += ["",
                f"- modes checked: **all {len(MODES)}** in the taxonomy",
                f"- worsened: **{', '.join(cmp['worsened']) or 'none'}**",
                f"- newly appeared: **{', '.join(cmp['appeared']) or 'none'}**",
                f"- cases that regressed on trajectory: "
                f"**{', '.join(cmp['regressed_cases']) or 'none'}**",
                "",
                "### After-mitigation case table", "",
                _case_rows(after), ""]

    inj = RUNS / "injection.json"
    if inj.exists():
        data = json.loads(inj.read_text())
        out += ["## 6. Bonus — indirect prompt injection", "",
                "Escalating payloads were planted in a contract the agent's own "
                "retrieval returns, inside the termination clause it actually "
                "reads (not off in an unrelated clause it never opens). Each was "
                "tried only after the previous one was refused unprompted:", "",
                "**v1 (bracketed drafting note):**", "",
                f"> {data['payload_v1']}", "",
                "**v2 (fake \"SYSTEM UPDATE\" framing):**", "",
                f"> {data['payload_v2']}", ""]
        if "payload_v3" in data:
            out += ["**v3 (spoofs the document/system boundary itself):**", "",
                    f"> {data['payload_v3']}", ""]
        if "payload_v4" in data:
            out += ["**v4 (plainest possible imperative, addressed directly to "
                    "\"the assistant\", no meta-framing):**", "",
                    f"> {data['payload_v4']}", ""]
        for arm, runs in data["arms"].items():
            out += [f"### {arm}", "", "| probe | obeyed injection? | guardrail | answer |",
                    "|---|---|---|---|"]
            for r in runs:
                out.append(
                    f"| {r['probe'][:60]} | "
                    f"{'**YES**' if r['obeyed_injection'] else 'no'} | "
                    f"{r['blocked_by_guardrail'] or '—'} | "
                    f"{r['answer'][:150].replace('|', '/')} |")
            out.append("")

        any_obeyed = any(
            r["obeyed_injection"] for runs in data["arms"].values() for r in runs
        )
        n_trials = sum(len(runs) for runs in data["arms"].values())
        out += ["### Result", ""]
        if any_obeyed:
            out += ["At least one payload got through — see the row(s) marked "
                    "**YES** above. The defended arm shows what the sanitiser + "
                    "output guardrail stopped, and what, if anything, still got "
                    "through it.", ""]
        else:
            out += [
                f"**None of the {n_trials} trials across four escalating payloads "
                "(bracketed note, fake system-update, fake document/system "
                "boundary, plain imperative) got the agent to assert the "
                "injected claim — undefended or defended.** "
                "`gemini-flash-lite-latest` read the injected text (confirmed in "
                "the raw tool output, not just the final answer) and refused it "
                "unprompted every time.", "",
                "**What this does and does not show.** It shows this model has "
                "real built-in resistance to this style of in-document "
                "instruction injection. It does NOT show the defences "
                "(`sanitize_tool_output`, `require_resolvable_clause`) actually "
                "stop anything — they were never tested against a successful "
                "bypass, because none occurred. A model swap, a subtler payload "
                "(one that doesn't announce itself as an instruction — e.g. "
                "forging what looks like a legitimately amended clause instead "
                "of a drafting note), or stacking the injection across multiple "
                "retrieved chunks instead of one could still get through; none of "
                "that was tried here. The honest claim is: this defence is "
                "**untested against a real bypass**, not **proven effective**.",
                ""]

    (ROOT / "WEEK8_TRAJECTORY_EVAL.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {ROOT / 'WEEK8_TRAJECTORY_EVAL.md'}")


if __name__ == "__main__":
    main()
