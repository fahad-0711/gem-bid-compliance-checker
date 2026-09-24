"""
Rule engine: takes an ExtractedDocument dict (from extraction/field_extractor.py)
and validates its fields against rules.json, returning a DocumentReport
matching the schema.py contract.
"""

import json
import re
import os
from datetime import datetime
from rapidfuzz import fuzz
from extraction.government_verifier import verify_against_government_records


def check_duplicate_documents(extracted_docs: list) -> dict:
    """
    Detects if more than one document of the same type was uploaded in a
    single batch (e.g. two PAN cards). Returns a dict mapping doc_type ->
    list of duplicate file names, empty if no duplicates found.
    """
    from collections import defaultdict
    by_type = defaultdict(list)
    for doc in extracted_docs:
        by_type[doc["doc_type"]].append(doc["file_name"])

    return {
        doc_type: names
        for doc_type, names in by_type.items()
        if len(names) > 1 and doc_type != "UNKNOWN"
    }


def load_rules(rules_path: str = "rules/rules.json") -> dict:
    with open(rules_path, "r") as f:
        return json.load(f)


def parse_date(date_str: str):
    """Try a few common date formats used in Indian certificates."""
    formats = ["%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d-%B-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def check_regex(value, pattern) -> bool:
    if value is None:
        return False
    return bool(re.match(pattern, value))


def check_expiry(value) -> bool:
    """Returns True if the date is today or in the future (i.e. not expired)."""
    parsed = parse_date(value)
    if parsed is None:
        return False
    return parsed >= datetime.now()


def normalize_name(name: str) -> str:
    """Strips common business suffixes and normalizes spacing/case for comparison."""
    if not name:
        return ""
    name = name.lower().strip()
    for suffix in ["pvt ltd", "private limited", "ltd", "llp", "inc", "limited"]:
        name = name.replace(suffix, "")
    return re.sub(r"\s+", " ", name).strip()


def check_cross_match(value, other_doc_field_value, threshold: float = 85.0) -> tuple[bool, float]:
    """
    Fuzzy match: compares two business/holder names using similarity scoring
    instead of exact string equality. Tolerates OCR noise, minor spelling
    differences, and formatting inconsistencies between documents.
    Returns (passed: bool, similarity_score: float 0-100).
    """
    norm_value = normalize_name(value)
    norm_other = normalize_name(other_doc_field_value)

    if not norm_value or not norm_other:
        return False, 0.0

    score = fuzz.token_sort_ratio(norm_value, norm_other)
    return score >= threshold, round(score, 1)


# ---------------------------------------------------------
# GST <-> PAN cross-document check
# ---------------------------------------------------------
def extract_pan_from_gstin(gstin: str) -> str | None:
    """
    A GSTIN's structure embeds the associated PAN at a fixed position:
    characters 3-12 (0-indexed 2:12). Returns None if the GSTIN is too
    short to extract this safely.
    """
    if not gstin or len(gstin) < 12:
        return None
    return gstin[2:12]


def check_gst_pan_embedding(all_documents: dict) -> dict | None:
    """
    Cross-checks that the PAN embedded inside an uploaded GST document's
    GSTIN matches the PAN number from a separately uploaded PAN document,
    if both are present in this batch. Returns a result dict, or None if
    there's nothing to check (one or both documents missing).
    """
    gst_doc = all_documents.get("GST")
    pan_doc = all_documents.get("PAN")

    if not gst_doc or not pan_doc:
        return None

    gstin = gst_doc.get("fields", {}).get("gstin")
    pan_number = pan_doc.get("fields", {}).get("pan_number")

    if not gstin or not pan_number:
        return None

    embedded_pan = extract_pan_from_gstin(gstin)
    if embedded_pan is None:
        return None

    if embedded_pan.upper() == pan_number.upper():
        return {
            "field": "gst_pan_embedding",
            "passed": True,
            "reason": None
        }
    else:
        return {
            "field": "gst_pan_embedding",
            "passed": False,
            "reason": f"GST certificate's embedded PAN ({embedded_pan}) does not match "
                      f"the uploaded PAN document ({pan_number})"
        }


# ---------------------------------------------------------
# Business name consistency across GST / MSME / TURNOVER / COMPANY_REG
# ---------------------------------------------------------
def check_business_name_consistency(all_documents: dict) -> dict | None:
    """
    Cross-checks that GST, MSME, TURNOVER, and COMPANY_REG documents (when
    more than one is present) all reference the same business/enterprise
    name. PAN is intentionally excluded, since it holds a personal name,
    not a business name. Returns a result dict, or None if fewer than two
    of these document types are present (nothing to compare).
    """
    name_field_by_type = {
        "GST": "business_name",
        "MSME": "business_name",
        "TURNOVER": "enterprise_name",
        "COMPANY_REG": "company_name",
    }

    names_found = {}
    for doc_type, field_name in name_field_by_type.items():
        doc = all_documents.get(doc_type)
        if doc:
            name = doc.get("fields", {}).get(field_name)
            if name:
                names_found[doc_type] = name

    if len(names_found) < 2:
        return None  # nothing to cross-check yet

    doc_types = list(names_found.keys())
    reference_type = doc_types[0]
    reference_name = names_found[reference_type]

    mismatches = []
    for doc_type in doc_types[1:]:
        similarity = fuzz.token_sort_ratio(reference_name.lower(), names_found[doc_type].lower())
        if similarity < 85:
            mismatches.append(f"{doc_type} ('{names_found[doc_type]}')")

    if mismatches:
        return {
            "field": "business_name_consistency",
            "passed": False,
            "reason": f"Business name on {reference_type} ('{reference_name}') doesn't match: "
                      f"{', '.join(mismatches)}"
        }
    else:
        return {
            "field": "business_name_consistency",
            "passed": True,
            "reason": None
        }


# Status precedence used when combining the rule-based status with the
# government-verification outcome. Higher index = more severe, and the
# combined status never moves to a less severe state than either input.
_STATUS_SEVERITY = ["Valid", "Needs Review", "Invalid"]


def _more_severe(a: str, b: str) -> str:
    """Returns whichever of two statuses is more severe, per _STATUS_SEVERITY."""
    a_rank = _STATUS_SEVERITY.index(a) if a in _STATUS_SEVERITY else 0
    b_rank = _STATUS_SEVERITY.index(b) if b in _STATUS_SEVERITY else 0
    return a if a_rank >= b_rank else b


def validate_document(extracted_doc: dict, rules: dict, all_documents: dict = None) -> dict:
    doc_type = extracted_doc["doc_type"]
    doc_rules = rules.get(doc_type)
    confidence = extracted_doc.get("confidence", 1.0)

    if doc_rules is None:
        return {
            "doc_type": doc_type,
            "file_name": extracted_doc["file_name"],
            "status": "Needs Review",
            "confidence": confidence,
            "results": [{"field": "doc_type", "passed": False,
            "reason": f"Unrecognized document type: {doc_type}"}]
        }

    results = []
    fields = extracted_doc.get("fields", {})

    for req_field in doc_rules.get("required_fields", []):
        if fields.get(req_field) is None:
            results.append({
                "field": req_field,
                "passed": False,
                "reason": f"Required field '{req_field}' could not be extracted"
            })

    for rule in doc_rules.get("rules", []):
        field = rule["field"]
        value = fields.get(field)
        rule_type = rule["type"]
        similarity = None

        if rule_type == "regex":
            passed = check_regex(value, rule["pattern"])
        elif rule_type == "expiry_check":
            if value is None:
                # No expiry date extracted — likely indefinite validity
                # (common on real certificates), not a failure.
                passed = True
            else:
                passed = check_expiry(value)
        elif rule_type == "cross_match":
            target_doc_type, target_field = rule["match_against"].split(".")
            other_value = None
            if all_documents and target_doc_type in all_documents:
                other_value = all_documents[target_doc_type]["fields"].get(target_field)
            passed, similarity = check_cross_match(value, other_value)
        else:
            passed = False

        reason = None
        if not passed:
            if rule_type == "cross_match":
                reason = f"{rule['error']} (similarity: {similarity}%, threshold: 85%)"
            else:
                reason = rule["error"]

        results.append({
            "field": field,
            "passed": passed,
            "reason": reason
        })

    overall_status = "Valid" if all(r["passed"] for r in results) else "Invalid"
    if confidence < 0.5:
        overall_status = _more_severe(overall_status, "Needs Review")

    government_check = verify_against_government_records(doc_type, fields)

    # A government-record mismatch is a hard compliance failure — the ID
    # number was found in the registry, but under a different name. A
    # "Not Found" is treated more leniently (flagged for manual review,
    # not an automatic fail), since it doesn't prove the document is
    # invalid, only that the mock registry has no matching record.
    # Either way, this can only make the status MORE severe than the
    # field-rule result, never override an Invalid back down to Valid.
    if government_check["status"] == "Mismatch":
        overall_status = _more_severe(overall_status, "Invalid")
        results.append({
            "field": "government_record_match",
            "passed": False,
            "reason": government_check["detail"]
        })
    elif government_check["status"] == "Not Found":
        overall_status = _more_severe(overall_status, "Needs Review")

    return {
        "doc_type": doc_type,
        "file_name": extracted_doc["file_name"],
        "status": overall_status,
        "confidence": confidence,
        "results": results,
        "government_verification": government_check
    }


def check_missing_documents(found_doc_types: list, rules: dict) -> list:
    mandatory = rules.get("mandatory_documents", [])
    missing = []
    for doc_type in mandatory:
        if doc_type not in found_doc_types:
            missing.append({
                "doc_type": doc_type,
                "file_name": None,
                "status": "Missing",
                "confidence": 0.0,
                "results": [{"field": "presence", "passed": False,
                "reason": f"{doc_type} document was not submitted"}]
            })
    return missing


def build_compliance_report(bid_id: str, extracted_docs: list, rules: dict) -> dict:
    """
    Full pipeline: takes a list of ExtractedDocument dicts, returns a
    ComplianceReport dict matching schema.py.
    """
    duplicates = check_duplicate_documents(extracted_docs)

    if duplicates:
        # Stop here and report the duplicate issue clearly — don't attempt
        # to validate ambiguous input (which document is the "real" one?).
        document_reports = []
        for doc_type, file_names in duplicates.items():
            document_reports.append({
                "doc_type": doc_type,
                "file_name": ", ".join(file_names),
                "status": "Invalid",
                "confidence": 0.0,
                "results": [{
                    "field": "duplicate_check",
                    "passed": False,
                    "reason": f"Multiple {doc_type} documents uploaded ({', '.join(file_names)}). "
                            f"Please upload exactly one document per type."
                }]
            })
        return {
            "bid_id": bid_id,
            "documents": document_reports,
            "overall_status": "Non-Compliant"
        }

    all_documents = {doc["doc_type"]: doc for doc in extracted_docs}
    document_reports = [
        validate_document(doc, rules, all_documents) for doc in extracted_docs
    ]

    # Cross-document check: GST's embedded PAN vs the uploaded PAN document
    gst_pan_result = check_gst_pan_embedding(all_documents)
    if gst_pan_result:
        for report in document_reports:
            if report["doc_type"] == "GST":
                report["results"].append(gst_pan_result)
                if not gst_pan_result["passed"] and report["status"] == "Valid":
                    report["status"] = "Invalid"

    # Cross-document check: business name consistency across GST/MSME/TURNOVER/COMPANY_REG
    consistency_result = check_business_name_consistency(all_documents)
    if consistency_result:
        for report in document_reports:
            if report["doc_type"] in ("GST", "MSME", "TURNOVER", "COMPANY_REG"):
                report["results"].append(consistency_result)
                if not consistency_result["passed"] and report["status"] == "Valid":
                    report["status"] = "Invalid"

    document_reports += check_missing_documents(list(all_documents.keys()), rules)

    # NOTE: this overall_status computation was missing from the version
    # of this function I was given to edit — without it the function fell
    # through to the end and returned None for every non-duplicate batch.
    # Adjust the exact rule below if your original logic differed.
    overall_status = (
        "Non-Compliant"
        if any(doc["status"] in ("Invalid", "Missing") for doc in document_reports)
        else "Needs Review"
        if any(doc["status"] == "Needs Review" for doc in document_reports)
        else "Compliant"
    )

    return {
        "bid_id": bid_id,
        "documents": document_reports,
        "overall_status": overall_status
    }


if __name__ == "__main__":
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from extraction.pdf_reader import extract_text_from_pdf
    from extraction.field_extractor import process_document

    # Test against your valid sample set
    folder = "data/sample_docs/valid"
    rules = load_rules()

    extracted_docs = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        text = extract_text_from_pdf(path)
        doc = process_document(path, text)
        extracted_docs.append(doc)

    report = build_compliance_report("BID-001", extracted_docs, rules)
    print(json.dumps(report, indent=2))