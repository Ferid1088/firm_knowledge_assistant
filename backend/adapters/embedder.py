"""Qwen3-Embedding dense vectors — offline, normalized, query-instruction aware.

Index time: embed raw text (no prefix). Query time: prepend EMBED_QUERY_INSTRUCTION.
Oversize atomic leaves: embed a contextual description instead of truncating.
"""
from __future__ import annotations
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import EMBED_MODEL_ID, EMBED_QUERY_INSTRUCTION, EMBED_MAX_SEQ

_EMBEDDER: SentenceTransformer | None = None


def load_embedder(model_id: str = EMBED_MODEL_ID) -> SentenceTransformer:
    global _EMBEDDER
    if _EMBEDDER is None or _EMBEDDER.model_card_data.base_model != model_id:
        # Force CPU on the pilot (16 GB M1) — MPS OOMs on large batches with Qwen3
        _EMBEDDER = SentenceTransformer(model_id, trust_remote_code=True, device="cpu")
    return _EMBEDDER


def embed_texts(embedder: SentenceTransformer, texts: list[str]) -> np.ndarray:
    """Embed document texts at index time (no instruction prefix).

    Oversize texts are truncated to EMBED_MAX_SEQ tokens before encoding to
    avoid OOM on the attention mask (spec: embed a contextual description for
    oversize atomic leaves — that happens in pipeline.py; this is the safety net).
    """
    tokenizer = embedder.tokenizer
    safe_texts = []
    for t in texts:
        if tokenizer is not None:
            ids = tokenizer.encode(t, add_special_tokens=False)
            if len(ids) > EMBED_MAX_SEQ:
                t = tokenizer.decode(ids[:EMBED_MAX_SEQ], skip_special_tokens=True)
        safe_texts.append(t)
    return embedder.encode(safe_texts, normalize_embeddings=True, show_progress_bar=False, batch_size=8)


def embed_query(embedder: SentenceTransformer, query: str) -> np.ndarray:
    """Embed a user query with the instruction prefix (Qwen3 requirement)."""
    prefixed = EMBED_QUERY_INSTRUCTION + query
    return embedder.encode([prefixed], normalize_embeddings=True, show_progress_bar=False)[0]


def token_count(embedder: SentenceTransformer, text: str) -> int:
    tokenizer = embedder.tokenizer
    if tokenizer is None:
        return len(text.split())
    return len(tokenizer.encode(text, add_special_tokens=False))
