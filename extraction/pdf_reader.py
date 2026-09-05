"""
Extracts raw text from digital (non-scanned) PDF files using pdfplumber.
"""

import pdfplumber


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extracts all text from a PDF file, page by page.
    Returns an empty string if the PDF has no extractable text
    (likely a scanned document — use ocr_reader.py instead).
    """
    full_text = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text).strip()


def is_text_based_pdf(file_path: str, min_chars: int = 30) -> bool:
    """
    Quick check: does this PDF have real extractable text,
    or does it need OCR? Returns True if text-based.
    """
    text = extract_text_from_pdf(file_path)
    return len(text) >= min_chars


if __name__ == "__main__":
    # Quick manual test
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"
    print(f"Testing: {path}")
    print(f"Is text-based: {is_text_based_pdf(path)}")
    print("--- Extracted text ---")
    print(extract_text_from_pdf(path))