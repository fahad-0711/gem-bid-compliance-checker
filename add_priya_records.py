import json
import os

REGISTRY_DIR = os.path.join("data", "mock_registry")

entries_to_add = {
    "gst_registry.json": {
        "gstin": "21FGHJI5678K1Z5",
        "business_name": "Priya Singh",
        "status": "Active",
    },
    "company_reg_registry.json": {
        "registration_number": "TS/PROP/2021/00102",
        "company_name": "Priya Singh",
        "status": "Active",
    },
    "turnover_registry.json": {
        "certificate_number": "TC/2025/0502",
        "enterprise_name": "Priya Singh",
        "status": "Active",
    },
}

id_field_by_file = {
    "gst_registry.json": "gstin",
    "company_reg_registry.json": "registration_number",
    "turnover_registry.json": "certificate_number",
}

for filename, new_entry in entries_to_add.items():
    path = os.path.join(REGISTRY_DIR, filename)

    with open(path, "r") as f:
        records = json.load(f)

    id_field = id_field_by_file[filename]
    new_id = new_entry[id_field]

    already_present = any(
        r.get(id_field, "").replace(" ", "").upper() == new_id.replace(" ", "").upper()
        for r in records
    )

    if already_present:
        print(f"{filename}: entry with {id_field}={new_id} already exists, skipping")
        continue

    records.append(new_entry)

    with open(path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"{filename}: added entry -> {new_entry}")