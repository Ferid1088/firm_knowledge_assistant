"""PHASE 2 — post-chunk cleanup (deterministic-first).

Step 4: empty / low-substance leaf filter. Drops PROSE leaves whose cleaned
text is only punctuation/whitespace or below a minimum length. Tables (and
recommendation leaves) are exempt — a "-" cell can mean "no value" and the
table/clause is kept whole.
"""
from __future__ import annotations
import re

_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)
_LOW_SUBSTANCE_VALUES = {"n/a", "na", "k.a.", "k. a."}


def is_low_substance_leaf(chunk_type: str, text: str, structure_cfg: dict) -> bool:
    """True if this leaf should be dropped before indexing."""
    if chunk_type != "prose":
        return False  # tables/recommendations kept whole, never filtered here

    t = text.strip()
    if not t:
        return True
    if len(t) < structure_cfg.get("min_prose_chars", 3):
        return True
    if _PUNCT_ONLY.match(t):
        return True
    if t.lower() in _LOW_SUBSTANCE_VALUES:
        return True
    return False


def filter_empty_leaves(chunks: list, structure_cfg: dict) -> tuple[list, int]:
    """Return (kept_chunks, dropped_count). Non-leaf nodes pass through untouched."""
    kept = []
    dropped = 0
    for c in chunks:
        if c.is_leaf and is_low_substance_leaf(c.chunk_type, c.text, structure_cfg):
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped


# ── Step 6: cross-reference extraction (best-effort) ──────────────────────

def extract_references(text: str, structure_cfg: dict) -> list[str]:
    """Find "siehe § 17 Abs. 2" / "vgl. § ..." style cross-references.

    Looks for an xref trigger phrase, then the nearest reference_patterns
    match within a short window after it. Best-effort: returns [] if the
    corpus has no such phrasing — never blocks ingestion.
    """
    ref_pats = [re.compile(p) for p in structure_cfg.get("reference_patterns", [])]
    xref_pats = [re.compile(p, re.IGNORECASE) for p in structure_cfg.get("xref_patterns", [])]

    refs: list[str] = []
    for xp in xref_pats:
        for m in xp.finditer(text):
            window = text[m.end():m.end() + 40]
            for rp in ref_pats:
                rm = rp.search(m.group(0) + window)
                if rm:
                    refs.append(rm.group(0))
                    break

    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def attach_references(chunks: list, structure_cfg: dict) -> None:
    """Set metadata["references"] on every leaf chunk, in place."""
    for c in chunks:
        if c.is_leaf:
            c.metadata["references"] = extract_references(c.text, structure_cfg)


# ── Step 3/5: orphan attachment + list cohesion ────────────────────────────

def _is_label(text: str, header_cfg: dict) -> bool:
    """Same predicate as rules.is_pseudo_header, applied to already-demoted
    leaf text — identifies "Frage 1:"/"Antwort:"/"Nein."-style labels that are
    now standalone tiny prose leaves and should absorb the following leaf."""
    t = text.strip()
    if any(t.endswith(s) for s in header_cfg.get("label_suffixes", [])):
        return True
    if header_cfg.get("demote_single_stopword", False):
        words = t.split()
        if len(words) == 1:
            bare = re.sub(r"[^\w]", "", words[0]).lower()
            if bare in header_cfg.get("label_stopwords", []):
                return True
    return False


def _is_list_item(text: str, list_pats: list[re.Pattern]) -> bool:
    return any(p.match(text.strip()) for p in list_pats)


def _heading_path_str(path: list[str]) -> str:
    return " > ".join(path) if path else ""


def _merge_leaf_group(group: list) -> "object":
    """Merge a group of leaf StructuralChunks (same heading_path) into one,
    joining their text with newlines and rebuilding context_text."""
    first = group[0]
    text = "\n".join(c.text for c in group)
    ctx = _heading_path_str(first.heading_path)
    context_text = f"{ctx}\n\n{text}".strip() if ctx else text

    doc_items = []
    for c in group:
        doc_items.extend(c.doc_items)

    first.text = text
    first.context_text = context_text
    first.doc_items = doc_items
    return first


def merge_orphans_and_lists(chunks: list, structure_cfg: dict) -> tuple[list, int]:
    """Attach standalone label leaves ("Frage 1:", "Antwort:", "Nein.") to the
    leaf that follows them, and merge consecutive list-marker items under the
    same heading into one cohesive chunk. Returns (chunks, n_merged)."""
    header_cfg = structure_cfg.get("header", {})
    list_pats = [re.compile(p) for p in structure_cfg.get("list_markers", [])]

    out = []
    n_merged = 0
    i, n = 0, len(chunks)
    while i < n:
        c = chunks[i]
        if not (c.is_leaf and c.chunk_type == "prose"):
            out.append(c)
            i += 1
            continue

        group = [c]
        j = i + 1

        # (a) orphan label(s) absorb the following leaf, chained
        while _is_label(group[-1].text, header_cfg) and j < n \
                and chunks[j].is_leaf and chunks[j].chunk_type == "prose" \
                and chunks[j].heading_path == c.heading_path:
            group.append(chunks[j])
            j += 1

        # (b) list cohesion: merge consecutive list-marker items
        if len(group) == 1 and _is_list_item(c.text, list_pats):
            while j < n and chunks[j].is_leaf and chunks[j].chunk_type == "prose" \
                    and chunks[j].heading_path == c.heading_path \
                    and _is_list_item(chunks[j].text, list_pats):
                group.append(chunks[j])
                j += 1

        if len(group) > 1:
            out.append(_merge_leaf_group(group))
            n_merged += len(group) - 1
            i = j
        else:
            out.append(c)
            i += 1

    return out, n_merged
