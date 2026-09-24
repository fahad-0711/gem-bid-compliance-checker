from extraction.pdf_reader import extract_text_from_pdf
from extraction.field_extractor import process_document

files = {
    "GST": r"data/sample_docs/pdf-docs/p2/02_GST_Registration_Priya_Singh.pdf",
    "COMPANY_REG": r"data/sample_docs/pdf-docs/p2/04_Business_Registration_Certificate_Priya_Singh.pdf",
    "TURNOVER": r"data/sample_docs/pdf-docs/p2/05_Turnover_Certificate_Priya_Singh.pdf",
}

for label, path in files.items():
    text = extract_text_from_pdf(path)
    result = process_document("x.pdf", text)
    print(label, "->", result["fields"])