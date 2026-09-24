from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import process_document

text, conf = extract_text_from_image(r'data\sample_docs\IMG-Docs\p2\03_MSME_Certificate_Priya_Singh.png')
print('--- RAW TEXT ---')
print(repr(text))
result = process_document('test.png', text)
print('Fields:', result['fields'])