"""Evaluation dataset: each question paired with the document that should answer
it (ground truth for hit-rate@k).

The mix is deliberate — some questions are answerable by meaning alone, others
hinge on exact terms (codes, passwords) where keyword search wins — which is why
hybrid retrieval is the change under test.
"""

from dataclasses import dataclass

# Source filenames as ingested (see docs/eval_corpus/).
LEAVE = "employee_leave_policy.txt"
IT = "it_support_guide.txt"
INSURANCE = "insurance_policy.txt"
PRINTER = "product_manual.txt"
REFUND = "customer_refund_policy.txt"


@dataclass(frozen=True)
class EvalCase:
    question: str
    gold_source: str  # the document that actually answers this question


CASES: list[EvalCase] = [
    EvalCase("How many weeks of maternity leave does an employee get?", LEAVE),
    EvalCase("Can unused casual leave be carried forward?", LEAVE),
    EvalCase("What does ERR-4032 mean?", IT),
    EvalCase("How can I unlock my account after ERR-4032?", IT),
    EvalCase("What is the deductible amount per claim?", INSURANCE),
    EvalCase("What is the annual coverage limit?", INSURANCE),
    EvalCase("Does SmartPrinter X200 support duplex printing?", PRINTER),
    EvalCase("What is the default admin password?", PRINTER),
    EvalCase("How long does a customer have to request a refund?", REFUND),
    EvalCase("Are digital products refundable?", REFUND),
    EvalCase("What happens after five failed login attempts?", IT),
    EvalCase("How much insurance coverage is provided annually?", INSURANCE),
    EvalCase("Can fathers take leave after a child's birth?", LEAVE),
    EvalCase("What printing options are supported by the X200?", PRINTER),
    EvalCase("How long does a refund usually take?", REFUND),
]
