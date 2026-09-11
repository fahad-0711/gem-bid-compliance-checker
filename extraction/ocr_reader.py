"""
Extracts text from scanned/image-based PDFs and standalone images
using OCR (pytesseract), with automatic rotation correction.
"""

import re
import pytesseract
from PIL import Image, ImageOps, ImageEnhance
from pdf2image import convert_from_path

Image.MAX_IMAGE_PIXELS = 150_000_000


def _resize_if_needed(image: Image.Image, max_dimension: int = 2500) -> Image.Image:
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
    return image


def _ocr_with_confidence(image: Image.Image) -> tuple[str, float]:
    """
    Runs OCR on a single image and returns (text, avg_confidence 0-1).

    Previously this called both image_to_data() and image_to_string(),
    which runs Tesseract TWICE for the same image (each call is a full
    OCR pass). image_to_data() already contains every recognized word,
    so we reconstruct the text from it instead of OCR'ing a second time.
    This alone halves OCR work everywhere this function is used.
    """
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = [w for w in data["text"] if w.strip()]
    text = " ".join(words)
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


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Grayscale + contrast boost — often improves OCR on busy/colored backgrounds."""
    gray = image.convert("L")
    enhancer = ImageEnhance.Contrast(gray)
    return enhancer.enhance(2.0)


def _looks_like_it_has_an_id_number(text: str) -> bool:
    """
    Quick check: does this text contain something that looks like a
    GSTIN, PAN, or Udyam number? Used to decide whether a fuller,
    slower retry is worth doing — if we already found something that
    looks like the actual ID we need, there's no need to keep searching.
    """
    patterns = [
        r"[A-Z]{5}[0-9]{4}[A-Z]",           # PAN-like
        r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]",    # GSTIN-like
        r"UDYAM-[A-Z]{2}",                    # Udyam-like
    ]
    return any(re.search(p, text) for p in patterns)


def _best_rotation_ocr(image: Image.Image) -> tuple[str, float]:
    """
    Fast path: use Tesseract's OSD pass to correct rotation in one shot,
    then OCR once. If that's confident AND an ID number is found, return
    immediately — this is the common case (clean, text-dense documents)
    and takes ~1-2 OCR passes.

    Fallback: if OSD fails outright, confidence is low, or no ID number
    pattern was found (the field we care about most), try each rotation
    in turn and stop as soon as one produces a confident ID-number match
    — instead of always running every rotation/variant combination to
    completion. If nothing confident turns up, fall back to whichever
    candidate scored highest.
    """
    best_text, best_confidence, best_score = "", 0.0, -1.0

    rotation = _detect_rotation_via_osd(image)
    if rotation is not None:
        candidate = image.rotate(-rotation, expand=True) if rotation != 0 else image
        text, confidence = _ocr_with_confidence(candidate)
        score = confidence * min(len(text), 200)
        if score > best_score:
            best_text, best_confidence, best_score = text, confidence, score

        if confidence >= 0.6 and _looks_like_it_has_an_id_number(text):
            return best_text, best_confidence  # fast path succeeded, stop here

    # Fallback: OSD failed, wasn't trustworthy, or didn't find an ID
    # number. Try plain rotations first (cheap), then only reach for
    # the contrast-enhanced variant of a given angle if the plain one
    # didn't find an ID number — and stop the whole search the moment
    # any candidate produces a confident ID-number match, rather than
    # always exhausting every rotation/variant combination.
    for angle in (0, 90, 180, 270):
        rotated = image.rotate(angle, expand=True) if angle != 0 else image

        for candidate in (rotated, _preprocess_for_ocr(rotated)):
            text, confidence = _ocr_with_confidence(candidate)
            score = confidence * min(len(text), 200)
            candidate_has_id = _looks_like_it_has_an_id_number(text)
            best_has_id = _looks_like_it_has_an_id_number(best_text)

            if candidate_has_id and not best_has_id:
                best_text, best_confidence, best_score = text, confidence, score
            elif candidate_has_id == best_has_id and score > best_score:
                best_text, best_confidence, best_score = text, confidence, score

            if candidate_has_id and confidence >= 0.5:
                return best_text, best_confidence  # good enough — stop searching

            # Plain rotation already found an ID number but confidence
            # was low — the contrast-enhanced variant rarely helps once
            # the pattern is already there, so skip it and move on.
            if candidate is rotated and candidate_has_id:
                break

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

    image = _resize_if_needed(image, max_dimension=2000)
    text, confidence = _best_rotation_ocr(image)
    return text, confidence


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_docs/valid/GST_Certificate.pdf"
    text, confidence = extract_text_via_ocr(path)
    print(f"Confidence: {confidence}")
    print("--- OCR text ---")
    print(text)