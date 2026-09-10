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


def _detect_rotation_via_osd(image: Image.Image) -> int | None:
    """
    Uses Tesseract's fast orientation-detection mode (not full OCR) to
    estimate the clockwise rotation needed to make text upright.
    Returns None if OSD couldn't produce an answer — common on sparse or
    visually busy images (ID cards, watermarked scans, photos mixed with
    text) — so the caller knows to fall back to the slower brute-force
    method instead of trusting a wrong or missing correction.
    """
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        return osd.get("rotate", 0)
    except pytesseract.TesseractError:
        return None


def _best_rotation_ocr(image: Image.Image) -> tuple[str, float]:
    """
    Fast path: use Tesseract's OSD pass to correct rotation in one shot,
    then OCR once. If that's confident, return immediately — this is the
    common case (clean, text-dense documents) and takes ~2 OCR passes.

    Fallback: if OSD fails outright, or its answer still yields
    low-confidence OCR (this happens on busy/low-text documents like ID
    cards, where OSD can misjudge or fail to detect orientation at all),
    brute-force all four rotations with and without contrast enhancement,
    same as the original approach, and keep the best result. This keeps
    the slow path reserved for documents that actually need it, instead
    of silently returning wrong-orientation text.
    """
    best_text, best_confidence, best_score = "", 0.0, -1.0

    rotation = _detect_rotation_via_osd(image)
    if rotation is not None:
        candidate = image.rotate(-rotation, expand=True) if rotation != 0 else image
        text, confidence = _ocr_with_confidence(candidate)
        score = confidence * min(len(text), 200)
        if score > best_score:
            best_text, best_confidence, best_score = text, confidence, score

        if confidence >= 0.6:
            return best_text, best_confidence  # fast path succeeded, stop here

    # Fallback: OSD failed or wasn't trustworthy — brute-force every
    # rotation (and a contrast-enhanced variant of each), same scoring
    # as before, so accuracy doesn't regress on harder documents.
    for angle in (0, 90, 180, 270):
        rotated = image.rotate(angle, expand=True) if angle != 0 else image
        for candidate in (rotated, _preprocess_for_ocr(rotated)):
            text, confidence = _ocr_with_confidence(candidate)
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

    image = _resize_if_needed(image, max_dimension=2000)  # was 2500
    text, confidence = _best_rotation_ocr(image)
    return text, confidence


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"
    text, confidence = extract_text_via_ocr(path)
    print(f"Confidence: {confidence}")
    print("--- OCR text ---")
    print(text)