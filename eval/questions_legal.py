"""Question set for legal-contracts error analysis (Week 5 · M3).

A deliberately broad, realistic mix — not cherry-picked easy questions. It spans:
  - straightforward single-clause lookups (should answer),
  - exact values (fees, notice periods, dollar amounts),
  - cross-document cases where Amendment No. 1 supersedes the base MSA,
  - questions spanning multiple contracts,
  - genuinely out-of-scope questions (should refuse with "I don't know"),
  - ambiguous / underspecified phrasing.

`expected` is a short human note on what a correct answer looks like — used only
as a reading aid while open-coding traces, NOT as an automatic grader.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    text: str
    kind: str        # rough intent, for later grouping (not ground truth)
    expected: str    # what a good answer should contain / do


QUESTIONS: list[Question] = [
    # --- straightforward single-clause lookups ---
    Question("What is the notice period to terminate the Master Services Agreement for convenience?",
             "lookup", "60 days' prior written notice"),
    Question("What law governs the Master Services Agreement?",
             "lookup", "Delaware"),
    Question("How long does confidentiality survive termination of the MSA?",
             "lookup", "five (5) years"),
    Question("What is the limitation of liability under the MSA?",
             "lookup", "capped at fees paid in the prior 12 months; no indirect/consequential damages"),
    Question("What is the initial term of the Master Services Agreement?",
             "lookup", "two (2) years, then auto-renews for one-year periods"),

    # --- exact values ---
    Question("What is the late payment interest rate in the MSA?",
             "exact-value", "1.5% per month"),
    Question("What is the base monthly rent in the commercial lease?",
             "exact-value", "$18,000"),
    Question("What is the security deposit for the commercial lease?",
             "exact-value", "$36,000"),
    Question("What is the annual base salary in the employment agreement?",
             "exact-value", "$145,000"),
    Question("How much commercial general liability insurance must the tenant carry?",
             "exact-value", "$2,000,000 per occurrence"),

    # --- cross-document: Amendment No. 1 supersedes the MSA ---
    Question("How many days does the client have to pay an undisputed invoice?",
             "conflict", "45 days per Amendment No. 1 (was 30 in the MSA) — amendment controls"),
    Question("What are the current payment terms of the agreement with Globex?",
             "conflict", "45 days, as amended — should not report the superseded 30 days"),

    # --- spanning multiple contracts ---
    Question("Which agreements contain a confidentiality clause?",
             "multi-doc", "MSA (5 yrs), NDA (3 yrs), and the amendment restates it"),
    Question("What are the governing-law states across all the contracts?",
             "multi-doc", "Delaware (MSA), New York (NDA), California (employment), Illinois (lease)"),
    Question("How long do confidentiality obligations last under the NDA?",
             "lookup", "three (3) years after disclosure"),

    # --- employment specifics ---
    Question("How much paid vacation does the employee get, and how much can carry over?",
             "lookup", "20 days/year; up to 5 days carry over, excess forfeited"),
    Question("What is the non-compete period in the employment agreement?",
             "lookup", "12 months; not applicable if terminated without cause"),
    Question("How long is the probationary period for the employee?",
             "lookup", "90 days, either party may terminate with 2 weeks' notice"),

    # --- out-of-scope (should refuse) ---
    Question("What is the penalty for early termination of the car lease?",
             "out-of-scope", "no car lease exists — should say I don't know"),
    Question("What is the employee's health insurance premium?",
             "out-of-scope", "not specified in the employment agreement — should refuse"),
    Question("Can the tenant keep a pet on the premises?",
             "out-of-scope", "lease is silent on pets — should refuse, not guess"),

    # --- ambiguous / underspecified ---
    Question("What is the termination notice period?",
             "ambiguous", "ambiguous across MSA/employment/lease — ideally asks which contract or lists them"),
    Question("What happens if payment is late?",
             "ambiguous", "differs by contract (MSA interest vs lease late fee) — should scope its answer"),
    Question("Is the agreement still valid?",
             "ambiguous", "under-specified; no clear answer — watch for a confident wrong answer"),
]
