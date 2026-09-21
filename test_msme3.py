from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import process_document

text, conf = extract_text_from_image('data/sample_docs/IMG-Docs/p2/P2.jpeg')
result = process_document('MSME.jpeg', text)
print("Extracted udyam_number:", repr(result['fields'].get('udyam_number')))
print("Full raw text:", repr(text))