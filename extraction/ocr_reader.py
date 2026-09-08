"""
Extracts text from scanned/image-based PDFs and standalone images
using OCR (pytesseract), with automatic rotation correction.
"""

import pytesseract
from PIL import Image, ImageOps, ImageEnhance
from pdf2image import convert_from_path
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 150_000_000


def _resize_if_needed(image: Image.Image, max_dimension: int = 2500) -> Image.Image:
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
    return image


def _ocr_with_confidence(image: Image.Image) -> tuple[str, float]:
    """Runs OCR on a single image and returns (text, avg_confidence 0-1)."""
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(image)
    word_confidences = [int(c) for c in data["conf"] if int(c) > 0]
    avg_confidence = (sum(word_confidences) / len(word_confidences) / 100) if word_confidences else 0.0
    return text.strip(), round(avg_confidence, 2)


def _best_rotation_ocr(image: Image.Image) -> tuple[str, float]:
    """
    Tries OCR at 0°/90°/180°/270° rotations, with and without contrast
    preprocessing, and keeps whichever result has the best combination
    of confidence and extracted text length. High confidence on very
    little text is not preferred over slightly lower confidence with
    substantially more recovered text.
    """
    best_text, best_confidence, best_score = "", 0.0, -1.0

    for angle in (0, 90, 180, 270):
        rotated = image.rotate(angle, expand=True) if angle != 0 else image

        candidates = [
            rotated,                       # original, no preprocessing
            _preprocess_for_ocr(rotated),  # contrast-enhanced version
        ]

        for candidate in candidates:
            text, confidence = _ocr_with_confidence(candidate)
            # Score rewards both confidence and amount of text recovered,
            # so a high-confidence-but-nearly-empty result doesn't win
            # over a slightly-lower-confidence result with real content.
            score = confidence * min(len(text), 200)

            if score > best_score:
                best_text, best_confidence, best_score = text, confidence, score

    return best_text, best_confidence

def extract_text_via_ocr(file_path: str, dpi: int = 150) -> tuple[str, float]:
    """
    Converts each page of a PDF to an image, then runs OCR on it,
    automatically correcting for sideways/upside-down pages.
    Returns (extracted_text, average_confidence 0.0-1.0).
    """
    images = convert_from_path(file_path, dpi=dpi)
    all_text = []
    confidences = []

    for image in images:
        image = _resize_if_needed(image)
        if image.mode != "RGB":
            image = image.convert("RGB")

        text, confidence = _best_rotation_ocr(image)
        all_text.append(text)
        confidences.append(confidence)

    full_text = "\n".join(all_text).strip()
    avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0
    return full_text, round(avg_confidence, 2)
def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Grayscale + contrast boost — often improves OCR on busy/colored backgrounds."""
    gray = image.convert("L")
    enhancer = ImageEnhance.Contrast(gray)
    return enhancer.enhance(2.0)

def extract_text_from_image(file_path: str) -> tuple[str, float]:
    """
    Runs OCR directly on an image file (jpg/png), automatically correcting
    EXIF-based orientation and sideways/upside-down photos.
    Returns (extracted_text, average_confidence 0.0-1.0).
    """
    image = Image.open(file_path)
    image = ImageOps.exif_transpose(image)  # fix phone-camera EXIF rotation

    if image.mode != "RGB":
        image = image.convert("RGB")

    image = _resize_if_needed(image)
    text, confidence = _best_rotation_ocr(image)
    return text, confidence


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"
    text, confidence = extract_text_via_ocr(path)
    print(f"Confidence: {confidence}")
    print("--- OCR text ---")
    print(text)