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
    """
    Checks extracted fields against the mock government registry.
    Returns a dict describing the verification outcome:
    {
        "verified": bool,
        "status": "Verified" | "Not Found" | "Mismatch" | "Not Checked",
        "detail": str
    }
    """
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

    for record in registry:
        record_id = record.get(id_field, "").replace(" ", "").upper()
        if record_id == extracted_id_clean:
            # ID matches a record — now check the name field also matches
            name_field = "business_name" if "business_name" in record else "holder_name"
            extracted_name = fields.get(name_field) or fields.get("business_name") or fields.get("holder_name")
            record_name = record.get(name_field, "")

            if extracted_name:
                similarity = fuzz.token_sort_ratio(extracted_name.lower(), record_name.lower())
                if similarity >= 85:
                    return {
                        "verified": True,
                        "status": "Verified",
                        "detail": f"Matches government record: {record_name} ({record.get('status', 'Active')})"
                    }
                else:
                    return {
                        "verified": False,
                        "status": "Mismatch",
                        "detail": f"{id_field.upper()} found in records, but name doesn't match "
                                  f"(record shows '{record_name}')"
                    }
            return {
                "verified": True,
                "status": "Verified",
                "detail": f"Matches government record ({record.get('status', 'Active')})"
            }

    return {
        "verified": False,
        "status": "Not Found",
        "detail": f"No matching {id_field.upper()} found in government records"
    }