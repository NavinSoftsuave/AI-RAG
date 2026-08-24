"""The evaluation dataset: questions + ground-truth source document.

These 15 questions come from RAG_Test_Documents_and_Questions.docx. For each
question we record which document *should* be retrieved to answer it. That
ground truth is what lets us compute hit-rate@k as a NUMBER instead of eyeballing
whether an answer "looks right".

The corpus is a deliberate mix:
  - Some questions are answerable by MEANING alone (e.g. "Can fathers take leave
    after a child's birth?" -> paternity leave, with zero shared keywords).
  - Some hinge on EXACT terms (e.g. "What does ERR-4032 mean?", "default admin
    password") where semantic embeddings blur and keyword search wins.
That mix is exactly why hybrid (semantic + keyword) is the change under test.
"""

from dataclasses import dataclass

# The source filenames as they get ingested (see docs/eval_corpus/).
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
