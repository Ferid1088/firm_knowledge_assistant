"""Query-rewrite orchestrator: skip-check -> dictionary -> LLM -> post-check.

Document-agnostic mechanism. All corpus knowledge (synonym dictionary,
few-shot examples, domain hint) lives in YAML/prompt files referenced from
config.REWRITE — nothing corpus-specific is hardcoded here.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

import yaml

from src.rewrite import protected
from src.common.tracing import observe_if_enabled

_dictionary_cache: dict[str, dict] = {}
_fewshots_cache: dict[str, list] = {}


def _load_yaml(path: str, cache: dict[str, Any], default: Any):
    if path not in cache:
        p = Path(path)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            cache[path] = data if data is not None else default
        else:
            cache[path] = default
    return cache[path]


def _load_dictionary(path: str) -> dict[str, list[str]]:
    return _load_yaml(path, _dictionary_cache, {})


def _load_fewshots(path: str) -> list[dict]:
    return _load_yaml(path, _fewshots_cache, [])


def apply_dictionary(query: str, dictionary: dict[str, list[str]]) -> str:
    """Additively expand `query` with domain terms for any matched colloquial term."""
    if not dictionary:
        return query

    query_lower = query.lower()
    additions: list[str] = []
    for term, expansions in dictionary.items():
        if term.lower() in query_lower:
            for exp in expansions or []:
                if exp.lower() not in query_lower and exp not in additions:
                    additions.append(exp)

    if not additions:
        return query
    return f"{query} {' '.join(additions)}"


def _format_fewshots(fewshots: list[dict]) -> str:
    lines = []
    for ex in fewshots:
        in_q = ex.get("in", "")
        out_q = ex.get("out", "")
        if in_q and out_q:
            lines.append(f'"{in_q}" -> "{out_q}"')
    return "\n\n".join(lines)


def _load_prompt_template(lang: str) -> str:
    from src.common.language import registry
    ld = registry.get(lang)
    p = Path("prompts") / f"rewrite_{ld.prompt_key}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    fallback = Path("prompts") / "rewrite_de.txt"
    return fallback.read_text(encoding="utf-8") if fallback.exists() else "{query}"


def _fewshots_path(lang: str) -> str:
    from src.common.language import registry
    ld = registry.get(lang)
    p = Path("rewrite_data") / f"rewrite_fewshots_{ld.prompt_key}.yaml"
    if p.exists():
        return str(p)
    fallback = Path("rewrite_data") / "rewrite_fewshots_de.yaml"
    return str(fallback)


@observe_if_enabled(name="ollama.rewrite_query", as_type="generation")
def _llm_rewrite(query: str, lang: str, fewshots: list[dict], domain_hint: str,
                  model: str, temperature: float) -> str:
    import ollama

    template = _load_prompt_template(lang)
    prompt = template.format(
        domain_hint=domain_hint,
        few_shots=_format_fewshots(fewshots),
        query=query,
    )
    resp = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": temperature},
        think=False,
    )
    raw = resp["message"]["content"].strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip a leading label like "Anfrage:" or quotes some models add
    raw = re.sub(r'^(Anfrage|Query)\s*:\s*', "", raw, flags=re.IGNORECASE).strip()
    raw = raw.strip('"').strip()
    return raw


def rewrite_query(query: str, lang: str, rewrite_config: dict, ollama_model: str) -> str | None:
    """Return an expanded/rewritten query, or None if rewriting is skipped/rejected.

    Always safe to ignore the result and search with the original query —
    this function never mutates `query` and the caller is expected to AUGMENT
    (RRF-fuse), never replace.
    """
    patterns = rewrite_config.get("protected_patterns", [])

    if protected.is_code_only(query, patterns):
        return None

    candidate = query
    if rewrite_config.get("use_dictionary"):
        dictionary = _load_dictionary(rewrite_config["dictionary_path"])
        candidate = apply_dictionary(query, dictionary)

    if rewrite_config.get("use_llm"):
        fewshots = _load_fewshots(_fewshots_path(lang))
        try:
            llm_out = _llm_rewrite(
                candidate, lang, fewshots,
                rewrite_config.get("domain_hint", ""),
                ollama_model, rewrite_config.get("temperature", 0.1),
            )
        except Exception:
            llm_out = ""

        if llm_out and protected.passes_post_check(query, llm_out, patterns):
            candidate = llm_out

    if candidate == query:
        return None
    if not protected.passes_post_check(query, candidate, patterns):
        return None
    return candidate
