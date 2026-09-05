"""
Extracts structured fields (GSTIN, PAN, dates, names) from raw document text
using regex, and packages the result into the ExtractedDocument shape
defined in schema.py.
"""

import re
import os
from datetime import datetime

# Regex patterns for each field type
GSTIN_PATTERN = r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b"
PAN_PATTERN = r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"
UDYAM_PATTERN = r"\bUDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}\b"
DATE_PATTERN = r"\b\d{1,2}[-/](?:[A-Za-z]{3}|\d{1,2})[-/]\d{4}\b"


def detect_doc_type(text: str) -> str:
    """Guess which document type this is, based on keywords in the text."""
    lower = text.lower()
    if "udyam" in lower or "msme" in lower:
        return "MSME"
    if "goods and services tax" in lower or "gstin" in lower:
        return "GST"
    if "permanent account number" in lower or re.search(PAN_PATTERN, text):
        return "PAN"
    return "UNKNOWN"


def extract_dates(text: str) -> list[str]:
    return re.findall(DATE_PATTERN, text)


def extract_fields(text: str, doc_type: str) -> dict:
    """Pulls out the fields relevant to a given document type."""
    fields = {}

    if doc_type == "GST":
        gstin_match = re.search(GSTIN_PATTERN, text)
        fields["gstin"] = gstin_match.group() if gstin_match else None

        name_match = re.search(r"Legal Name of Business\s*\n?\s*(.+)", text)
        fields["business_name"] = name_match.group(1).strip() if name_match else None

        dates = extract_dates(text)
        fields["expiry_date"] = dates[-1] if dates else None  # last date = "valid until"

    elif doc_type == "PAN":
        pan_match = re.search(PAN_PATTERN, text)
        fields["pan_number"] = pan_match.group() if pan_match else None

        name_match = re.search(r"Name\s*\n?\s*(.+)", text)
        fields["holder_name"] = name_match.group(1).strip() if name_match else None

    elif doc_type == "MSME":
        udyam_match = re.search(UDYAM_PATTERN, text)
        fields["udyam_number"] = udyam_match.group() if udyam_match else None

        category_match = re.search(r"Category\s*\n?\s*(\w+)", text)
        fields["category"] = category_match.group(1).strip() if category_match else None

        dates = extract_dates(text)
        fields["expiry_date"] = dates[-1] if dates else None

    return fields


def estimate_confidence(fields: dict) -> float:
    """
    Simple confidence heuristic: what fraction of expected fields
    were successfully extracted (not None)?
    """
    if not fields:
        return 0.0
    found = sum(1 for v in fields.values() if v is not None)
    return round(found / len(fields), 2)


def process_document(file_path: str, raw_text: str) -> dict:
    """
    Main entry point: takes raw extracted text and returns a dict
    matching the ExtractedDocument shape from schema.py.
    """
    doc_type = detect_doc_type(raw_text)
    fields = extract_fields(raw_text, doc_type)
    confidence = estimate_confidence(fields)

    return {
        "doc_type": doc_type,
        "file_name": os.path.basename(file_path),
        "raw_text": raw_text,
        "fields": fields,
        "confidence": confidence,
    }


if __name__ == "__main__":
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from extraction.pdf_reader import extract_text_from_pdf, is_text_based_pdf
    from extraction.ocr_reader import extract_text_via_ocr

    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"

    if is_text_based_pdf(path):
        text = extract_text_from_pdf(path)
    else:
        text, _ = extract_text_via_ocr(path)

    result = process_document(path, text)
    import json
    print(json.dumps(result, indent=2))