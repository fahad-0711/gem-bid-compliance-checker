"""
Streamlit UI for the GeM Bid Compliance Checker.
Upload bid documents -> see extraction + rule validation results instantly.
Also tracks compliance history across checks for an Insights view,
and allows editing compliance rules without touching code.
"""
from login_page import require_login
require_login()

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import tempfile
import json
from collections import Counter

from extraction.pdf_reader import extract_text_from_pdf, is_text_based_pdf
from extraction.ocr_reader import extract_text_via_ocr, extract_text_from_image
from extraction.field_extractor import process_document
from rules.rule_engine import load_rules, build_compliance_report
from rules.rules_manager import (
    read_rules_raw,
    validate_rules_json,
    save_rules,
    list_backups,
    restore_backup,
)
from reports.pdf_export import generate_pdf_report
from reports.excel_export import generate_excel_report
from extraction.docx_reader import read_docx


st.set_page_config(
    page_title="GeM Bid Compliance Checker",
    page_icon="📋",
    layout="wide",
)


# ---------- Session history ----------
if "report_history" not in st.session_state:
    st.session_state.report_history = []


st.title("📋 GeM Bid Compliance Checker")
st.caption(
    "Upload GST, PAN, and MSME certificates to instantly check compliance."
)


tab_check, tab_insights, tab_rules = st.tabs(
    ["🔍 Check Compliance", "📊 Insights", "⚙️ Manage Rules"]
)


# ============================================================
# TAB 1: CHECK COMPLIANCE
# ============================================================

with tab_check:

    # ---------- Uploader reset mechanism ----------
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    upload_col, clear_col = st.columns([5, 1])

    with upload_col:
        uploaded_files = st.file_uploader(
            "Upload bid documents (PDF, DOCX, or image)",
            type=["pdf", "docx", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"uploader_{st.session_state.uploader_key}",
        )

    with clear_col:
        st.write("")
        st.write("")
        if st.button("🗑️ Clear all"):
            st.session_state.uploader_key += 1
            st.rerun()

    # ---------- File size guard ----------
    MAX_FILE_SIZE_MB = 10

    if uploaded_files:
        oversized = [
            f.name
            for f in uploaded_files
            if f.size > MAX_FILE_SIZE_MB * 1024 * 1024
        ]

        if oversized:
            st.error(
                f"⚠️ These files exceed the {MAX_FILE_SIZE_MB}MB limit "
                f"and were excluded: {', '.join(oversized)}. "
                "Please upload a smaller/compressed version."
            )

            uploaded_files = [
                f for f in uploaded_files
                if f.name not in oversized
            ]

    check_clicked = st.button(
        "🔍 Check Compliance",
        type="primary",
        disabled=not uploaded_files,
    )
    if check_clicked and uploaded_files:

        with st.spinner("Processing documents..."):

            extracted_docs = []

            # ---------- Process every uploaded file ----------
            for uploaded_file in uploaded_files:

                tmp_path = None

                try:
                    # Use the file's REAL extension
                    ext = os.path.splitext(uploaded_file.name)[1].lower()

                    with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=ext
                    ) as tmp:

                        tmp.write(uploaded_file.read())
                        tmp_path = tmp.name

                    confidence_note = None

                    # ---------- PDF ----------
                    if ext == ".pdf":

                        if is_text_based_pdf(tmp_path):
                            text = extract_text_from_pdf(tmp_path)
                        else:
                            text, confidence_note = extract_text_via_ocr(
                                tmp_path
                            )

                    # ---------- DOCX ----------
                    elif ext == ".docx":

                        text = read_docx(tmp_path)

                    # ---------- Images ----------
                    elif ext in (".jpg", ".jpeg", ".png"):

                        # Images use direct OCR — NOT extract_text_via_ocr,
                        # since that function converts PDFs to images first
                        # and would fail on a file that's already an image.
                        text, confidence_note = extract_text_from_image(
                            tmp_path
                        )

                    else:
                        raise ValueError(
                            f"Unsupported file type: {ext}"
                        )

                    # ---------- Extract fields ----------
                    doc = process_document(
                        tmp_path,
                        text
                    )

                    doc["file_name"] = uploaded_file.name

                    if confidence_note is not None:
                        doc["confidence"] = min(
                            doc["confidence"],
                            confidence_note
                        )

                    extracted_docs.append(doc)

                except Exception as e:

                    st.warning(
                        f"⚠️ Couldn't process {uploaded_file.name}: "
                        f"{type(e).__name__}: {e}"
                    )

                    continue

                finally:

                    # Delete temporary file safely
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

            # ---------- Build compliance report ----------
            rules_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "rules",
                "rules.json",
            )

            rules = load_rules(rules_path)

            bid_id = (
                "BID-"
                + str(hash(tuple(f.name for f in uploaded_files)))[-6:]
            )

            report = build_compliance_report(
                bid_id,
                extracted_docs,
                rules,
            )

            # ---------- Save report in session history ----------
            st.session_state.report_history.append(report)

        # ====================================================
        # SUMMARY
        # ====================================================

        st.divider()

        status_color = {
            "Compliant": "🟢",
            "Non-Compliant": "🔴",
            "Incomplete": "🟡",
        }.get(
            report["overall_status"],
            "⚪",
        )

        st.subheader(
            f"{status_color} Overall Status: "
            f"{report['overall_status']}"
        )

        valid_count = sum(
            1
            for d in report["documents"]
            if d["status"] == "Valid"
        )

        total_count = len(report["documents"])

        confidence_values = [
            d.get("confidence", 1.0)
            for d in report["documents"]
            if d["status"] != "Missing"
        ]

        avg_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0
        )

        m1, m2 = st.columns(2)

        m1.metric(
            "Documents checked",
            f"{valid_count} / {total_count} valid",
        )

        m2.metric(
            "Avg. extraction confidence",
            f"{int(avg_confidence * 100)}%",
        )

        st.divider()

        # ====================================================
        # PER-DOCUMENT RESULTS
        # ====================================================

        for doc in report["documents"]:

            status_icon = {
                "Valid": "✅",
                "Invalid": "❌",
                "Missing": "🚫",
                "Needs Review": "⚠️",
            }.get(
                doc["status"],
                "❔",
            )

            confidence = doc.get("confidence", 1.0)
            confidence_pct = int(confidence * 100)

            with st.expander(
                f"{status_icon} "
                f"{doc['doc_type']} — "
                f"{doc.get('file_name') or 'Not submitted'} "
                f"({doc['status']}, {confidence_pct}% confidence)",
                expanded=(doc["status"] != "Valid"),
            ):

                # ---------- Confidence ----------
                if doc["status"] != "Missing":

                    if confidence >= 0.8:

                        st.progress(
                            confidence,
                            text=(
                                f"Extraction confidence: "
                                f"{confidence_pct}% — High"
                            ),
                        )

                    elif confidence >= 0.5:

                        st.progress(
                            confidence,
                            text=(
                                f"Extraction confidence: "
                                f"{confidence_pct}% — Medium"
                            ),
                        )

                    else:

                        st.progress(
                            confidence,
                            text=(
                                f"Extraction confidence: "
                                f"{confidence_pct}% — Low"
                            ),
                        )

                        st.warning(
                            "⚠️ Low extraction confidence — this document "
                            "may be blurry, scanned poorly, or in an "
                            "unexpected format. Please verify manually "
                            "before relying on this result."
                        )

                # ---------- Missing document ----------
                if doc["status"] == "Missing":

                    st.error(
                        doc["results"][0]["reason"]
                    )

                # ---------- Validation results ----------
                else:

                    for result in doc["results"]:

                        if result["passed"]:

                            st.success(
                                f"**{result['field']}**: OK"
                            )

                        else:

                            st.error(
                                f"**{result['field']}**: "
                                f"{result['reason']}"
                        )
                # ---------- Government record check ----------
                # "Mismatch" is already surfaced as a failed row in the
                # results list above (rules/rule_engine.py adds it there),
                # so showing it again here would just be a duplicate.
                # The other outcomes (Verified / Not Found / Not Checked)
                # aren't in results, so this box is still the only place
                # they're shown.
                gov_check = doc.get("government_verification")
                if gov_check and gov_check["status"] != "Mismatch":
                    gov_icon = {"Verified": "🏛️✅", "Not Found": "🏛️❓",
                                "Not Checked": "🏛️➖"}.get(gov_check["status"], "🏛️")
                    st.info(f"{gov_icon} **Government Record Check**: {gov_check['status']} — {gov_check['detail']}")
        # ====================================================
        # DOWNLOAD REPORTS
        # ====================================================

        st.divider()

        col1, col2, col3 = st.columns(3)

        # ---------- JSON ----------
        with col1:

            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(
                    report,
                    indent=2
                ),
                file_name="compliance_report.json",
                mime="application/json",
            )

        # ---------- PDF ----------
        with col2:

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".pdf"
            ) as tmp_pdf:

                generate_pdf_report(
                    report,
                    tmp_pdf.name
                )

                pdf_path = tmp_pdf.name

            with open(
                pdf_path,
                "rb"
            ) as f:

                st.download_button(
                    "⬇️ Download PDF",
                    data=f.read(),
                    file_name="compliance_report.pdf",
                    mime="application/pdf",
                )

        # ---------- Excel ----------
        with col3:

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".xlsx"
            ) as tmp_xlsx:

                generate_excel_report(
                    report,
                    tmp_xlsx.name
                )

                excel_path = tmp_xlsx.name

            with open(
                excel_path,
                "rb"
            ) as f:

                st.download_button(
                    "⬇️ Download Excel",
                    data=f.read(),
                    file_name="compliance_report.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )

    elif not uploaded_files:

        st.info(
            "Upload one or more documents above, then click "
            "**Check Compliance**."
        )


# ============================================================
# TAB 2: INSIGHTS
# ============================================================

with tab_insights:

    history = st.session_state.report_history

    if not history:

        st.info(
            "No compliance checks run yet this session. "
            "Check a bid's documents in the "
            "**Check Compliance** tab to start building insights here."
        )

    else:

        st.subheader(
            f"📊 Insights across {len(history)} bid(s) "
            "checked this session"
        )

        # ---------- Overall compliance breakdown ----------
        overall_counts = Counter(
            r["overall_status"]
            for r in history
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "🟢 Compliant",
            overall_counts.get("Compliant", 0)
        )

        c2.metric(
            "🔴 Non-Compliant",
            overall_counts.get("Non-Compliant", 0)
        )

        c3.metric(
            "🟡 Incomplete",
            overall_counts.get("Incomplete", 0)
        )

        st.divider()

        # ====================================================
        # MOST COMMON REJECTION REASONS
        # ====================================================

        st.markdown(
            "### ❌ Most common rejection reasons"
        )

        reason_counter = Counter()

        for report_item in history:

            for doc in report_item["documents"]:

                for result in doc["results"]:

                    if (
                        not result["passed"]
                        and result["reason"]
                    ):

                        reason_counter[
                            result["reason"]
                        ] += 1

        if reason_counter:

            top_reasons = reason_counter.most_common(10)

            st.bar_chart(
                {
                    reason: count
                    for reason, count in top_reasons
                }
            )

            for reason, count in top_reasons:

                st.write(
                    f"**{count}×** — {reason}"
                )

        else:

            st.write(
                "No rejections recorded yet — every document "
                "checked so far has been valid."
            )

        st.divider()

        # ====================================================
        # DOCUMENT TYPE BREAKDOWN
        # ====================================================

        st.markdown(
            "### 📄 Document status by type"
        )

        doc_type_status = Counter()

        for report_item in history:

            for doc in report_item["documents"]:

                doc_type_status[
                    f"{doc['doc_type']} — {doc['status']}"
                ] += 1

        if doc_type_status:

            st.bar_chart(
                doc_type_status
            )

        st.divider()

        # ====================================================
        # AVERAGE CONFIDENCE TREND
        # ====================================================

        st.markdown(
            "### 📈 Average extraction confidence per bid"
        )

        confidences = []

        for report_item in history:

            confs = [
                d.get("confidence", 1.0)
                for d in report_item["documents"]
                if d["status"] != "Missing"
            ]

            avg = (
                sum(confs) / len(confs)
                if confs
                else 0
            )

            confidences.append(avg)

        st.line_chart(
            confidences
        )

        st.divider()

        # ---------- Clear history ----------
        if st.button("🗑️ Clear session history"):

            st.session_state.report_history = []

            st.rerun()


# ============================================================
# TAB 3: MANAGE RULES
# ============================================================

with tab_rules:

    st.subheader(
        "⚙️ Compliance Rules Editor"
    )

    st.caption(
        "Edit the validation rules below without touching any code. "
        "Changes are validated before saving, and a backup of the "
        "previous version is kept automatically."
    )

    current_rules = read_rules_raw()

    edited_rules = st.text_area(
        "rules.json content",
        value=current_rules,
        height=450,
        help=(
            "Edit format checks, expiry rules, cross-document matches, "
            "or the mandatory document list. Must remain valid JSON."
        ),
    )

    col1, col2 = st.columns([1, 1])

    # ---------- Validate rules ----------
    with col1:

        if st.button("✅ Validate"):

            is_valid, message = validate_rules_json(
                edited_rules
            )

            if is_valid:

                st.success(
                    "Valid! This can be safely saved."
                )

            else:

                st.error(
                    f"Invalid: {message}"
                )

    # ---------- Save rules ----------
    with col2:

        if st.button(
            "💾 Save Rules",
            type="primary"
        ):

            success, message = save_rules(
                edited_rules
            )

            if success:

                st.success(
                    message
                )

                st.rerun()

            else:

                st.error(
                    f"Not saved — {message}"
                )

    st.divider()

    # ========================================================
    # RESTORE BACKUP
    # ========================================================

    st.markdown(
        "### 📦 Restore a previous version"
    )

    backups = list_backups()

    if backups:

        chosen_backup = st.selectbox(
            "Available backups (most recent first)",
            backups
        )

        if st.button(
            "⏪ Restore this backup"
        ):

            success, message = restore_backup(
                chosen_backup
            )

            if success:

                st.success(
                    message
                )

                st.rerun()

            else:

                st.error(
                    message
                )

    else:

        st.write(
            "No backups yet — one will be created automatically "
            "the first time you save a change."
        )