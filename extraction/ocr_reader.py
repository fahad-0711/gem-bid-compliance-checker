"""
Extracts text from scanned/image-based PDFs using OCR (pytesseract).
Falls back path when pdf_reader.py finds no extractable text.
"""

import pytesseract
from pdf2image import convert_from_path


def extract_text_via_ocr(file_path: str, dpi: int = 300) -> tuple[str, float]:
    """
    Converts each page of a PDF to an image, then runs OCR on it.
    Returns (extracted_text, average_confidence 0.0-1.0).
    """
    images = convert_from_path(file_path, dpi=dpi)
    all_text = []
    confidences = []

    for image in images:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        page_text = pytesseract.image_to_string(image)
        all_text.append(page_text)

        # Average confidence across detected words (ignore -1 = no detection)
        word_confidences = [int(c) for c in data["conf"] if int(c) > 0]
        if word_confidences:
            confidences.append(sum(word_confidences) / len(word_confidences))

    full_text = "\n".join(all_text).strip()
    avg_confidence = (sum(confidences) / len(confidences) / 100) if confidences else 0.0
    return full_text, round(avg_confidence, 2)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"
    text, confidence = extract_text_via_ocr(path)
    print(f"Confidence: {confidence}")
    print("--- OCR text ---")
    print(text)