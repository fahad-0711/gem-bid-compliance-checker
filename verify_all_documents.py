"""
Verification script: extracts every document in your sample_docs folder,
checks extraction success, and cross-references against the mock
government registries — all in one pass, so you can see the complete
picture instead of testing person-by-person.
"""
import os
import glob
from extraction.pdf_reader import extract_text_from_pdf, is_text_based_pdf
from extraction.ocr_reader import extract_text_via_ocr, extract_text_from_image
from extraction.field_extractor import process_document
from extraction.government_verifier import verify_against_government_records

# Adjust this to wherever your document folders actually are
BASE_FOLDER = "data/sample_docs/IMG-Docs"

def get_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        if is_text_based_pdf(path):
            return extract_text_from_pdf(path)
        else:
            text, _ = extract_text_via_ocr(path)
            return text
    elif ext in (".jpg", ".jpeg", ".png"):
        text, _ = extract_text_from_image(path)
        return text
    return ""

results = []
person_folders = sorted(glob.glob(os.path.join(BASE_FOLDER, "p*")))

for folder in person_folders:
    person_name = os.path.basename(folder)
    files = sorted(glob.glob(os.path.join(folder, "*")))

    for file_path in files:
        filename = os.path.basename(file_path)
        try:
            text = get_text(file_path)
            result = process_document(filename, text)
            doc_type = result["doc_type"]
            fields = result["fields"]

            gov_check = verify_against_government_records(doc_type, fields)

            status = "OK" if gov_check["status"] == "Verified" else gov_check["status"]

            results.append({
                "person": person_name,
                "file": filename,
                "doc_type": doc_type,
                "fields": fields,
                "gov_status": status,
                "gov_detail": gov_check["detail"],
            })
        except Exception as e:
            results.append({
                "person": person_name,
                "file": filename,
                "doc_type": "ERROR",
                "fields": {},
                "gov_status": "CRASH",
                "gov_detail": str(e),
            })

# ---------- Print summary ----------
print(f"\n{'='*100}")
print(f"Checked {len(results)} documents across {len(person_folders)} people")
print(f"{'='*100}\n")

problems = [r for r in results if r["gov_status"] not in ("OK",)]
clean = [r for r in results if r["gov_status"] == "OK"]

print(f"✅ {len(clean)} documents Verified correctly")
print(f"⚠️  {len(problems)} documents need attention\n")

if problems:
    print("--- ISSUES FOUND ---\n")
    for r in problems:
        print(f"[{r['person']}] {r['file']}")
        print(f"  Detected type: {r['doc_type']}")
        print(f"  Fields: {r['fields']}")
        print(f"  Status: {r['gov_status']} — {r['gov_detail']}")
        print()