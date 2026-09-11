from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import process_document

text, conf = extract_text_from_image('data/sample_docs/MSME_1.jpeg')
result = process_document('MSME_1.jpeg', text)
print(result)