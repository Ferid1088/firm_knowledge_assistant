"""Document-type detector: LLM-on-sample classification.

Samples up to SAMPLE_PAGES pages (first, middle, last) to keep it fast, then
asks the local LLM (via Ollama) to classify the document into one of 10 types.

10 document types (A–J):
  A  prose_text        — general flowing-text document (Fließtext)
  B  table_structured  — primarily tabular data / spreadsheet-like
  C  norm_standard     — technical standard/norm (DIN, ISO, EN, VDE, …)
  D  technical_manual  — technical manual / operating instructions
  E  legal_contract    — contract, terms & conditions, legal agreement
  F  report_study      — report / study / analysis
  G  form_template     — form or fillable template
  H  invoice_bill      — invoice, delivery note, bill
  I  presentation      — presentation slides
  J  correspondence    — email, letter, memo

Returns a TypeDetectionResult with doc_type and confidence (0..1).
Falls back to "prose_text" when confidence < CONFIDENCE_THRESHOLD.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass

import pypdfium2 as pdfium

from backend.config import OLLAMA_MODEL, OLLAMA_BASE_URL

SAMPLE_PAGES = 3         # pages to sample (first, middle, last — deduplicated)
CONFIDENCE_THRESHOLD = 0.80  # fall back to prose_text below this

VALID_TYPES = {
    "prose_text",
    "table_structured",
    "norm_standard",
    "technical_manual",
    "legal_contract",
    "report_study",
    "form_template",
    "invoice_bill",
    "presentation",
    "correspondence",
}

_PROMPT = """\
You are a document classification expert. Given a text sample from a PDF, classify it into EXACTLY ONE of these types:

- prose_text        : general flowing text document
- table_structured  : primarily tabular / spreadsheet-like data
- norm_standard     : technical standard or norm (DIN, ISO, EN, VDE, …)
- technical_manual  : technical manual or operating instructions
- legal_contract    : contract, terms & conditions, legal agreement
- report_study      : report, study, or analysis
- form_template     : form or fillable template
- invoice_bill      : invoice, delivery note, or bill
- presentation      : presentation slides
- correspondence    : email, letter, or memo

Respond with ONLY valid JSON in this exact format, nothing else:
{"doc_type": "<type>", "confidence": <0.0 to 1.0>}

Text sample:
\"\"\"
{sample}
\"\"\"
"""


@dataclass
class TypeDetectionResult:
    doc_type: str       # one of VALID_TYPES
    confidence: float   # 0..1
    sampled_pages: list[int]  # 1-based


def _sample_text(pdf_path: str) -> tuple[str, list[int]]:
    """Extract text from a representative sample of pages."""
    pdf = pdfium.PdfDocument(pdf_path)
    total = len(pdf)

    indices: list[int] = []
    if total > 0:
        indices.append(0)
    if total > 2:
        indices.append(total // 2)
    if total > 1:
        indices.append(total - 1)
    # deduplicate, preserve order
    seen: set[int] = set()
    unique: list[int] = []
    for i in indices:
        if i not in seen:
            seen.add(i)
            unique.append(i)

    parts: list[str] = []
    for i in unique:
        text = pdf[i].get_textpage().get_text_range().strip()
        if text:
            parts.append(f"[Page {i + 1}]\n{text[:1500]}")

    pdf.close()
    return "\n\n".join(parts), [i + 1 for i in unique]


def _call_llm(prompt: str) -> str:
    """Call the local Ollama API; returns the raw text response."""
    import urllib.request

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data.get("response", "")


def _parse_llm_response(text: str) -> tuple[str, float]:
    """Parse LLM JSON response -> (doc_type, confidence). Falls back on error."""
    # Strip optional markdown code fences
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    try:
        obj = json.loads(text)
        doc_type = str(obj.get("doc_type", "")).strip()
        confidence = float(obj.get("confidence", 0.0))
        if doc_type not in VALID_TYPES:
            return "prose_text", 0.0
        return doc_type, max(0.0, min(1.0, confidence))
    except Exception:
        return "prose_text", 0.0


def detect_type(pdf_path: str) -> TypeDetectionResult:
    """Sample the PDF and use the local LLM to classify its document type."""
    sample, sampled_pages = _sample_text(pdf_path)
    if not sample.strip():
        return TypeDetectionResult(
            doc_type="prose_text",
            confidence=0.0,
            sampled_pages=sampled_pages,
        )

    prompt = _PROMPT.format(sample=sample[:4000])
    try:
        raw = _call_llm(prompt)
        doc_type, confidence = _parse_llm_response(raw)
    except Exception:
        doc_type, confidence = "prose_text", 0.0

    # Fall back to prose_text when confidence is too low
    if confidence < CONFIDENCE_THRESHOLD:
        doc_type = "prose_text"

    return TypeDetectionResult(
        doc_type=doc_type,
        confidence=confidence,
        sampled_pages=sampled_pages,
    )
