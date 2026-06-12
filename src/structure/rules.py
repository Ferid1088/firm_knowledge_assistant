"""Deterministic structure-correction predicates, driven by config.STRUCTURE.

No corpus-specific patterns live here — everything is read from the STRUCTURE
dict passed in by the caller (see config.py).
"""
from __future__ import annotations
import re


def is_pseudo_header(text: str, structure_cfg: dict) -> bool:
    """True if a Docling SECTION_HEADER/TITLE is actually a form label, not a
    real section title (e.g. "Antwort:", "Frage 3:").

    Demoting it removes the artificial chunk-merge boundary it would otherwise
    create (see indexing_correction.md, PHASE 1 step 1).
    """
    t = text.strip()
    if not t:
        return True

    cfg = structure_cfg.get("header", {})
    suffixes = cfg.get("label_suffixes", [])
    if any(t.endswith(s) for s in suffixes):
        return True

    if cfg.get("demote_single_stopword", False):
        words = t.split()
        if len(words) == 1:
            bare = re.sub(r"[^\w]", "", words[0]).lower()
            if bare in cfg.get("label_stopwords", []):
                return True

    return False


def is_ambiguous_header(text: str, structure_cfg: dict) -> bool:
    """True if a SECTION_HEADER/TITLE is short enough to plausibly be a form
    label, but wasn't already deterministically demoted by `is_pseudo_header`.

    Such headers are flagged for the (optional, label-only) LLM classifier —
    see indexing_correction.md, step 6.
    """
    cfg = structure_cfg.get("header", {})
    if not cfg.get("flag_ambiguous_short_headers", False):
        return False
    if is_pseudo_header(text, structure_cfg):
        return False

    t = text.strip()
    words = t.split()
    return len(words) <= cfg.get("max_label_words", 3) or len(t) <= cfg.get("max_label_chars", 25)
