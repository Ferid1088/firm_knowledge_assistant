"""LangGraph state for the RAG query pipeline."""
from __future__ import annotations
from typing import TypedDict, Optional


class RAGState(TypedDict, total=False):
    # Input
    question: str
    active_lang_codes: list[str]       # e.g. ["de", "en"]

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

    # Internals
    escalation_reason: str
