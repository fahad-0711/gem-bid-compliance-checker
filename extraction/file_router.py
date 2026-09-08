"""
file_router.py

Single entry point for "any uploaded file -> raw extracted text".

Right now your Streamlit uploader presumably calls pdf_reader.py or
ocr_reader.py directly depending on whether the PDF is digital or
scanned. This module sits in FRONT of that: it looks at what the user
actually uploaded (PDF, image, or DOCX) and calls the right reader -
so app.py only ever has to call ONE function, regardless of format.

Integration:
    Replace whatever currently decides "which reader do I call" in
    app.py with a single call to `extract_text(file_path)` from here.
    It returns the same kind of raw text string your field_extractor.py
    already expects, so nothing downstream needs to change.
"""

import os

from docx_reader import read_docx

# --- These two imports point at YOUR existing modules. -----------------
# Swap the function names below if your real function signatures differ.
from pdf_reader import extract_text_from_pdf, is_scanned_pdf  # existing
from ocr_reader import extract_text_with_ocr  # existing
# -------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}


class UnsupportedFileType(ValueError):
    """Raised when an uploaded file's extension isn't one we can handle."""


def extract_text(file_path: str) -> dict:
    """
    Route an uploaded file to the correct extraction pipeline and
    return its raw text, plus a bit of metadata about how it was read.

    Args:
        file_path: path to the uploaded file on disk (Streamlit's
                   file_uploader writes to a temp path, or you can
                   write the uploaded bytes to disk yourself first).

    Returns:
        {
            "text": "<raw extracted text>",
            "source_format": "pdf" | "docx" | "image",
            "extraction_method": "pdfplumber" | "ocr" | "docx",
        }

    Raises:
        UnsupportedFileType: if the extension isn't PDF/DOCX/image.
        ValueError: bubbled up from the underlying reader if the file
                    is corrupted or unreadable.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"'{ext}' is not supported. Please upload a PDF, DOCX, "
            f"JPG, or PNG file."
        )

    if ext == ".pdf":
        # Keep using your existing digital-vs-scanned detection -
        # this router doesn't change that logic, just calls into it.
        if is_scanned_pdf(file_path):
            text = extract_text_with_ocr(file_path)
            method = "ocr"
        else:
            text = extract_text_from_pdf(file_path)
            method = "pdfplumber"
        return {"text": text, "source_format": "pdf", "extraction_method": method}

    if ext == ".docx":
        text = read_docx(file_path)
        return {"text": text, "source_format": "docx", "extraction_method": "docx"}

    if ext in (".jpg", ".jpeg", ".png"):
        # Images always go through OCR - there's no "digital text" layer
        # in a photo/scan the way there is in a native PDF.
        text = extract_text_with_ocr(file_path)
        return {"text": text, "source_format": "image", "extraction_method": "ocr"}

    # Defensive - should be unreachable given the extension check above.
    raise UnsupportedFileType(f"No handler wired up for '{ext}'.")
