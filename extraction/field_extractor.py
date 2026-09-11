"""
Extracts structured fields (GSTIN, PAN, dates, names) from raw document text
using regex, and packages the result into the ExtractedDocument shape
defined in schema.py.
"""

import re
import os
from datetime import datetime

# Regex patterns for each field type
GSTIN_PATTERN = r"\b[0-9]{2}\s?[A-Z]{5}\s?[0-9]{4}\s?[A-Z]{1}\s?[1-9A-Z]{1}\s?Z\s?[0-9A-Z]{1}\b"
PAN_PATTERN = r"\b[A-Z]{5}\s?[0-9]{4}\s?[A-Z]{1}\b"
UDYAM_PATTERN = r"\bUDYAM[-.]?[A-Z]{2}[-.]?[0-9]{2}[-.]?[0-9]{7}\b"
DATE_PATTERN = r"\b\d{1,2}[-/](?:[A-Za-z]{3}|\d{1,2})[-/]\d{4}\b"


def detect_doc_type(text: str) -> str:
    """Guess which document type this is, based on keywords in the text."""
    lower = text.lower()
    if "udyam" in lower or "msme" in lower:
        return "MSME"
    if "goods and services tax" in lower or "gstin" in lower:
        return "GST"
    if ("permanent account number" in lower
            or "income tax department" in lower
            or re.search(PAN_PATTERN, text)):
        return "PAN"
    return "UNKNOWN"


def extract_dates(text: str) -> list[str]:
    return re.findall(DATE_PATTERN, text)


def _looks_like_a_name(s: str) -> bool:
    """
    Quick sanity check: does this string look like a real name, or is it
    likely OCR noise (stray characters, a single short garbled token)?
    Requires at least 4 characters and a run of 3+ letters somewhere.
    """
    return len(s) >= 4 and bool(re.search(r"[A-Za-z]{3,}", s))

def _clean_name_noise(name: str) -> str:
    """
    Light cleanup for common OCR artifacts in extracted names: trailing
    short noise tokens (1-2 lowercase letters stuck on the end) and stray
    punctuation. This doesn't guarantee a perfect name, but removes the
    most common junk without risking over-correction.
    """
    name = re.sub(r"\s+[a-z]{1,3}$", "", name)
    name = name.replace("!", "I")
    return name.strip()


def _extract_name_after_label(text, label_pattern, exclude_terms=("father", "पिता", "husband", "पति")):
    """
    Return the value following the first label match whose own line
    does NOT also reference an excluded relation (father's/husband's name).
    """
    for match in re.finditer(label_pattern, text, re.IGNORECASE):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line_end = line_end if line_end != -1 else len(text)
        line = text[line_start:line_end]

        if any(term in line.lower() for term in exclude_terms):
            continue  # this is "Father's Name" / "Husband's Name", not the holder's

        rest = text[match.end():]
        value_match = re.search(r"\n?\s*(.+)", rest)
        if value_match:
            return value_match.group(1).strip()

    return None

def extract_fields(text: str, doc_type: str) -> dict:
    """Pulls out the fields relevant to a given document type."""
    fields = {}

    if doc_type == "GST":
        gstin_match = re.search(GSTIN_PATTERN, text)
        fields["gstin"] = re.sub(r"\s+", "", gstin_match.group()) if gstin_match else None

        name_match = re.search(r"Legal Name of Business\s*\n?\s*(.+)", text)
        fields["business_name"] = name_match.group(1).strip() if name_match else None

        dates = extract_dates(text)
        fields["expiry_date"] = dates[-1] if dates else None  # last date = "valid until"

    elif doc_type == "PAN":
        pan_match = re.search(PAN_PATTERN, text)
        fields["pan_number"] = re.sub(r"\s+", "", pan_match.group()) if pan_match else None

        fields["holder_name"] = _extract_name_after_label(text, r"Name")

    elif doc_type == "MSME":
        udyam_match = re.search(UDYAM_PATTERN, text)
        if udyam_match:
            raw = udyam_match.group()
            # Normalize OCR punctuation confusion (., missing separators)
            # back into the canonical UDYAM-XX-00-0000000 format
            digits_letters = re.sub(r"[^A-Z0-9]", "", raw)  # strip all separators
            if digits_letters.startswith("UDYAM") and len(digits_letters) == 16:
                fields["udyam_number"] = (
                    f"UDYAM-{digits_letters[5:7]}-{digits_letters[7:9]}-{digits_letters[9:]}"
                )
            else:
                fields["udyam_number"] = raw
        else:
            fields["udyam_number"] = None

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