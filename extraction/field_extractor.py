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
UDYAM_PATTERN = r"\bUDYAM[-.\s]*[A-Z]{2}[-.\s]*[0-9]{2}[-.\s]*[0-9]{7}\b"
DATE_PATTERN = r"\b\d{1,2}[-/](?:[A-Za-z]{3}|\d{1,2})[-/]\d{4}\b"
TURNOVER_CERT_PATTERN = r"\bDEMO-TURN-\d{4}\b"
COMPANY_REG_PATTERN = r"\bSAMPLE-COMP-\d{3}\b"

# Words that should never be treated as part of a person's name, even if
# they happen to be capitalized cleanly by OCR (e.g. "Date", "Signature").
# Acts as a safety net alongside the Title-Case shape check below.
_NAME_STOPWORDS = {
    "date", "birth", "signature", "permanent", "account", "number",
    "card", "government", "govt", "india", "income", "tax", "department",
    "name", "sample", "valid", "not", "father's", "fathers",
    "husband's", "husbands",
}

# A real name word (in this pipeline's OCR output) looks like "Rohit" or
# "Kumar" -- one capital letter followed by lowercase letters, nothing
# else. Garbled OCR noise ("fare", "aTtha", "FeaTeR") reliably fails this
# pattern, which is what lets us stop capturing a name WITHOUT a line
# break to anchor on.
_TITLE_CASE_WORD = re.compile(r"^[A-Z][a-z]+$")


def detect_doc_type(text: str) -> str:
    """Guess which document type this is, based on keywords in the text."""
    lower = text.lower()
    if "turnover certificate" in lower or re.search(TURNOVER_CERT_PATTERN, text):
        return "TURNOVER"
    if "company registration certificate" in lower or re.search(COMPANY_REG_PATTERN, text):
        return "COMPANY_REG"
    if "goods and services tax" in lower or "gstin" in lower or "gst registration" in lower:
        return "GST"
    if "udyam registration" in lower or "udyam registration certificate" in lower:
        return "MSME"
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


def _extract_name_after_label(text, label_pattern, exclude_terms=("father", "पिता", "husband", "पति"), max_words=5):
    """
    Return the value following the first label match whose immediate
    local context does NOT also reference an excluded relation
    (father's/husband's name).

    This works whether or not `text` contains real newlines. OCR output
    from ocr_reader.py's _ocr_with_confidence is a single space-joined
    string with NO line breaks at all (every recognized word is joined
    with " "). Text-based PDFs, by contrast, may still have real
    newlines. The previous version of this function located "the current
    line" via text.rfind("\n", ...) / text.find("\n", ...); when no
    newline exists, both calls return -1, which silently expanded "the
    current line" to the ENTIRE document -- so the exclude-term check
    ended up seeing every word in the whole text (including a later,
    unrelated "Father's Name" section), and excluded EVERY match of
    "Name", including the correct one.

    Both the exclusion check and the value boundary below are therefore
    based on a small fixed-size local window and word-shape heuristics
    instead of "\n", so they behave the same way regardless of whether
    the input text has line breaks or not.
    """
    CONTEXT_WINDOW = 40  # characters of local context to inspect, not the whole doc

    for match in re.finditer(label_pattern, text, re.IGNORECASE):
        nearest_newline = text.rfind("\n", 0, match.start())
        context_start = max(nearest_newline + 1, match.start() - CONTEXT_WINDOW, 0)
        local_context = text[context_start:match.start()]

        if any(term in local_context.lower() for term in exclude_terms):
            continue  # this is "Father's Name" / "Husband's Name", not the holder's

        # Walk forward from the label, word by word, collecting only
        # tokens that look like real name components and stopping at the
        # first word that doesn't -- this replaces relying on a newline
        # to know where the name ends, and also stops naturally before
        # hitting the NEXT label if that label survives OCR intact.
        rest_words = text[match.end():].split()
        collected = []
        for word in rest_words[:max_words]:
            stripped = re.sub(r"^\W+|\W+$", "", word)
            if not stripped:
                continue
            if stripped.lower() in exclude_terms or stripped.lower() in _NAME_STOPWORDS:
                break
            if not _TITLE_CASE_WORD.match(stripped):
                break
            collected.append(stripped)

        if not collected:
            continue

        candidate = _clean_name_noise(" ".join(collected))
        if _looks_like_a_name(candidate):
            return candidate
        # otherwise this match produced junk -- keep checking other
        # occurrences of the label rather than returning garbage

    return None
# Labels that can appear after the business name on a GST certificate.
# Used to bound the greedy capture so it stops before running into
# unrelated fields -- critical for OCR text, which has no newlines.
_GST_NAME_STOP_LABELS = [
    "GSTIN", "Registered Address", "Address", "Authorized Signatory",
    "Signature", "Period of Validity", "Date of Issue",
    "State Jurisdiction", "Center Jurisdiction", "Centre Jurisdiction",
    "Type of Registration", "Constitution of Business", "Trade Name",
]


def _extract_business_name_gst(text: str) -> str | None:
    label_match = re.search(r"Legal Name(?:\s+of\s+Business)?\s*:?\s*", text, re.IGNORECASE)
    if not label_match:
        return None

    remainder = text[label_match.end():]
    end = len(remainder)

    newline_pos = remainder.find("\n")
    if newline_pos != -1:
        end = min(end, newline_pos)

    for label in _GST_NAME_STOP_LABELS:
        label_pos = remainder.lower().find(label.lower())
        if label_pos != -1:
            end = min(end, label_pos)

    MAX_NAME_LENGTH = 80
    end = min(end, MAX_NAME_LENGTH)

    candidate = remainder[:end].strip(" :\n\t.-")
    return candidate if candidate else None

def extract_fields(text: str, doc_type: str) -> dict:
    """Pulls out the fields relevant to a given document type."""
    fields = {}

    if doc_type == "GST":
        gstin_match = re.search(GSTIN_PATTERN, text)
        fields["gstin"] = re.sub(r"\s+", "", gstin_match.group()) if gstin_match else None

        # Real certificates use "Legal Name" (sometimes numbered "2. Legal Name"),
        # our own dummy PDFs use "Legal Name of Business" — match either.
        fields["business_name"] = _extract_business_name_gst(text)

        # Real certificates often say "Period of Validity From <date> to Regular"
        # meaning indefinite validity, not a fixed expiry date. Only treat it as
        # an expiry date if the text after "to" actually looks like a date.
        validity_match = re.search(
            r"Period of Validity\s+From\s+" + DATE_PATTERN + r"\s+to\s+(" + DATE_PATTERN + r")",
            text
        )
        if validity_match:
            fields["expiry_date"] = validity_match.group(1)
        else:
            # No fixed end date found (e.g. "to Regular" = indefinite) —
            # don't treat the start date as an expiry date.
            fields["expiry_date"] = None

    elif doc_type == "PAN":
        pan_match = re.search(PAN_PATTERN, text)
        fields["pan_number"] = re.sub(r"\s+", "", pan_match.group()) if pan_match else None

        fields["holder_name"] = _extract_name_after_label(text, r"Name")
    elif doc_type == "TURNOVER":
        cert_match = re.search(TURNOVER_CERT_PATTERN, text)
        fields["certificate_number"] = cert_match.group() if cert_match else None

        name_match = re.search(r"Enterprise Name\s*:?\s*(.+)", text)
        fields["enterprise_name"] = name_match.group(1).strip() if name_match else None

    elif doc_type == "COMPANY_REG":
        reg_match = re.search(COMPANY_REG_PATTERN, text)
        fields["registration_number"] = reg_match.group() if reg_match else None

        name_match = re.search(r"Company Name\s*:?\s*(.+)", text)
        fields["company_name"] = name_match.group(1).strip() if name_match else None

    elif doc_type == "MSME":
        udyam_match = re.search(UDYAM_PATTERN, text)
        if udyam_match:
            raw = udyam_match.group()
            digits_letters = re.sub(r"[^A-Z0-9]", "", raw)  # strips spaces, dots, dashes
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