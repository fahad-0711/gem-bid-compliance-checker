"""
Shared data contract between extraction, rules, and UI modules.
Everyone imports from here — do not redefine these keys elsewhere.
"""

from typing import TypedDict, Optional, List

class ExtractedDocument(TypedDict):
    doc_type: str              # "GST" | "PAN" | "MSME"
    file_name: str
    raw_text: str
    fields: dict                # e.g. {"gstin": "...", "expiry_date": "2025-03-12"}
    confidence: float           # 0.0 to 1.0, OCR/extraction confidence

class RuleResult(TypedDict):
    field: str
    passed: bool
    reason: Optional[str]       # None if passed

class DocumentReport(TypedDict):
    doc_type: str
    file_name: str
    status: str                  # "Valid" | "Invalid" | "Missing" | "Needs Review"
    results: List[RuleResult]

class ComplianceReport(TypedDict):
    bid_id: str
    documents: List[DocumentReport]
    overall_status: str          # "Compliant" | "Non-Compliant" | "Incomplete"