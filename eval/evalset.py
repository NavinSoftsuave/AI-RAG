"""The Week-6 eval set: 25+ cases, each tagged with one Week-5 taxonomy mode.

Every case reuses a real question the app was asked (see questions_legal.py /
the captured traces), tagged with the failure mode it stresses. Regression cases
replayed verbatim from real failed traces are marked regression=True so they can
never silently come back.

This module is pure data — no LLM calls. The runner (run_eval_week6.py) pairs
each case with the app's cached answer, runs assertions, and (optionally) the
judge, then reports pass rate BY MODE.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    question: str
    mode: str               # Week-5 taxonomy mode this case stresses
    should_answer: bool     # True = app should answer; False = should refuse
    regression: bool = False
    note: str = ""          # what a correct answer looks like (reading aid)


# Taxonomy modes (finalised from the Week-5 trace analysis):
#   lookup         — single-clause fact lookup
#   exact-value    — a specific number/amount/date
#   conflict       — amendment supersedes the base contract
#   multi-doc      — answer spans several contracts
#   out-of-scope   — not in the corpus; app must refuse
#   ambiguous      — under-specified; app should scope or refuse, not guess

CASES: list[EvalCase] = [
    EvalCase("What is the notice period to terminate the Master Services Agreement for convenience?",
             "lookup", True, note="60 days' prior written notice"),
    EvalCase("What law governs the Master Services Agreement?",
             "lookup", True, note="Delaware"),
    EvalCase("How long does confidentiality survive termination of the MSA?",
             "lookup", True, note="five (5) years"),
    EvalCase("What is the limitation of liability under the MSA?",
             "lookup", True, note="capped at prior-12-months fees; no indirect damages"),
    EvalCase("What is the initial term of the Master Services Agreement?",
             "lookup", True, note="two (2) years, then auto-renews yearly"),
    EvalCase("What is the late payment interest rate in the MSA?",
             "exact-value", True, note="1.5% per month"),
    EvalCase("What is the base monthly rent in the commercial lease?",
             "exact-value", True, note="$18,000"),
    EvalCase("What is the security deposit for the commercial lease?",
             "exact-value", True, note="$36,000"),
    EvalCase("What is the annual base salary in the employment agreement?",
             "exact-value", True, note="$145,000"),
    EvalCase("How much commercial general liability insurance must the tenant carry?",
             "exact-value", True, note="$2,000,000 per occurrence"),
    EvalCase("How many days does the client have to pay an undisputed invoice?",
             "conflict", True, note="45 days per Amendment No. 1 (was 30) — amendment controls"),
    EvalCase("What are the current payment terms of the agreement with Globex?",
             "conflict", True, note="45 days as amended; must not report superseded 30 days"),
    EvalCase("Which agreements contain a confidentiality clause?",
             "multi-doc", True, note="MSA, NDA, amendment"),
    EvalCase("What are the governing-law states across all the contracts?",
             "multi-doc", True, note="Delaware, New York, California, Illinois"),
    EvalCase("How long do confidentiality obligations last under the NDA?",
             "lookup", True, note="three (3) years after disclosure"),
    EvalCase("How much paid vacation does the employee get, and how much can carry over?",
             "lookup", True, note="20 days/year; up to 5 carry over"),
    EvalCase("What is the non-compete period in the employment agreement?",
             "lookup", True, note="12 months; n/a if terminated without cause"),
    EvalCase("How long is the probationary period for the employee?",
             "lookup", True, note="90 days, 2 weeks' notice either side"),
    EvalCase("What is the penalty for early termination of the car lease?",
             "out-of-scope", False, note="no car lease exists — must refuse"),
    EvalCase("What is the employee's health insurance premium?",
             "out-of-scope", False, note="not specified — must refuse"),
    EvalCase("Can the tenant keep a pet on the premises?",
             "out-of-scope", False, note="lease silent on pets — must refuse"),
    EvalCase("What is the termination notice period?",
             "ambiguous", True, note="ambiguous across contracts — should scope or list"),
    EvalCase("What happens if payment is late?",
             "ambiguous", True, note="differs by contract — should scope its answer"),
    EvalCase("Is the agreement still valid?",
             "ambiguous", False, note="under-specified — should not confidently answer"),

    # --- Regression cases (replayed verbatim from real failed traces) ---
    # T2: false refusal — the MSA governing-law clause was retrieved, yet the app
    # said "I don't know". The fix must make this answer "Delaware".
    EvalCase("What law governs the Master Services Agreement?",
             "false-refusal", True, regression=True,
             note="REGRESSION from trace T2: was falsely refused; MSA says Delaware"),
    # T11: conflict not resolved — both the MSA (30 days) and Amendment No. 1 (45
    # days) chunks were retrieved; the app refused instead of stating the amended,
    # governing value. The fix must answer 45 days (amendment controls).
    EvalCase("How many days does the client have to pay an undisputed invoice?",
             "conflict", True, regression=True,
             note="REGRESSION from trace T11: was falsely refused; amended term is 45 days"),
]


def modes() -> list[str]:
    return sorted({c.mode for c in CASES})
