"""
Streamlit UI for the GeM Bid Compliance Checker.
Upload bid documents -> see extraction + rule validation results instantly.
"""

import streamlit as st
import sys
import os
import tempfile
import json

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from extraction.pdf_reader import extract_text_from_pdf, is_text_based_pdf
from extraction.ocr_reader import extract_text_via_ocr
from extraction.field_extractor import process_document
from rules.rule_engine import load_rules, build_compliance_report

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
            # Save to a temp file so our extraction functions (which expect a path) can read it
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
            doc["file_name"] = uploaded_file.name  # restore original name, not temp path
            if confidence_note is not None:
                doc["confidence"] = min(doc["confidence"], confidence_note)

            extracted_docs.append(doc)
            os.unlink(tmp_path)  # clean up temp file

        rules = load_rules(os.path.join(os.path.dirname(__file__), "..", "rules", "rules.json"))
        report = build_compliance_report("BID-" + str(hash(tuple(f.name for f in uploaded_files)))[-6:], extracted_docs, rules)

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
    st.metric("Documents checked", f"{valid_count} / {total_count} valid")

    st.divider()

    # ---------- Per-document results ----------
    for doc in report["documents"]:
        status_icon = {
            "Valid": "✅",
            "Invalid": "❌",
            "Missing": "🚫",
            "Needs Review": "⚠️"
        }.get(doc["status"], "❔")

        with st.expander(f"{status_icon} {doc['doc_type']} — {doc.get('file_name') or 'Not submitted'} ({doc['status']})",
                          expanded=(doc["status"] != "Valid")):
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
    report_json = json.dumps(report, indent=2)
    st.download_button(
        "⬇️ Download report (JSON)",
        data=report_json,
        file_name="compliance_report.json",
        mime="application/json"
    )

elif not uploaded_files:
    st.info("Upload one or more documents above, then click **Check Compliance**.")