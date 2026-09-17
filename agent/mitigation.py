"""The arms of the experiment. ONE mitigation, named, with its price measured.

Week-8 rule: ship ONE mitigation, not two. If tighter tool descriptions and
argument validation land together and the mode drops, you have learned nothing
about which change did it — and you now maintain both forever. So `mitigated`
differs from `baseline` in EXACTLY ONE place, documented below.

THE MITIGATION (chosen after reading the baseline run, not before):
  Type      : tighter tool description
  Target    : skipped_required_step — the agent answers a question that turns on
              a defined term without ever resolving that term, so a right answer
              rides on an unchecked assumption about which instrument governs.
  Change    : `resolve_defined_term`'s description in the tool spec states WHEN
              it is mandatory, and the system prompt adds one precondition line.
              Nothing else moves: same tools, same step limit, same model, no
              argument validation, no re-planning, no workflow replacement.

The price is measured, not assumed: a mandatory extra tool call costs one more
model turn per affected question. See runs/regression_*.json for the numbers.
"""

from .contract_agent import SYSTEM, TOOL_SPEC

# --- the single change: one tool's description, tightened ---------------------
# Baseline text for resolve_defined_term was:
#     "Return where a capitalised defined term (e.g. "Agreement", "Confidential
#      Information", "Premises") is defined and by what text."
# It said what the tool DOES and never said when the agent MUST reach for it.

TIGHT_TOOL_SPEC = TOOL_SPEC.replace(
    """resolve_defined_term(term: string, document: string)
    Return where a capitalised defined term (e.g. "Agreement", "Confidential
    Information", "Premises") is defined and by what text.""",
    """resolve_defined_term(term: string, document: string)
    Return where a capitalised defined term (e.g. "Agreement", "Confidential
    Information", "Premises") is defined and by what text.
    REQUIRED before you answer whenever the answer depends on what a capitalised
    defined term refers to — in particular any question about termination,
    notice, survival or liability "under the Agreement", because a later
    amendment may redefine or supersede the clause you just read. Reading the
    operative clause is NOT sufficient on its own: resolve the term, then answer.
    Skipping this step is a failure even if your final number happens to be
    right.""",
)

MITIGATED_SYSTEM = SYSTEM.replace(
    "- Ground every statement in text a tool returned. Never invent clause numbers.",
    "- Ground every statement in text a tool returned. Never invent clause numbers.\n"
    "- Before answering, confirm you resolved every defined term the answer turns on.",
)

ARMS: dict[str, dict] = {
    "baseline": {
        "system": SYSTEM,
        "max_steps": 8,
    },
    "mitigated": {
        "system": MITIGATED_SYSTEM,
        "tool_spec": TIGHT_TOOL_SPEC,
        "max_steps": 8,
    },
}
