"""
Streamlit UI for the GeM Bid Compliance Checker.
Upload bid documents -> see extraction + rule validation results instantly.
"""

import sys
import os

# This MUST run before any local package imports (reports, extraction, rules)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import tempfile
import json

from extraction.pdf_reader import extract_text_from_pdf, is_text_based_pdf
from extraction.ocr_reader import extract_text_via_ocr
from extraction.field_extractor import process_document
from rules.rule_engine import load_rules, build_compliance_report
from reports.pdf_export import generate_pdf_report
from reports.excel_export import generate_excel_report

st.set_page_config(page_title="GeM Bid Compliance Checker", page_icon="📋", layout="wide")

st.title("📋 GeM Bid Compliance Checker")
st.caption("Upload GST, PAN, and MSME certificates to instantly check compliance.")

st.divider()

uploaded_files = st.file_uploader(
    "Upload bid documents (PDF)",
    type=["pdf"],
    accept_multiple_files=True
)

check_clicked = st.button("🔍 Check Compliance", type="primary", disabled=not uploaded_files)

if check_clicked and uploaded_files:
    with st.spinner("Processing documents..."):
        extracted_docs = []

        for uploaded_file in uploaded_files:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                if is_text_based_pdf(tmp_path):
                    text = extract_text_from_pdf(tmp_path)
                    confidence_note = None
                else:
                    text, ocr_confidence = extract_text_via_ocr(tmp_path)
                    confidence_note = ocr_confidence

                doc = process_document(tmp_path, text)
                doc["file_name"] = uploaded_file.name
                if confidence_note is not None:
                    doc["confidence"] = min(doc["confidence"], confidence_note)

                extracted_docs.append(doc)
                os.unlink(tmp_path)
            except Exception:
                st.warning(f"⚠️ Couldn't process {uploaded_file.name}: please re-upload a clear PDF.")
                continue

        rules = load_rules(os.path.join(os.path.dirname(__file__), "..", "rules", "rules.json"))
        report = build_compliance_report(
            "BID-" + str(hash(tuple(f.name for f in uploaded_files)))[-6:],
            extracted_docs,
            rules
        )

    # ---------- Summary ----------
    st.divider()
    status_color = {
        "Compliant": "🟢",
        "Non-Compliant": "🔴",
        "Incomplete": "🟡"
    }.get(report["overall_status"], "⚪")

    st.subheader(f"{status_color} Overall Status: {report['overall_status']}")

    valid_count = sum(1 for d in report["documents"] if d["status"] == "Valid")
    total_count = len(report["documents"])
    avg_confidence = sum(d.get("confidence", 1.0) for d in report["documents"] if d["status"] != "Missing") / \
                      max(1, sum(1 for d in report["documents"] if d["status"] != "Missing"))

    m1, m2 = st.columns(2)
    m1.metric("Documents checked", f"{valid_count} / {total_count} valid")
    m2.metric("Avg. extraction confidence", f"{int(avg_confidence * 100)}%")

    st.divider()
    # ---------- Per-document results ----------
    for doc in report["documents"]:
        status_icon = {
            "Valid": "✅",
            "Invalid": "❌",
            "Missing": "🚫",
            "Needs Review": "⚠️"
        }.get(doc["status"], "❔")

        confidence = doc.get("confidence", 1.0)
        confidence_pct = int(confidence * 100)

        with st.expander(
            f"{status_icon} {doc['doc_type']} — {doc.get('file_name') or 'Not submitted'} "
            f"({doc['status']}, {confidence_pct}% confidence)",
            expanded=(doc["status"] != "Valid")
        ):
            # Confidence bar
            if doc["status"] != "Missing":
                if confidence >= 0.8:
                    st.progress(confidence, text=f"Extraction confidence: {confidence_pct}% — High")
                elif confidence >= 0.5:
                    st.progress(confidence, text=f"Extraction confidence: {confidence_pct}% — Medium")
                else:
                    st.progress(confidence, text=f"Extraction confidence: {confidence_pct}% — Low")
                    st.warning(
                        "⚠️ Low extraction confidence — this document may be blurry, scanned poorly, "
                        "or in an unexpected format. Please verify manually before relying on this result."
                    )

            if doc["status"] == "Missing":
                st.error(doc["results"][0]["reason"])
            else:
                for result in doc["results"]:
                    if result["passed"]:
                        st.success(f"**{result['field']}**: OK")
                    else:
                        st.error(f"**{result['field']}**: {result['reason']}")

    # ---------- Download report ----------
    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        st.download_button(
            "⬇️ Download JSON",
            data=json.dumps(report, indent=2),
            file_name="compliance_report.json",
            mime="application/json"
        )

    with col2:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            generate_pdf_report(report, tmp_pdf.name)
            with open(tmp_pdf.name, "rb") as f:
                st.download_button(
                    "⬇️ Download PDF", data=f.read(),
                    file_name="compliance_report.pdf", mime="application/pdf"
                )

    with col3:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_xlsx:
            generate_excel_report(report, tmp_xlsx.name)
            with open(tmp_xlsx.name, "rb") as f:
                st.download_button(
                    "⬇️ Download Excel", data=f.read(),
                    file_name="compliance_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

elif not uploaded_files:
    st.info("Upload one or more documents above, then click **Check Compliance**.")