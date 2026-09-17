"""The 10 trajectory cases: question, expected tool SEQUENCES, and ground truth.

Two things are asserted per case:

  `expected_paths` — a SET of acceptable tool sequences, not one. Where clause
  order is legally irrelevant (reading the Definitions/defined term before or
  after the operative clause are both correct), every valid ordering is listed.
  Asserting a single sequence there would score correct runs as failures and
  inflate the outcome-vs-trajectory gap — the exact mistake the brief warns about.

  `required_tools` — the steps that are NOT optional. A termination question that
  turns on which agreement governs MUST resolve the defined term; getting "60
  days" without it is the right answer down a wrong path.

`alt_path` marks the cases that legitimately accept more than one sequence, so
the report can show which ones were deliberately loosened.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrajectoryCase:
    id: str
    question: str
    mode: str                        # question type
    expected_paths: tuple            # set of acceptable tool sequences
    required_tools: tuple            # tools that must appear, in any position
    min_steps: int                   # steps a competent path needs
    expected_answer_contains: tuple  # outcome ground truth (any one suffices)
    should_refuse: bool = False
    # Documents the agent must actually OPEN. A conflict between a base
    # agreement and its amendment is invisible unless both are read.
    required_documents: tuple = ()
    alt_path: bool = False
    alt_reason: str = ""
    valid_args: dict = field(default_factory=dict)  # document -> legal clauses


CASES: list[TrajectoryCase] = [

    # --- 1. THE CORE CASE -----------------------------------------------------
    # The MSA says 60 days. Amendment No. 1 ALSO says 60 days. So the outcome is
    # identical either way — and that is precisely why the path matters: an agent
    # that never checks which instrument governs gets the right number by luck.
    TrajectoryCase(
        id="C1-termination-convenience",
        question=(
            "What is the notice period to terminate the Master Services Agreement "
            "for convenience?"
        ),
        mode="defined-term-dependent",
        expected_paths=(
            ("search_contracts", "get_clause", "resolve_defined_term"),
            ("search_contracts", "resolve_defined_term", "get_clause"),
            ("resolve_defined_term", "search_contracts", "get_clause"),
            ("list_documents", "search_contracts", "get_clause", "resolve_defined_term"),
            ("list_documents", "resolve_defined_term", "search_contracts", "get_clause"),
            ("search_contracts", "get_clause", "get_clause", "resolve_defined_term"),
            ("search_contracts", "resolve_defined_term", "get_clause", "get_clause"),
        ),
        required_tools=("resolve_defined_term", "get_clause"),
        min_steps=3,
        expected_answer_contains=("sixty", "60"),
        alt_path=True,
        alt_reason=(
            'Resolving "Agreement" before or after reading the termination clause '
            "are both correct; only skipping it is wrong."
        ),
        valid_args={"msa": {"8"}, "amendment": {"1"}},
    ),

    # --- 2. conflict: amendment supersedes base ------------------------------
    TrajectoryCase(
        id="C2-payment-terms-conflict",
        question="How many days does Globex have to pay an undisputed invoice?",
        mode="conflict",
        expected_paths=(
            ("search_contracts", "get_clause", "get_clause"),
            ("search_contracts", "get_clause", "get_clause", "resolve_defined_term"),
            ("list_documents", "search_contracts", "get_clause", "get_clause"),
            ("search_contracts", "get_clause", "resolve_defined_term", "get_clause"),
        ),
        required_tools=("get_clause",),
        required_documents=("msa", "amendment"),
        min_steps=3,
        expected_answer_contains=("forty-five", "45"),
        alt_path=True,
        alt_reason=(
            "The base MSA clause 3 and Amendment clause 2 may be read in either "
            "order; both must be read before the conflict can be resolved."
        ),
        valid_args={"msa": {"3"}, "amendment": {"2"}},
    ),

    # --- 3. single-clause lookup, one document -------------------------------
    TrajectoryCase(
        id="C3-nda-governing-law",
        question="What law governs the mutual non-disclosure agreement?",
        mode="lookup",
        expected_paths=(
            ("search_contracts",),
            ("search_contracts", "get_clause"),
            ("get_clause",),
            ("list_documents", "get_clause"),
            ("list_documents", "search_contracts", "get_clause"),
        ),
        required_tools=(),
        min_steps=1,
        expected_answer_contains=("New York",),
        alt_path=True,
        alt_reason=(
            "A single-clause fact: search alone is sufficient; pulling the clause "
            "verbatim to cite it is equally correct, not an extra step to penalise."
        ),
        valid_args={"nda": {"7"}},
    ),

    # --- 4. defined term is the whole question -------------------------------
    TrajectoryCase(
        id="C4-confidential-information-definition",
        question=(
            "Under the mutual NDA, what does Confidential Information exclude?"
        ),
        mode="defined-term-dependent",
        expected_paths=(
            ("resolve_defined_term",),
            ("search_contracts", "resolve_defined_term"),
            ("resolve_defined_term", "get_clause"),
            ("search_contracts", "resolve_defined_term", "get_clause"),
            ("resolve_defined_term", "search_contracts"),
        ),
        required_tools=("resolve_defined_term",),
        min_steps=1,
        expected_answer_contains=("publicly available", "independently developed"),
        valid_args={"nda": {"2"}},
    ),

    # --- 5. exact value ------------------------------------------------------
    TrajectoryCase(
        id="C5-lease-security-deposit",
        question="What is the security deposit under the commercial lease?",
        mode="exact-value",
        expected_paths=(
            ("search_contracts",),
            ("search_contracts", "get_clause"),
            ("get_clause",),
            ("list_documents", "get_clause"),
        ),
        required_tools=(),
        min_steps=1,
        expected_answer_contains=("36,000", "$36,000"),
        alt_path=True,
        alt_reason="Search-only and clause-fetch are both complete paths for a single figure.",
        valid_args={"lease": {"3"}},
    ),

    # --- 6. multi-document comparison ----------------------------------------
    TrajectoryCase(
        id="C6-confidentiality-survival-compare",
        question=(
            "How long do confidentiality obligations survive under the MSA "
            "compared with the mutual NDA?"
        ),
        mode="multi-doc",
        expected_paths=(
            ("search_contracts", "get_clause", "get_clause"),
            ("get_clause", "get_clause"),
            ("search_contracts", "get_clause", "get_clause", "resolve_defined_term"),
            ("list_documents", "get_clause", "get_clause"),
            ("search_contracts", "search_contracts", "get_clause", "get_clause"),
        ),
        required_tools=("get_clause",),
        required_documents=("msa", "nda"),
        min_steps=2,
        expected_answer_contains=("five", "three", "5", "3"),
        alt_path=True,
        alt_reason="The two contracts may be read in either order; neither is privileged.",
        valid_args={"msa": {"5"}, "nda": {"4"}},
    ),

    # --- 7. conditional clause, needs the carve-out --------------------------
    TrajectoryCase(
        id="C7-noncompete-carveout",
        question=(
            "Does the non-compete in the employment agreement apply if Peter "
            "Gibbons is terminated without cause?"
        ),
        mode="conditional",
        expected_paths=(
            ("search_contracts", "get_clause"),
            ("get_clause",),
            ("search_contracts", "get_clause", "get_clause"),
            ("list_documents", "search_contracts", "get_clause"),
        ),
        required_tools=("get_clause",),
        min_steps=1,
        expected_answer_contains=("does not apply", "not apply", "no"),
        alt_path=True,
        alt_reason="Clause 6 alone answers it; also reading clause 5 (termination) is reasonable.",
        valid_args={"employment": {"5", "6"}},
    ),

    # --- 8. out of scope: must refuse ----------------------------------------
    TrajectoryCase(
        id="C8-out-of-scope-arbitration-fees",
        question=(
            "Who pays the arbitrator's fees in a dispute under the Master "
            "Services Agreement?"
        ),
        mode="out-of-scope",
        expected_paths=(
            ("search_contracts",),
            ("search_contracts", "get_clause"),
            ("search_contracts", "search_contracts"),
            ("search_contracts", "get_clause", "search_contracts"),
            ("list_documents", "search_contracts", "get_clause"),
        ),
        required_tools=("search_contracts",),
        min_steps=1,
        expected_answer_contains=("don't know", "does not", "not specified", "silent"),
        should_refuse=True,
        alt_path=True,
        alt_reason=(
            "Confirming absence may reasonably take one search or a search plus "
            "the arbitration clause; both are honest paths to a refusal."
        ),
        valid_args={"msa": {"9"}},
    ),

    # --- 9. term arithmetic on the base agreement -----------------------------
    TrajectoryCase(
        id="C9-msa-renewal-notice",
        question=(
            "How much notice must a party give to stop the Master Services "
            "Agreement from auto-renewing?"
        ),
        mode="defined-term-dependent",
        expected_paths=(
            ("search_contracts", "get_clause"),
            ("get_clause",),
            ("search_contracts", "get_clause", "resolve_defined_term"),
            ("search_contracts", "get_clause", "get_clause"),
            ("list_documents", "search_contracts", "get_clause"),
        ),
        required_tools=("get_clause",),
        min_steps=1,
        expected_answer_contains=("ninety", "90"),
        alt_path=True,
        alt_reason="Clause 1 carries the whole answer; confirming the term is optional.",
        valid_args={"msa": {"1"}},
    ),

    # --- 10. ambiguous across documents --------------------------------------
    TrajectoryCase(
        id="C10-ambiguous-termination-notice",
        question="What is the termination notice period?",
        mode="ambiguous",
        expected_paths=(
            ("list_documents",),
            ("list_documents", "search_contracts"),
            ("search_contracts",),
            ("search_contracts", "list_documents"),
            ("search_contracts", "get_clause", "get_clause"),
            ("list_documents", "search_contracts", "get_clause"),
        ),
        required_tools=(),
        min_steps=1,
        expected_answer_contains=("which", "depends", "sixty", "thirty", "60", "30"),
        alt_path=True,
        alt_reason=(
            "The question does not name a contract. Listing the documents to ask "
            "which, or enumerating each contract's notice period, are both valid."
        ),
        valid_args={"msa": {"8"}, "amendment": {"1"}, "employment": {"4", "5"},
                    "lease": {"1"}, "nda": {"4"}},
    ),
]

ALT_PATH_CASES = [c.id for c in CASES if c.alt_path]
