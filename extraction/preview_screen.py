"""
preview_screen.py

The "extracted data preview" step: after a file is uploaded and text is
pulled out (via file_router.extract_text), show the officer a clean
table of what was extracted - BEFORE running it through the rule
engine. They can fix an obvious OCR misread (e.g. a '0' read as 'O')
before it causes a wrong Invalid/Missing result.

This does NOT replace field_extractor.py or the rule engine - it's a
new step that sits between them:

    upload -> file_router.extract_text()
           -> field_extractor.extract_fields()   (existing)
           -> preview_screen.render()             <-- NEW, this file
           -> (officer confirms / edits)
           -> rule_engine.validate()              (existing, unchanged)

Integration into your app.py:

    from file_router import extract_text
    from field_extractor import extract_fields   # your existing module
    from preview_screen import render_extraction_preview

    uploaded_file = st.file_uploader(
        "Upload document",
        type=["pdf", "docx", "jpg", "jpeg", "png"],
    )

    if uploaded_file:
        temp_path = save_uploaded_file(uploaded_file)   # your existing helper
        extraction = extract_text(temp_path)
        fields = extract_fields(extraction["text"])     # -> dict of field:value

        confirmed_fields = render_extraction_preview(
            fields=fields,
            source_format=extraction["source_format"],
            extraction_method=extraction["extraction_method"],
        )

        if confirmed_fields is not None:
            # user clicked "Confirm & Validate" - proceed as normal
            report = run_rule_engine(confirmed_fields)   # your existing call
            display_results(report)                      # your existing UI
"""

import streamlit as st


def render_extraction_preview(
    fields: dict,
    source_format: str,
    extraction_method: str,
    confidence_scores: dict = None,
) -> dict | None:
    """
    Render an editable preview table of extracted fields and return the
    (possibly edited) fields once the officer confirms, or None if
    they haven't confirmed yet (so app.py knows not to run validation
    on this Streamlit rerun).

    Args:
        fields: {"GSTIN": "27ABCPL1234F1Z5", "Legal Name": "...", ...}
                as produced by your existing field_extractor.py.
        source_format: "pdf" | "docx" | "image" - shown to the officer
                so they know how the file was processed.
        extraction_method: "pdfplumber" | "ocr" | "docx" - shown next
                to low-confidence fields as a hint about why a field
                might be wrong (OCR is more error-prone than pdfplumber
                or docx text extraction).
        confidence_scores: optional {"GSTIN": 0.92, ...} matching your
                existing confidence-score feature. Fields below 0.75
                are visually flagged for a closer look.

    Returns:
        The confirmed (possibly edited) fields dict, once the officer
        clicks "Confirm & Validate". Returns None on every rerun before
        that click, so the calling code knows to keep showing this
        screen instead of proceeding to validation.
    """
    st.subheader("📄 Extracted Data — Please Confirm")
    st.caption(
        f"Read via **{extraction_method.upper()}** from a **{source_format.upper()}** "
        f"file. Please check the fields below before running compliance checks."
    )

    if extraction_method == "ocr":
        st.info(
            "This document was read using OCR (scanned/image input). "
            "OCR can misread characters — please double-check fields marked ⚠️ below."
        )

    edited_fields = {}
    low_confidence_fields = []

    for field_name, field_value in fields.items():
        confidence = None
        if confidence_scores:
            confidence = confidence_scores.get(field_name)

        is_low_confidence = confidence is not None and confidence < 0.75
        label = f"⚠️ {field_name}" if is_low_confidence else field_name

        if is_low_confidence:
            low_confidence_fields.append(field_name)

        edited_value = st.text_input(
            label,
            value=field_value or "",
            key=f"preview_{field_name}",
            help=(
                f"Confidence: {confidence:.0%} — please verify this value."
                if is_low_confidence
                else None
            ),
        )
        edited_fields[field_name] = edited_value

    if low_confidence_fields:
        st.warning(
            f"{len(low_confidence_fields)} field(s) had low extraction "
            f"confidence and are marked with ⚠️ above — please verify "
            f"them before continuing: {', '.join(low_confidence_fields)}"
        )

    col1, col2 = st.columns([1, 4])
    with col1:
        confirmed = st.button("✅ Confirm & Validate", type="primary")
    with col2:
        st.caption("Edits above are used for validation once you confirm.")

    if confirmed:
        return edited_fields

    return None
