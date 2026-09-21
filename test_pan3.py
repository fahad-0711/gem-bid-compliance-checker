from extraction.pdf_reader import extract_text_from_pdf
from extraction.field_extractor import process_document

text = extract_text_from_pdf('data\\sample_docs\\pdf-docs\\p2\\PAN_Card_02_Priya_Singh.pdf')
result = process_document('PAN_Card_02_Priya_Singh.pdf', text)
print("Extracted pan_number:", repr(result['fields'].get('pan_number')))
print("Full raw text:", repr(text))