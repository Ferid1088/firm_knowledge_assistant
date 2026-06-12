"""LLM adapter — single Ollama → vLLM swap point.

CLAUDE.md: 'Production: swap to vLLM base_url here only.'
Every node and tool that needs an LLM call imports chat() from here.
Never call ollama.chat() directly outside this module.
"""
from __future__ import annotations
from typing import Any

from backend.config import OLLAMA_MODEL, OLLAMA_BASE_URL


def chat(
    prompt: str,
    model: str = OLLAMA_MODEL,
    temperature: float = 0,
    think: bool = False,
) -> str:
    """Send a single-turn prompt and return the text response.

    Returns empty string on any error so callers can decide how to handle it.
    """
    import ollama
    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature},
            think=think,
        )
        return resp["message"]["content"].strip()
    except Exception:
        return ""
