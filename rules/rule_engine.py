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
    all_documents = {doc["doc_type"]: doc for doc in extracted_docs}
    document_reports = [
        validate_document(doc, rules, all_documents) for doc in extracted_docs
    ]
    document_reports += check_missing_documents(list(all_documents.keys()), rules)

    overall_status = "Compliant"
    for report in document_reports:
        if report["status"] in ("Invalid", "Missing"):
            overall_status = "Non-Compliant"
            break
        if report["status"] == "Needs Review" and overall_status == "Compliant":
            overall_status = "Incomplete"

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