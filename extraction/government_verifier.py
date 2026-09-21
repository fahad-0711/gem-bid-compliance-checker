"""
Simulates verification of extracted document fields against a government
records database. In production, this would call live GST/PAN/MSME
government APIs. For demo purposes, this checks against a curated set of
mock registry records — no real/confidential government data is used.
"""

import json
import os
from rapidfuzz import fuzz

REGISTRY_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "mock_registry")

REGISTRY_FILES = {
    "GST": "gst_registry.json",
    "PAN": "pan_registry.json",
    "MSME": "msme_registry.json",
}

ID_FIELD_BY_TYPE = {
    "GST": "gstin",
    "PAN": "pan_number",
    "MSME": "udyam_number",
}


def _load_registry(doc_type: str) -> list:
    filename = REGISTRY_FILES.get(doc_type)
    if not filename:
        return []
    path = os.path.join(REGISTRY_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def verify_against_government_records(doc_type: str, fields: dict) -> dict:
    id_field = ID_FIELD_BY_TYPE.get(doc_type)
    if not id_field:
        return {"verified": False, "status": "Not Checked",
                "detail": f"No government registry available for {doc_type}"}

    extracted_id = fields.get(id_field)
    if not extracted_id:
        return {"verified": False, "status": "Not Checked",
                "detail": f"No {id_field} was extracted to verify"}

    registry = _load_registry(doc_type)
    extracted_id_clean = extracted_id.replace(" ", "").upper()

    matching_id_records = [
        r for r in registry
        if r.get(id_field, "").replace(" ", "").upper() == extracted_id_clean
    ]

    if not matching_id_records:
        return {
            "verified": False,
            "status": "Not Found",
            "detail": f"No matching {id_field.upper()} found in government records"
        }

    extracted_name = fields.get("business_name") or fields.get("holder_name")

    if extracted_name:
        best_match = None
        best_similarity = 0
        for record in matching_id_records:
            name_field = "business_name" if "business_name" in record else "holder_name"
            record_name = record.get(name_field, "")
            similarity = fuzz.token_sort_ratio(extracted_name.lower(), record_name.lower())
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = record

        if best_similarity >= 85:
            name_field = "business_name" if "business_name" in best_match else "holder_name"
            return {
                "verified": True,
                "status": "Verified",
                "detail": f"Matches government record: {best_match[name_field]} ({best_match.get('status', 'Active')})"
            }
        else:
            return {
                "verified": False,
                "status": "Mismatch",
                "detail": f"{id_field.upper()} found in records, but no matching name among "
                          f"{len(matching_id_records)} record(s) with this ID"
            }

    return {
        "verified": True,
        "status": "Verified",
        "detail": f"Matches government record ({matching_id_records[0].get('status', 'Active')})"
    }