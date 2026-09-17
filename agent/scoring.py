"""Scoring a trajectory: the four numbers, the outcome check, and the mode zoo.

Trajectory metrics (Week 8):

  tool_choice_accuracy  — fraction of steps whose tool is the one a competent
                          path would call at that point. Scored against the SET
                          of expected paths: a step counts as correct if any
                          accepted path allows that tool at that position, so
                          legitimate reorderings are not punished.
  argument_validity     — fraction of tool calls whose arguments named a real
                          document and a real clause / defined term. This is the
                          "fluent fiction" detector: a call to get_clause(msa,
                          "12") is a fabricated citation, and the tool says so.
  step_efficiency       — steps_needed / steps_taken (1.0 = no wasted steps,
                          < 1.0 = wandering). Reported that way round so higher
                          is better and a loop drives it toward 0.
  cost_per_question     — USD per question from measured token counts, reported
                          as p50 AND max, never a bare mean.

Trajectory PASS requires: every required tool called, all arguments valid, the
realised sequence accepted by the path set, and no step-limit stop.
Outcome PASS only asks whether the final answer is right.
"""

from dataclasses import dataclass, field
from statistics import median

from .cases import TrajectoryCase
from .tools import DOC_REGISTRY

# --- the failure-mode zoo -----------------------------------------------------
MODES = [
    "wrong_tool",            # called a tool the task did not call for
    "fabricated_argument",   # named a clause/document/term that does not exist
    "skipped_required_step", # right answer, missing the step it depends on
    "loop",                  # repeated the same call with the same arguments
    "step_limit",            # ran out of steps without answering
    "quiet_giveup",          # refused/hedged despite the answer being retrievable
    "unrecoverable_error",   # a tool error the agent never recovered from
]


@dataclass
class TrajectoryScore:
    complete: bool
    case_id: str
    mode: str
    sequence: list[str]
    outcome_pass: bool
    trajectory_pass: bool
    tool_choice_accuracy: float
    argument_validity: float
    step_efficiency: float
    steps_taken: int
    steps_needed: int
    cost_usd: float
    latency_ms: float
    failure_modes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _prefix_ok(seq: list[str], paths: tuple) -> bool:
    """Is `seq` a prefix of, or equal to, any accepted path?"""
    return any(tuple(seq) == p or tuple(seq) == p[:len(seq)] for p in paths)


def tool_choice_accuracy(seq: list[str], paths: tuple) -> float:
    """Fraction of steps that some accepted path allows at that position.

    Scored greedily against the whole SET: at step i, the step is correct if any
    path still consistent with steps 0..i-1 permits this tool at position i.
    """
    if not seq:
        return 0.0
    alive = [p for p in paths]
    correct = 0
    for i, tool in enumerate(seq):
        allowed = {p[i] for p in alive if len(p) > i}
        if tool in allowed:
            correct += 1
            alive = [p for p in alive if len(p) > i and p[i] == tool] or alive
        else:
            # Step diverged. Keep scoring the rest against the full set so one
            # extra call does not zero out an otherwise sound path.
            alive = [p for p in paths]
    return correct / len(seq)


def argument_validity(calls: list[dict], case: TrajectoryCase) -> tuple[float, list[str]]:
    """Fraction of calls whose arguments referred to something real.

    A call is invalid if the tool rejected its arguments (unknown document,
    non-existent clause, undefined term) — i.e. the model produced a plausible
    citation that does not exist.
    """
    if not calls:
        return 0.0, []
    bad = []
    valid = 0
    for c in calls:
        args = c.get("args") or {}
        doc = str(args.get("document", "")).strip().lower()
        if doc and doc not in DOC_REGISTRY:
            bad.append(f"{c['name']}: unknown document {doc!r}")
            continue
        if not c.get("ok", False):
            bad.append(f"{c['name']}({args}): {c.get('error','tool error')}")
            continue
        valid += 1
    return valid / len(calls), bad


def _has_loop(calls: list[dict]) -> bool:
    """Same tool with the same arguments called more than once."""
    seen = set()
    for c in calls:
        key = (c["name"], repr(sorted((c.get("args") or {}).items())))
        if key in seen:
            return True
        seen.add(key)
    return False


def _answer_correct(answer: str, case: TrajectoryCase) -> bool:
    low = answer.lower()
    if case.should_refuse:
        return any(k.lower() in low for k in case.expected_answer_contains)
    if "i don't know" in low or "i dont know" in low:
        return False
    return any(k.lower() in low for k in case.expected_answer_contains)


def score(traj, case: TrajectoryCase) -> TrajectoryScore:
    """Score one trajectory against one case: outcome, path, four numbers, modes."""
    seq = traj.tool_sequence
    calls = traj.calls

    outcome = _answer_correct(traj.answer, case)

    tca = tool_choice_accuracy(seq, case.expected_paths)
    arg_ok, bad_args = argument_validity(calls, case)

    steps_needed = case.min_steps
    steps_taken = max(len(seq), 1)
    efficiency = min(1.0, steps_needed / steps_taken)

    modes: list[str] = []
    notes: list[str] = []

    missing = [t for t in case.required_tools if t not in seq]
    if missing:
        modes.append("skipped_required_step")
        notes.append(f"never called {missing}")

    # Some questions cannot be answered soundly from one document: a conflict
    # between the base agreement and its amendment is invisible unless BOTH are
    # opened. Reaching the right number from one of them is luck, not reasoning.
    opened = {
        str((c.get("args") or {}).get("document", "")).strip().lower()
        for c in calls if c.get("ok")
    }
    missing_docs = [d for d in case.required_documents if d not in opened]
    if missing_docs:
        modes.append("skipped_required_step")
        notes.append(f"never opened {missing_docs}; a conflict there would be invisible")

    if bad_args:
        modes.append("fabricated_argument")
        notes.extend(bad_args[:3])

    if seq and not any(_prefix_ok(seq[:i + 1], case.expected_paths)
                       for i in range(len(seq))) and tca < 1.0:
        modes.append("wrong_tool")
        notes.append(f"sequence {seq} matches no accepted path")
    elif tca < 1.0 and not missing:
        modes.append("wrong_tool")
        notes.append(f"off-path step in {seq}")

    if _has_loop(calls):
        modes.append("loop")
        notes.append("repeated an identical tool call")

    if traj.stopped_reason == "step_limit":
        modes.append("step_limit")
        notes.append(f"hit the {steps_taken}-step limit without answering")

    if not case.should_refuse and not outcome and "don't know" in traj.answer.lower():
        modes.append("quiet_giveup")
        notes.append("refused although the corpus contains the answer")

    if calls and not calls[-1].get("ok", True) and not outcome:
        modes.append("unrecoverable_error")
        notes.append("final tool call errored and the agent did not recover")

    trajectory_pass = (
        not missing
        and not missing_docs
        and not bad_args
        and tuple(seq) in case.expected_paths
        and traj.stopped_reason != "step_limit"
    )

    return TrajectoryScore(
        complete=traj.stopped_reason != "not_cached",
        case_id=case.id, mode=case.mode, sequence=seq,
        outcome_pass=outcome, trajectory_pass=trajectory_pass,
        tool_choice_accuracy=round(tca, 3),
        argument_validity=round(arg_ok, 3),
        step_efficiency=round(efficiency, 3),
        steps_taken=len(seq), steps_needed=steps_needed,
        cost_usd=round(traj.cost_usd, 6), latency_ms=traj.latency_ms,
        failure_modes=sorted(set(modes)), notes=notes,
    )


def aggregate(scores: list[TrajectoryScore]) -> dict:
    """Roll the per-case scores into the numbers the report needs.

    Only COMPLETE trajectories are scored. A run cut short because the daily API
    budget ran out is not evidence of a failure and must not be averaged in as
    one; it is reported separately as `incomplete`.
    """
    incomplete = [s.case_id for s in scores if not s.complete]
    scores = [s for s in scores if s.complete]
    n = len(scores) or 1
    costs = sorted(s.cost_usd for s in scores)
    outcome_rate = sum(s.outcome_pass for s in scores) / n
    traj_rate = sum(s.trajectory_pass for s in scores) / n

    mode_counts = {m: 0 for m in MODES}
    for s in scores:
        for m in s.failure_modes:
            mode_counts[m] = mode_counts.get(m, 0) + 1

    return {
        "n": len(scores),
        "incomplete": incomplete,
        "tool_choice_accuracy": round(sum(s.tool_choice_accuracy for s in scores) / n, 3),
        "argument_validity": round(sum(s.argument_validity for s in scores) / n, 3),
        "step_efficiency": round(sum(s.step_efficiency for s in scores) / n, 3),
        "cost_p50": round(median(costs), 6) if costs else 0.0,
        "cost_max": round(max(costs), 6) if costs else 0.0,
        "cost_mean": round(sum(costs) / n, 6),
        "latency_p50": round(median(sorted(s.latency_ms for s in scores)), 1),
        "latency_max": round(max((s.latency_ms for s in scores), default=0.0), 1),
        "outcome_pass_rate": round(outcome_rate, 3),
        "trajectory_pass_rate": round(traj_rate, 3),
        "gap": round(outcome_rate - traj_rate, 3),
        "mode_counts": mode_counts,
    }
