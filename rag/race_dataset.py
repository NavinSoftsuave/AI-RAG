"""10 Contract questions benchmark dataset for Agent vs Fixed Workflow Race.

Includes 3 multi-step dependent queries where step 3 depends on what step 2 found (defined-term-chase and amendment schedule lookups).
"""

from dataclasses import dataclass
from typing import List


@dataclass
class ContractQuestion:
    id: int
    category: str  # "single_step", "two_step", "multi_step_dependent"
    question: str
    expected_key_terms: List[str]


RACE_DATASET: List[ContractQuestion] = [
    # --- Single-step Lookups (4) ---
    ContractQuestion(
        id=1,
        category="single_step",
        question="What is the monthly base rent under the Commercial Lease Agreement?",
        expected_key_terms=["18,000", "$18,000", "18000"],
    ),
    ContractQuestion(
        id=2,
        category="single_step",
        question="What is the governing law for the Commercial Lease Agreement?",
        expected_key_terms=["Illinois", "State of Illinois"],
    ),
    ContractQuestion(
        id=3,
        category="single_step",
        question="What is the annual base salary for the Senior Software Engineer in the Employment Agreement?",
        expected_key_terms=["145,000", "$145,000", "145000"],
    ),
    ContractQuestion(
        id=4,
        category="single_step",
        question="What is the duration of confidentiality obligations after disclosure under the Mutual NDA?",
        expected_key_terms=["three", "3", "3 years", "three (3) years"],
    ),
    # --- Two-step Queries (3) ---
    ContractQuestion(
        id=5,
        category="two_step",
        question="What is the notice period required for termination if tenant fails to pay rent under the Commercial Lease Agreement?",
        expected_key_terms=["ten", "10", "10 days", "ten (10) days"],
    ),
    ContractQuestion(
        id=6,
        category="two_step",
        question="What is the limitation of liability cap specified in Amendment No. 1 to Master Services Agreement?",
        expected_key_terms=["total fees", "12 months", "twelve"],
    ),
    ContractQuestion(
        id=7,
        category="two_step",
        question="How many days of paid vacation per year is the employee entitled to in the Employment Agreement, and how many days can carry over?",
        expected_key_terms=["20", "twenty", "5", "five"],
    ),
    # --- Multi-step Dependent Queries (3) ---
    # Step 3 depends on what step 2 found (e.g. clause turns on a defined term pointing to schedule)
    ContractQuestion(
        id=8,
        category="multi_step_dependent",
        question="Under Amendment No. 1, lookup the defined 'Notice Period' for convenience termination, then lookup the defined 'Cure Period' for material breach in the Amendment schedule, and compare both periods.",
        expected_key_terms=["sixty", "60", "thirty", "30"],
    ),
    ContractQuestion(
        id=9,
        category="multi_step_dependent",
        question="In the Commercial Lease Agreement, resolve the defined 'Effective Date' from Section 1, locate the rent increase percentage on the anniversary date, and calculate the increased monthly rent after 1 year.",
        expected_key_terms=["July 1, 2025", "3%", "18,540", "18540"],
    ),
    ContractQuestion(
        id=10,
        category="multi_step_dependent",
        question="In the Employment Agreement, resolve the defined probationary period notice requirement from Section 4, compare it with the non-probationary termination notice requirement in Section 5, and state the notice period during day 45 of employment.",
        expected_key_terms=["two", "2", "2 weeks", "two (2) weeks"],
    ),
]
