"""LangGraph state for the RAG query pipeline."""
from __future__ import annotations
from typing import TypedDict, Optional


class RAGState(TypedDict, total=False):
    """All mutable state carried through the LangGraph RAG pipeline.

    Fields are optional (total=False) so each node only populates what it owns;
    downstream nodes default missing fields rather than crashing.
    """

    # Input
    question: str
    active_lang_codes: list[str]       # e.g. ["de", "en"]
    history: list[dict]                # prior conversation turns [{role, text}], oldest-first

    # Language
    query_lang: str                    # detected language of query
    answer_lang: str                   # language to answer in
    translated_queries: dict[str, str] # {lang_code: translated_query}, cached

    # Multi-part decomposition
    sub_questions: list[str]
    sub_results: list[list[dict]]      # per sub-question retrieved hits

    # Retrieval
    candidate_pool: list[dict]         # deep pool from retrieve node
    reranked: list[dict]               # top-k after reranking

    # Confidence
    confidence: float
    confidence_gap: float
    attempts: int

    # Answer
    answer: str
    claims: list[dict]                 # [{text, source, quote, verified}]
    artifact_chunks: list[dict]        # UI only: [{chunk_id, text, boxes, address, source}]

    # Access control
    allowed_doc_type_ids: Optional[list[str]]  # None = unrestricted; set per request from user session
    structural_types: Optional[list[str]]       # None = all; e.g. ["table", "list"] for structure-filtered retrieval

    # Date range filtering (query-time; ISO date strings, inclusive bounds)
    date_filter_from: Optional[str]   # ISO date, inclusive lower bound
    date_filter_to: Optional[str]     # ISO date, inclusive upper bound

    # Internals
    escalation_reason: str
    reranker_failed: Optional[bool]     # True when reranker raised an exception and fell back
