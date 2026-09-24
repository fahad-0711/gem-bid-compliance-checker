from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import process_document

text, conf = extract_text_from_image(r'data/sample_docs/IMG-Docs/p1/05_Turnover_Certificate_Rohit_Kumar_Sharma.png')
print('Confidence:', conf)
print('--- RAW TEXT ---')
print(repr(text))
result = process_document('test.png', text)
print('Detected type:', result['doc_type'])
print('Fields:', result['fields'])