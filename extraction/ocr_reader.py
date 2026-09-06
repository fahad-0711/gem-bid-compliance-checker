"""
Extracts text from scanned/image-based PDFs using OCR (pytesseract).
Falls back path when pdf_reader.py finds no extractable text.
"""

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

Image.MAX_IMAGE_PIXELS = 150_000_000


def extract_text_via_ocr(file_path: str, dpi: int = 150) -> tuple[str, float]:
    """
    Converts each page of a PDF to an image, then runs OCR on it.
    Uses a moderate DPI (150) to balance OCR accuracy against memory
    usage — important on memory-constrained hosting like Streamlit Cloud.
    Returns (extracted_text, average_confidence 0.0-1.0).
    """
    images = convert_from_path(file_path, dpi=dpi)
    all_text = []
    confidences = []

    for image in images:
        max_dimension = 2500
        if max(image.size) > max_dimension:
            scale = max_dimension / max(image.size)
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, Image.LANCZOS)

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        page_text = pytesseract.image_to_string(image)
        all_text.append(page_text)

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