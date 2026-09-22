"""
Simulates verification of extracted document fields against a government
records database. In production, this would call live GST/PAN/MSME
government APIs. For demo purposes, this checks against a curated set of
mock registry records — no real/confidential government data is used.
"""

import json
import os
import re
from rapidfuzz import fuzz


REGISTRY_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "mock_registry"
)


# ---------------------------------------------------------
# Registry files for each document type
# ---------------------------------------------------------
REGISTRY_FILES = {
    "GST": "gst_registry.json",
    "PAN": "pan_registry.json",
    "MSME": "msme_registry.json",
    "TURNOVER": "turnover_registry.json",
    "COMPANY_REG": "company_reg_registry.json",
}


# ---------------------------------------------------------
# ID field used to search each registry
# ---------------------------------------------------------
ID_FIELD_BY_TYPE = {
    "GST": "gstin",
    "PAN": "pan_number",
    "MSME": "udyam_number",
    "TURNOVER": "certificate_number",
    "COMPANY_REG": "registration_number",
}


# ---------------------------------------------------------
# Possible name fields across all document types
# ---------------------------------------------------------
NAME_FIELD_CANDIDATES = [
    "business_name",
    "holder_name",
    "enterprise_name",
    "company_name"
]


# ---------------------------------------------------------
# Legal-suffix / punctuation noise stripped before comparing names
# ---------------------------------------------------------
_LEGAL_SUFFIXES = [
    r'\bpvt\b', r'\bprivate\b', r'\bltd\b', r'\blimited\b',
    r'\bllp\b', r'\binc\b', r'\bcorp\b', r'\bcorporation\b',
    r'\benterprises\b', r'\btechnologies\b', r'\bsolutions\b',
]


def normalize_business_name(name: str) -> str:
    """
    Lowercases, strips punctuation, removes common legal suffixes, and
    collapses whitespace so that names like 'Aarav Digital Solutions
    Pvt. Ltd.' and 'ARAAV DIGITAL SOLUTIONS PRIVATE LIMITED' compare equal.
    """

    if not name:
        return ""

    normalized = name.lower()
    normalized = re.sub(r'[.,]', '', normalized)

    for suffix in _LEGAL_SUFFIXES:
        normalized = re.sub(suffix, '', normalized)

    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def _load_registry(doc_type: str) -> list:
    """
    Loads the mock registry JSON file for the given document type.
    """

    filename = REGISTRY_FILES.get(doc_type)

    if not filename:
        return []

    path = os.path.join(REGISTRY_DIR, filename)

    if not os.path.exists(path):
        return []

    with open(path, "r") as f:
        return json.load(f)


def _get_name_from_fields(fields: dict) -> str | None:
    """
    Finds whichever name-like field is present in the extracted fields.
    """

    for field_name in NAME_FIELD_CANDIDATES:
        if fields.get(field_name):
            return fields[field_name]

    return None


def _get_name_field_in_record(record: dict) -> str | None:
    """
    Finds which name-like field exists in a registry record.
    """

    for field_name in NAME_FIELD_CANDIDATES:
        if field_name in record:
            return field_name

    return None


def verify_against_government_records(doc_type: str, fields: dict) -> dict:
    """
    Checks extracted fields against the mock government registry.

    Returns:
    {
        "verified": bool,
        "status": "Verified" | "Not Found" | "Mismatch" | "Not Checked",
        "detail": str
    }
    """

    # ---------------------------------------------------------
    # 1. Find the ID field for the document type
    # ---------------------------------------------------------
    id_field = ID_FIELD_BY_TYPE.get(doc_type)

    if not id_field:
        return {
            "verified": False,
            "status": "Not Checked",
            "detail": f"No government registry available for {doc_type}"
        }

    # ---------------------------------------------------------
    # 2. Get extracted document ID
    # ---------------------------------------------------------
    extracted_id = fields.get(id_field)

    if not extracted_id:
        return {
            "verified": False,
            "status": "Not Checked",
            "detail": f"No {id_field} was extracted to verify"
        }

    # ---------------------------------------------------------
    # 3. Load registry
    # ---------------------------------------------------------
    registry = _load_registry(doc_type)

    extracted_id_clean = (
        extracted_id
        .replace(" ", "")
        .upper()
    )

    # ---------------------------------------------------------
    # 4. Find records with matching ID
    # ---------------------------------------------------------
    matching_id_records = [
        record
        for record in registry
        if record.get(id_field, "")
        .replace(" ", "")
        .upper() == extracted_id_clean
    ]

    # ---------------------------------------------------------
    # 5. ID not found
    # ---------------------------------------------------------
    if not matching_id_records:
        return {
            "verified": False,
            "status": "Not Found",
            "detail": (
                f"No matching {id_field.upper()} "
                f"found in government records"
            )
        }

    # ---------------------------------------------------------
    # 6. Get extracted name
    #
    # Supports:
    # business_name
    # holder_name
    # enterprise_name
    # company_name
    # ---------------------------------------------------------
    extracted_name = (
        fields.get("business_name")
        or fields.get("holder_name")
        or fields.get("enterprise_name")
        or fields.get("company_name")
    )

    # ---------------------------------------------------------
    # 7. Compare name with registry record
    # ---------------------------------------------------------
    if extracted_name:

        best_match = None
        best_name_field = None
        best_similarity = 0

        normalized_extracted = normalize_business_name(extracted_name)

        for record in matching_id_records:

            # Find whichever name field exists in this record
            name_field = next(
                (
                    field
                    for field in [
                        "business_name",
                        "holder_name",
                        "enterprise_name",
                        "company_name"
                    ]
                    if field in record
                ),
                None
            )

            if not name_field:
                continue

            record_name = record.get(name_field, "")
            normalized_record = normalize_business_name(record_name)
            print(f"DEBUG — extracted: {normalized_extracted!r} | registry: {normalized_record!r}")
            similarity = fuzz.token_set_ratio(
                normalized_extracted,
                normalized_record
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = record
                best_name_field = name_field

        # -----------------------------------------------------
        # 8. Name matches
        # -----------------------------------------------------
        if best_similarity >= 80 and best_match:

            return {
                "verified": True,
                "status": "Verified",
                "detail": (
                    f"Matches government record: "
                    f"{best_match[best_name_field]} "
                    f"({best_match.get('status', 'Active')})"
                )
            }

        # -----------------------------------------------------
        # 9. ID exists but name does not match
        # -----------------------------------------------------
        else:

            return {
                "verified": False,
                "status": "Mismatch",
                "detail": (
                    f"{id_field.upper()} found in records, "
                    f"but no matching name among "
                    f"{len(matching_id_records)} record(s) "
                    f"with this ID (best similarity: {best_similarity}%)"
                )
            }

    # ---------------------------------------------------------
    # 10. ID matched but no name was extracted
    # ---------------------------------------------------------
    return {
        "verified": True,
        "status": "Verified",
        "detail": (
            f"Matches government record "
            f"({matching_id_records[0].get('status', 'Active')})"
        )
    }