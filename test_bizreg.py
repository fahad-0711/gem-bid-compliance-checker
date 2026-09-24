from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import detect_doc_type, process_document

text, conf = extract_text_from_image(r'data/sample_docs/IMG-Docs/p1/04_Business_Registration_Certificate_Rohit_Kumar_Sharma.png')
result = process_document('test.png', text)
print('Detected type:', result['doc_type'])
print('Fields:', result['fields'])