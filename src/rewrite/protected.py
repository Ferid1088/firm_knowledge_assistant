"""Protected-token safety for query rewriting.

References, identifiers/codes, proper names, and numbers must survive a rewrite
unchanged. This module provides:
- is_code_only: pre-check to skip rewriting queries that are mostly codes/refs.
- extract_tokens: pull all protected-pattern matches out of a query.
- passes_post_check: verify every protected token from the original is still
  present, unchanged, in the rewritten query.

Patterns are CONFIG (REWRITE["protected_patterns"] in config.py) — this module
is a generic engine with zero corpus-specific knowledge.
"""
from __future__ import annotations
import re

# Above this fraction of non-whitespace characters covered by protected
# patterns, the query is considered "code-only" and rewriting is skipped.
CODE_ONLY_THRESHOLD = 0.6


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def extract_tokens(text: str, patterns: list[str]) -> list[str]:
    """Return all substrings of `text` matching any protected pattern."""
    tokens: list[str] = []
    for pat in _compile(patterns):
        tokens.extend(m.group(0) for m in pat.finditer(text))
    return tokens


def is_code_only(query: str, patterns: list[str], threshold: float = CODE_ONLY_THRESHOLD) -> bool:
    """True if `query` is primarily identifiers/codes/numbers — skip rewrite."""
    non_ws = re.sub(r"\s+", "", query)
    if not non_ws:
        return True

    covered: set[int] = set()
    for pat in _compile(patterns):
        for m in pat.finditer(query):
            for i in range(m.start(), m.end()):
                if not query[i].isspace():
                    covered.add(i)

    return (len(covered) / len(non_ws)) >= threshold


def passes_post_check(original: str, rewritten: str, patterns: list[str]) -> bool:
    """True if every protected token in `original` is unchanged in `rewritten`."""
    norm_rewritten = re.sub(r"\s+", " ", rewritten)
    for tok in extract_tokens(original, patterns):
        norm_tok = re.sub(r"\s+", " ", tok).strip()
        if norm_tok and norm_tok not in norm_rewritten:
            return False
    return True
