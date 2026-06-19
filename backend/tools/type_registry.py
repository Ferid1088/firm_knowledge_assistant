"""TypeRegistry — maps doc_type → (parser, chunker, embed_strategy).

Single source of truth for the dispatch table. The pipeline calls
``get_handler(doc_type)`` and delegates parse/chunk to the returned handler.

Adding a new type = one entry here + one parser/chunker module.

Embed strategies (step 8):
  text_dense        — standard Qwen3-Embedding on context_text (pilot path)
  description_dense — for oversize atomic leaves (tables): embed a generated
                      contextual description; store the full original text
  vision_text_dense — pilot: same as text_dense (vision path deferred to GPU)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

from backend.tools.parsers.parse_result import ParseResult
from backend.tools.chunk import StructuralChunk


@dataclass(frozen=True)
class DocTypeHandler:
    """Immutable binding of a doc_type key to its parser, chunker, and embed strategy."""

    doc_type: str
    parse: Callable[[str], ParseResult]
    chunk: Callable[[ParseResult], list[StructuralChunk]]
    embed_strategy: str   # "text_dense" | "description_dense" | "vision_text_dense"
    parser_name: str      # informational
    chunker_name: str     # informational
    table_schemas: dict = field(default_factory=dict)
    # Maps role-name → list of lowercase header keywords that identify that role.
    # Used by pipeline to classify each table chunk's table_role payload field.


def _build_registry() -> dict[str, DocTypeHandler]:
    """Construct the dispatch table mapping each doc_type key to its handler.

    Imports are lazy so that parser/chunker modules (which may load heavy
    dependencies like Docling) are not imported until the pipeline actually runs.
    """
    # Lazy imports so individual chunker/parser modules don't load at import time
    from backend.tools.parsers import docling_parser, ocr_parser, eml_parser
    from backend.tools.chunkers import (
        hybrid, table_atomic, plan_chunker, image_chunker,
        clause_atomic, document_structure, project_chunker, thread_chunker,
        list_chunker,
    )

    return {
        "prose_text": DocTypeHandler(
            doc_type="prose_text",
            parse=docling_parser.parse,
            chunk=hybrid.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="HybridChunker",
        ),
        "table_structured": DocTypeHandler(
            doc_type="table_structured",
            parse=docling_parser.parse,
            chunk=table_atomic.chunk,
            embed_strategy="description_dense",
            parser_name="Docling",
            chunker_name="TableAtomic",
        ),
        "technical_plan": DocTypeHandler(
            doc_type="technical_plan",
            parse=docling_parser.parse,
            chunk=plan_chunker.chunk,
            embed_strategy="text_dense",   # vision_text_dense on GPU
            parser_name="Docling",
            chunker_name="PlanChunker",
            table_schemas={
                "requirements": ["anforderung", "requirement", "spezifikation", "spec"],
                "schedule": ["datum", "milestone", "meilenstein", "date", "deadline", "termin"],
                "resources": ["ressource", "resource", "mitarbeiter", "person", "team"],
            },
        ),
        "scanned_image": DocTypeHandler(
            doc_type="scanned_image",
            parse=ocr_parser.parse,        # raises OcrNotBuiltError in pilot
            chunk=image_chunker.chunk,
            embed_strategy="text_dense",   # vision_dense on GPU
            parser_name="OCR (Tesseract)",
            chunker_name="ImageChunker",
        ),
        "legal_contract": DocTypeHandler(
            doc_type="legal_contract",
            parse=docling_parser.parse,
            chunk=clause_atomic.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="ClauseAtomic",
            table_schemas={
                "parties": ["vertragspartner", "auftragnehmer", "auftraggeber", "party", "contractor", "client"],
                "pricing": ["preis", "betrag", "summe", "price", "amount", "fee", "honorar", "vergütung"],
                "schedule": ["frist", "datum", "termin", "deadline", "date", "laufzeit", "gültigkeit"],
                "obligations": ["pflicht", "leistung", "verpflichtung", "obligation", "scope"],
            },
        ),
        "authority_document": DocTypeHandler(
            doc_type="authority_document",
            parse=docling_parser.parse,
            chunk=document_structure.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="DocumentStructureChunker",
            table_schemas={
                "obligations": ["pflicht", "verpflichtung", "obligation", "anforderung", "requirement"],
                "penalties": ["strafe", "bußgeld", "sanktion", "penalty", "fine"],
            },
        ),
        "project_management": DocTypeHandler(
            doc_type="project_management",
            parse=docling_parser.parse,
            chunk=project_chunker.chunk,
            embed_strategy="text_dense",   # dense + temporal-sparse on GPU
            parser_name="Docling",
            chunker_name="ProjectChunker",
            table_schemas={
                "milestones": ["meilenstein", "milestone", "phase", "datum", "date", "frist"],
                "budget": ["budget", "kosten", "cost", "aufwand", "effort", "ressource"],
                "risks": ["risiko", "risk", "wahrscheinlichkeit", "probability", "impact"],
            },
        ),
        "knowledge_base": DocTypeHandler(
            doc_type="knowledge_base",
            parse=docling_parser.parse,
            chunk=hybrid.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="HybridChunker",
        ),
        "hr_personnel": DocTypeHandler(
            doc_type="hr_personnel",
            parse=docling_parser.parse,
            chunk=hybrid.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="HybridChunker",
        ),
        "list_heavy": DocTypeHandler(
            doc_type="list_heavy",
            parse=docling_parser.parse,
            chunk=list_chunker.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="ListChunker",
        ),
        "email_thread": DocTypeHandler(
            doc_type="email_thread",
            parse=docling_parser.parse,
            chunk=thread_chunker.chunk,
            embed_strategy="text_dense",
            parser_name="Docling / Native EML",
            chunker_name="ThreadChunker",
        ),
        # ── Previously unregistered types (were falling back to prose_text) ──
        "norm_standard": DocTypeHandler(
            doc_type="norm_standard",
            parse=docling_parser.parse,
            chunk=document_structure.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="DocumentStructureChunker",
            table_schemas={
                "requirements": ["anforderung", "requirement", "muss", "shall", "must"],
                "limits": ["grenzwert", "limit", "toleranz", "tolerance", "max", "min"],
                "test_methods": ["prüfverfahren", "test method", "messung", "measurement"],
            },
        ),
        "technical_manual": DocTypeHandler(
            doc_type="technical_manual",
            parse=docling_parser.parse,
            chunk=document_structure.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="DocumentStructureChunker",
            table_schemas={
                "specifications": ["spezifikation", "specification", "technische daten", "technical data"],
                "parts": ["teil", "part", "bauteil", "component", "ersatzteil", "spare"],
                "procedures": ["schritt", "step", "vorgehensweise", "procedure", "anleitung"],
            },
        ),
        "report_study": DocTypeHandler(
            doc_type="report_study",
            parse=docling_parser.parse,
            chunk=hybrid.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="HybridChunker",
            table_schemas={
                "results": ["ergebnis", "result", "finding", "befund", "messwert"],
                "statistics": ["statistik", "statistic", "durchschnitt", "average", "median"],
            },
        ),
        "form_template": DocTypeHandler(
            doc_type="form_template",
            parse=docling_parser.parse,
            chunk=table_atomic.chunk,
            embed_strategy="description_dense",
            parser_name="Docling",
            chunker_name="TableAtomic",
            table_schemas={
                "fields": ["feld", "field", "eingabe", "input", "ausfüllen", "fill"],
            },
        ),
        "invoice_bill": DocTypeHandler(
            doc_type="invoice_bill",
            parse=docling_parser.parse,
            chunk=table_atomic.chunk,
            embed_strategy="description_dense",
            parser_name="Docling",
            chunker_name="TableAtomic",
            table_schemas={
                "line_items": ["position", "artikel", "item", "menge", "quantity", "beschreibung"],
                "totals": ["summe", "total", "gesamt", "netto", "brutto", "mwst", "vat"],
                "payment": ["zahlung", "payment", "konto", "account", "iban", "bank"],
            },
        ),
        "presentation": DocTypeHandler(
            doc_type="presentation",
            parse=docling_parser.parse,
            chunk=hybrid.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="HybridChunker",
        ),
        "correspondence": DocTypeHandler(
            doc_type="correspondence",
            parse=docling_parser.parse,
            chunk=thread_chunker.chunk,
            embed_strategy="text_dense",
            parser_name="Docling",
            chunker_name="ThreadChunker",
        ),
    }


_REGISTRY: dict[str, DocTypeHandler] | None = None


def get_handler(doc_type: str) -> DocTypeHandler:
    """Return the DocTypeHandler for doc_type, falling back to prose_text for unknown types."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    handler = _REGISTRY.get(doc_type)
    if handler is None:
        handler = _REGISTRY["prose_text"]
    return handler


def all_doc_types() -> list[str]:
    """List all registered doc_type keys."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return list(_REGISTRY.keys())


def handler_info(doc_type: str) -> dict:
    """Return a plain dict with parser, chunker, and embed_strategy for logging."""
    h = get_handler(doc_type)
    return {
        "doc_type": h.doc_type,
        "parser": h.parser_name,
        "chunker": h.chunker_name,
        "embed_strategy": h.embed_strategy,
    }
