import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from extraction.pdf_reader import extract_text_from_pdf
from extraction.field_extractor import process_document, detect_doc_type


def test_gst_extraction():
    path = "data/sample_docs/valid/GST_Certificate.pdf"
    text = extract_text_from_pdf(path)
    result = process_document(path, text)

    assert result["doc_type"] == "GST"
    assert result["fields"]["gstin"] == "27ABCPL1234F1Z5"
    assert result["confidence"] == 1.0


def test_pan_extraction():
    path = "data/sample_docs/valid/PAN_Card.pdf"
    text = extract_text_from_pdf(path)
    result = process_document(path, text)

    assert result["doc_type"] == "PAN"
    assert result["fields"]["pan_number"] == "ABCPL1234F"


def test_missing_field_lowers_confidence():
    text = "Some random unrelated text with no GSTIN in it"
    result = process_document("fake.pdf", text)
    assert result["fields"].get("gstin") is None