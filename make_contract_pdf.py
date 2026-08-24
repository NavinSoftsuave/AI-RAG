"""Generate a sample legal contract PDF for testing the RAG app."""

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

OUT = "docs/sample_service_agreement.pdf"

# (heading, body) sections of the contract.
SECTIONS = [
    ("MASTER SERVICES AGREEMENT",
     "This Master Services Agreement (\"Agreement\") is entered into as of "
     "January 15, 2025 (the \"Effective Date\") by and between Acme "
     "Corporation, a Delaware corporation (\"Provider\"), and Globex Limited, "
     "a company incorporated in England and Wales (\"Client\")."),

    ("1. TERM",
     "This Agreement shall commence on the Effective Date and continue for an "
     "initial term of two (2) years, unless earlier terminated in accordance "
     "with Section 8. Thereafter it shall automatically renew for successive "
     "one (1) year periods unless either party gives written notice of "
     "non-renewal at least ninety (90) days before the end of the then-current "
     "term."),

    ("2. SCOPE OF SERVICES",
     "Provider shall perform the software development and support services "
     "described in one or more Statements of Work (each, an \"SOW\") agreed by "
     "the parties. Each SOW shall be governed by the terms of this Agreement. "
     "In the event of a conflict, the terms of the SOW control only with "
     "respect to the specific services described therein."),

    ("3. FEES AND PAYMENT",
     "Client shall pay the fees set out in each SOW. Provider shall invoice "
     "Client monthly in arrears. Client shall pay all undisputed invoices "
     "within thirty (30) days of receipt. Any amount not paid when due shall "
     "accrue interest at a rate of one and one-half percent (1.5%) per month, "
     "or the maximum rate permitted by law, whichever is lower."),

    ("4. INTELLECTUAL PROPERTY",
     "All deliverables created by Provider specifically for Client under an "
     "SOW shall, upon full payment, be owned by Client. Provider retains all "
     "rights to its pre-existing materials, tools, and know-how, and grants "
     "Client a perpetual, non-exclusive licence to use such pre-existing "
     "materials solely as incorporated into the deliverables."),

    ("5. CONFIDENTIALITY",
     "Each party shall keep the other party's Confidential Information "
     "confidential and shall not disclose it to any third party without prior "
     "written consent. This obligation shall survive termination of this "
     "Agreement for a period of five (5) years. Confidential Information does "
     "not include information that is or becomes publicly available through no "
     "fault of the receiving party."),

    ("6. WARRANTIES",
     "Provider warrants that the services will be performed in a professional "
     "and workmanlike manner in accordance with generally accepted industry "
     "standards. Except as expressly stated, the services are provided \"as "
     "is\" and Provider disclaims all other warranties, whether express or "
     "implied, including any implied warranty of merchantability or fitness "
     "for a particular purpose."),

    ("7. LIMITATION OF LIABILITY",
     "Except for breaches of confidentiality or indemnification obligations, "
     "neither party's aggregate liability arising out of or related to this "
     "Agreement shall exceed the total fees paid by Client under the "
     "applicable SOW during the twelve (12) months preceding the event giving "
     "rise to the claim. In no event shall either party be liable for any "
     "indirect, incidental, special, or consequential damages."),

    ("8. TERMINATION",
     "Either party may terminate this Agreement for convenience upon sixty "
     "(60) days' prior written notice. Either party may terminate immediately "
     "upon written notice if the other party materially breaches this "
     "Agreement and fails to cure such breach within thirty (30) days of "
     "receiving written notice of it. Upon termination, Client shall pay for "
     "all services performed up to the effective date of termination."),

    ("9. GOVERNING LAW AND DISPUTES",
     "This Agreement shall be governed by and construed in accordance with the "
     "laws of the State of Delaware, without regard to its conflict of laws "
     "principles. Any dispute arising under this Agreement shall be resolved "
     "by binding arbitration administered in Wilmington, Delaware, under the "
     "rules of the American Arbitration Association."),

    ("10. FORCE MAJEURE",
     "Neither party shall be liable for any failure or delay in performance "
     "due to causes beyond its reasonable control, including acts of God, "
     "natural disasters, war, terrorism, labour disputes, or governmental "
     "action, provided that the affected party gives prompt notice and uses "
     "reasonable efforts to resume performance."),

    ("11. ENTIRE AGREEMENT",
     "This Agreement, together with all SOWs, constitutes the entire agreement "
     "between the parties and supersedes all prior or contemporaneous "
     "understandings, whether written or oral. Any amendment must be in "
     "writing and signed by authorised representatives of both parties."),
]


def main() -> None:
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "Heading", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6,
        fontSize=11,
    )
    title = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=16, spaceAfter=18,
    )
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"], fontSize=10, leading=15,
        spaceAfter=6,
    )

    story = []
    for i, (head, text) in enumerate(SECTIONS):
        style = title if i == 0 else heading
        story.append(Paragraph(head, style))
        story.append(Paragraph(text, body))
        story.append(Spacer(1, 0.08 * inch))

    doc = SimpleDocTemplate(
        OUT, pagesize=LETTER,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        leftMargin=1 * inch, rightMargin=1 * inch,
        title="Master Services Agreement",
    )
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
