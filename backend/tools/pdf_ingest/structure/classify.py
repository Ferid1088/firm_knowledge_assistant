"""LLM-as-classifier-only for ambiguous structure decisions (step 6).

Local model, label-only output, batched, never edits content/numbers. If the
LLM is unavailable or its output can't be parsed, returns {} — callers fall
back to the deterministic default ("heading" = keep, do not demote). Never
blocks ingestion.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from backend.services.tracing import observe_if_enabled

_VALID_LABELS = {"heading", "label"}


def _load_prompt_template(lang: str) -> str:
    from backend.services.language import registry
    ld = registry.get(lang)
    p = Path("prompts") / f"structure_classify_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    fallback = Path("prompts") / "structure_classify_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else (
        "Classify each item as \"heading\" or \"label\". "
        "Return a JSON array of labels, same order, nothing else.\n\n{items}"
    )


def _format_items(items: list[str]) -> str:
    return "\n".join(f"{i+1}. {text}" for i, text in enumerate(items))


@observe_if_enabled(name="ollama.classify_structure", as_type="generation")
def _llm_classify(items: list[str], lang: str, model: str) -> list[str]:
    import ollama

    template = _load_prompt_template(lang)
    prompt = template.format(items=_format_items(items))

    resp = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
        think=False,
    )
    raw = resp["message"]["content"].strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Tolerate a fenced code block around the JSON array.
    m = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if not m:
        raise ValueError(f"no JSON array in classifier output: {raw!r}")
    labels = json.loads(m.group(0))

    if not isinstance(labels, list) or len(labels) != len(items):
        raise ValueError(f"label count mismatch: {len(labels)} vs {len(items)}")
    labels = [str(l).strip().lower() for l in labels]
    if not all(l in _VALID_LABELS for l in labels):
        raise ValueError(f"invalid label(s): {labels!r}")
    return labels


def classify_headers(flagged: list[str], lang: str, structure_cfg: dict, ollama_model: str) -> dict[str, str]:
    """Batch-classify ambiguous header texts as "heading" or "label".

    Returns {} on any failure (offline, bad output) — caller's
    `.get(text, "heading")` then keeps the deterministic default (no demotion).
    """
    if not flagged:
        return {}
    try:
        labels = _llm_classify(flagged, lang, ollama_model)
    except Exception:
        return {}
    return dict(zip(flagged, labels))
