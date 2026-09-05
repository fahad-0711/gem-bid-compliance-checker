"""
Generates a professional PDF compliance report from a ComplianceReport dict.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from datetime import datetime

NAVY = colors.HexColor("#0B2545")
GREEN = colors.HexColor("#1E7E34")
RED = colors.HexColor("#B02A2A")
AMBER = colors.HexColor("#B8860B")
LIGHT_GRAY = colors.HexColor("#F1EFE8")

STATUS_COLORS = {"Valid": GREEN, "Invalid": RED, "Missing": RED, "Needs Review": AMBER}

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="RTitle", fontName="Helvetica-Bold", fontSize=18,
                           textColor=NAVY, alignment=TA_CENTER, spaceAfter=6))
styles.add(ParagraphStyle(name="RSub", fontName="Helvetica", fontSize=10,
                           textColor=colors.gray, alignment=TA_CENTER, spaceAfter=16))
styles.add(ParagraphStyle(name="RHeading", fontName="Helvetica-Bold", fontSize=12,
                           textColor=NAVY, spaceBefore=14, spaceAfter=6))
styles.add(ParagraphStyle(name="RBody", fontName="Helvetica", fontSize=9.5, leading=14))


def generate_pdf_report(report: dict, output_path: str):
    doc = SimpleDocTemplate(output_path, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    story = []

    story.append(Paragraph("GeM Bid Compliance Report", styles["RTitle"]))
    story.append(Paragraph(f"Bid ID: {report['bid_id']}  |  Generated: "
                            f"{datetime.now().strftime('%d %b %Y, %I:%M %p')}", styles["RSub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=10))

    status_color = {"Compliant": GREEN, "Non-Compliant": RED, "Incomplete": AMBER}.get(
        report["overall_status"], colors.black)
    story.append(Paragraph(
        f'<font color="{status_color.hexval()}"><b>Overall Status: {report["overall_status"]}</b></font>',
        ParagraphStyle(name="OverallStatus", fontSize=14, alignment=TA_CENTER, spaceAfter=16)))

    for doc_report in report["documents"]:
        story.append(Paragraph(
            f'{doc_report["doc_type"]} — {doc_report.get("file_name") or "Not submitted"}',
            styles["RHeading"]))

        rows = [["Field", "Status", "Reason"]]
        for r in doc_report["results"]:
            status_text = "Pass" if r["passed"] else "Fail"
            rows.append([r["field"], status_text, r["reason"] or "-"])

        t = Table(rows, colWidths=[4*cm, 2.5*cm, 9.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GRAY]),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Generated automatically by GeM Bid Compliance Checker — "
                            "Smart India Hackathon 2026 (SIH26100).", styles["RSub"]))

    doc.build(story)


if __name__ == "__main__":
    # Quick manual test
    import sys, os, json
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from extraction.pdf_reader import extract_text_from_pdf
    from extraction.field_extractor import process_document
    from rules.rule_engine import load_rules, build_compliance_report

    folder = "data/sample_docs/valid"
    rules = load_rules()
    extracted_docs = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        text = extract_text_from_pdf(path)
        extracted_docs.append(process_document(path, text))

    report = build_compliance_report("BID-001", extracted_docs, rules)
    generate_pdf_report(report, "reports/sample_compliance_report.pdf")
    print("PDF report generated: reports/sample_compliance_report.pdf")