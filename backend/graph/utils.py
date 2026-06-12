"""Shared utilities for graph nodes."""
from __future__ import annotations
from pathlib import Path

from backend.config import RETRIEVE_DEEP_POOL, RETRIEVE_K, RERANKER_TOP_K
from backend.services.language import registry


def load_prompt(purpose: str, lang: str) -> str:
    """Load a prompt template from backend/prompts/, falling back to German."""
    ld = registry.get(lang)
    p = Path("backend/prompts") / f"{purpose}_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    fallback = Path("backend/prompts") / f"{purpose}_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else ""


def retrieve_pool_size(attempts: int) -> int:
    expansion = max(10, RETRIEVE_DEEP_POOL // 2)
    return RETRIEVE_DEEP_POOL + (attempts * expansion)


def answer_source_limit(attempts: int) -> int:
    return max(RETRIEVE_K, RERANKER_TOP_K + (attempts * 2))
