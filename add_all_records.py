import json
import os
from extraction.pdf_reader import extract_text_from_pdf
from extraction.field_extractor import process_document

PDF_DOCS_DIR = os.path.join("data", "sample_docs", "pdf-docs")
REGISTRY_DIR = os.path.join("data", "mock_registry")

REGISTRY_CONFIG = {
    "GST": {"file": "gst_registry.json", "id_field": "gstin"},
    "PAN": {"file": "pan_registry.json", "id_field": "pan_number"},
    "MSME": {"file": "msme_registry.json", "id_field": "udyam_number"},
    "TURNOVER": {"file": "turnover_registry.json", "id_field": "certificate_number"},
    "COMPANY_REG": {"file": "company_reg_registry.json", "id_field": "registration_number"},
}

NAME_FIELD_CANDIDATES = ["business_name", "holder_name", "enterprise_name", "company_name"]


def load_registry(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_registry(path, records):
    with open(path, "w") as f:
        json.dump(records, f, indent=2)


def main():
    registries = {
        doc_type: load_registry(os.path.join(REGISTRY_DIR, cfg["file"]))
        for doc_type, cfg in REGISTRY_CONFIG.items()
    }

    added, skipped_existing, skipped_no_id, unrecognized = [], [], [], []

    for person_folder in sorted(os.listdir(PDF_DOCS_DIR)):
        folder_path = os.path.join(PDF_DOCS_DIR, person_folder)
        if not os.path.isdir(folder_path):
            continue

        for filename in sorted(os.listdir(folder_path)):
            if not filename.lower().endswith(".pdf"):
                continue

            file_path = os.path.join(folder_path, filename)
            text = extract_text_from_pdf(file_path)
            result = process_document(filename, text)

            doc_type = result.get("doc_type")
            fields = result.get("fields", {})

            if doc_type not in REGISTRY_CONFIG:
                unrecognized.append(filename)
                continue

            cfg = REGISTRY_CONFIG[doc_type]
            id_field = cfg["id_field"]
            id_value = fields.get(id_field)

            if not id_value:
                skipped_no_id.append(filename)
                continue

            id_clean = id_value.replace(" ", "").upper()
            already_present = any(
                r.get(id_field, "").replace(" ", "").upper() == id_clean
                for r in registries[doc_type]
            )
            if already_present:
                skipped_existing.append(f"{doc_type}: {id_value}")
                continue

            name_value, name_field_used = None, None
            for candidate in NAME_FIELD_CANDIDATES:
                if fields.get(candidate):
                    name_value, name_field_used = fields[candidate], candidate
                    break

            new_entry = {id_field: id_value, "status": "Active"}
            if name_value:
                new_entry[name_field_used] = name_value

            registries[doc_type].append(new_entry)
            added.append(f"{doc_type}: {new_entry}")

    for doc_type, cfg in REGISTRY_CONFIG.items():
        save_registry(os.path.join(REGISTRY_DIR, cfg["file"]), registries[doc_type])

    print(f"Added {len(added)} new record(s):")
    for line in added:
        print("  +", line)
    if skipped_existing:
        print(f"\nSkipped {len(skipped_existing)} already-present:")
        for line in skipped_existing:
            print("  =", line)
    if skipped_no_id:
        print(f"\nSkipped {len(skipped_no_id)} file(s) with no extracted ID:")
        for line in skipped_no_id:
            print("  ?", line)
    if unrecognized:
        print(f"\n{len(unrecognized)} file(s) had unrecognized doc_type:")
        for line in unrecognized:
            print("  !", line)


if __name__ == "__main__":
    main()