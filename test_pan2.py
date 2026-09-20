from extraction.ocr_reader import extract_text_from_image
from extraction.field_extractor import _extract_name_after_label

text, conf = extract_text_from_image('data/sample_docs/p1/PAN_Card_1.jpeg')
print('Confidence:', conf)
print('--- RAW TEXT ---')
print(repr(text))
print('holder_name:', _extract_name_after_label(text, r"Name"))