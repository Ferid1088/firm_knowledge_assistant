"""Node: rerank — Qwen3-Reranker scores the deep pool down to RERANKER_TOP_K.

Enhanced with:
  B1. Heading-path prepended to reranker input
  B2. Multi-field metadata in reranker input
  B3. Cross-lingual reranking (score with translated query, take max)
  B4. Semantic dedup by (doc_id, parent_id) before scoring
  C1. Percentile / min-max normalization of reranker scores
  C2. Drop low-score chunks (keep at least 1)
  C4. Exact-match boost for §-refs, part numbers, quoted strings
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from backend.config import (
    RERANKER_DEDUP_BY_PARENT,
    RERANKER_EXACT_MATCH_BOOST,
    RERANKER_MIN_SCORE,
    RERANKER_NORMALIZE_METHOD,
    RERANKER_TOP_K,
)
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import get_reranker

log = logging.getLogger("retrieval.rerank")

# Regex for exact-match tokens: §-refs, part numbers (XX-123), semver, quoted strings
EXACT_MATCH_RE = re.compile(r'§\s*\d+|[A-Z]{2,}-\d{2,}|\d+\.\d+\.\d+|"([^"]+)"')


# ── B1 + B2: build enhanced text for the reranker ─────────────────────────


def _build_enhanced_text(hit: dict) -> str:
    """Prepend heading path + compact metadata to the chunk text for reranker input."""
    parts: list[str] = []

    # B2: multi-field metadata line (compact, ~30 tokens)
    address = hit.get("address") or {}
    doc_id = address.get("doc_id", "")
    version_num = hit.get("version_num", "?")
    chunk_type = hit.get("chunk_type", "")
    meta_line = f"Document: {doc_id} (v{version_num}, {chunk_type})"
    parts.append(meta_line)

    lang = hit.get("lang", "")
    dates_iso = hit.get("dates_iso", [])
    if dates_iso:
        parts.append(f"Language: {lang} | Dates: {json.dumps(dates_iso)}")
    elif lang:
        parts.append(f"Language: {lang}")

    # B1: heading path
    heading_path = address.get("heading_path", [])
    if heading_path:
        heading = " > ".join(str(h) for h in heading_path)
        parts.append(f"Section: {heading}")

    parts.append("---")
    parts.append(hit.get("context_text", "") or hit.get("text", ""))
    return "\n".join(parts)


# ── B4: semantic dedup by parent_id ────────────────────────────────────────


def _dedup_by_parent(pool: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    """Group hits by (doc_id, parent_id). Keep the highest-retrieval-score representative.

    Returns:
        kept: list of representative hits (one per group)
        deferred: mapping from group key -> deferred siblings
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for h in pool:
        address = h.get("address") or {}
        key = f"{address.get('doc_id', '')}::{h.get('parent_id', '') or address.get('parent_id', '')}"
        groups[key].append(h)

    kept: list[dict] = []
    deferred: dict[str, list[dict]] = {}
    for key, members in groups.items():
        # Sort by retrieval score (rrf_score or retrieval_score if present), descending
        members.sort(
            key=lambda x: x.get("rrf_score", x.get("retrieval_score", 0.0)),
            reverse=True,
        )
        kept.append(members[0])
        if len(members) > 1:
            deferred[key] = members[1:]

    return kept, deferred


# ── C1: score normalization ────────────────────────────────────────────────


def _normalize_scores(
    raw_scores: list[float], method: str = "percentile"
) -> list[float]:
    """Normalize reranker scores using the chosen method."""
    if not raw_scores:
        return []

    if method == "percentile":
        sorted_s = sorted(raw_scores)
        n = max(len(sorted_s) - 1, 1)
        return [sorted_s.index(s) / n for s in raw_scores]
    elif method == "minmax":
        mn, mx = min(raw_scores), max(raw_scores)
        spread = mx - mn + 1e-9
        return [(s - mn) / spread for s in raw_scores]
    else:  # "none"
        return list(raw_scores)


# ── C4: exact-match boost ─────────────────────────────────────────────────


def _extract_exact_tokens(query: str) -> list[str]:
    """Extract exact-match tokens from the query (§ refs, part numbers, quoted strings)."""
    tokens: list[str] = []
    for m in EXACT_MATCH_RE.finditer(query):
        # If it's a quoted string, use the capture group (without quotes)
        if m.group(1):
            tokens.append(m.group(1))
        else:
            # Strip whitespace inside the match (e.g. "§ 3" -> "§3" for matching)
            tokens.append(m.group(0))
    return tokens


def _apply_exact_match_boost(
    pool: list[dict], query: str, boost: float
) -> list[dict]:
    """Add a retrieval-score boost to hits whose text contains exact-match tokens from the query."""
    tokens = _extract_exact_tokens(query)
    if not tokens:
        return pool
    boosted = []
    for h in pool:
        text = (h.get("context_text", "") or h.get("text", "")).lower()
        # Normalize whitespace in text for matching "§ 3" patterns
        text_normalized = re.sub(r"\s+", " ", text)
        matched = any(t.lower() in text_normalized for t in tokens)
        if matched:
            h = {**h, "exact_match_boosted": True}
            # Boost the retrieval score used for dedup ranking
            for key in ("rrf_score", "retrieval_score"):
                if key in h:
                    h[key] = h[key] + boost
                    break
        boosted.append(h)
    return boosted


# ── Main node ──────────────────────────────────────────────────────────────


def rerank(state: RAGState) -> RAGState:
    """Score the candidate pool with Qwen3-Reranker and keep the top RERANKER_TOP_K hits."""
    pool = list(state.get("candidate_pool", []))
    if not pool:
        return {**state, "reranked": []}

    question = state["question"]
    query_lang = state.get("query_lang", "de")
    translated_queries = state.get("translated_queries", {})

    # C4: exact-match boost (applied to retrieval scores before dedup)
    if RERANKER_EXACT_MATCH_BOOST:
        pool = _apply_exact_match_boost(pool, question, RERANKER_EXACT_MATCH_BOOST)

    # B4: semantic dedup by parent_id
    if RERANKER_DEDUP_BY_PARENT:
        pool, deferred = _dedup_by_parent(pool)
        log.debug(
            "Dedup: %d representatives from %d candidates (%d deferred groups)",
            len(pool), len(state.get("candidate_pool", [])), len(deferred),
        )
    else:
        deferred = {}

    reranker = get_reranker()

    # B1 + B2: build enhanced text per hit
    enhanced_texts = [_build_enhanced_text(h) for h in pool]

    # B3: cross-lingual reranking — score with original query first
    pairs = [(question, et) for et in enhanced_texts]
    try:
        scores = reranker.predict(pairs)

        # B3: for hits whose language differs from query_lang and a translated
        # query exists for that language, score again and take max
        cross_lingual_indices: list[int] = []
        cross_lingual_pairs: list[tuple[str, str]] = []
        for i, h in enumerate(pool):
            hit_lang = h.get("lang", "de")
            if hit_lang != query_lang and hit_lang in translated_queries:
                cross_lingual_indices.append(i)
                cross_lingual_pairs.append(
                    (translated_queries[hit_lang], enhanced_texts[i])
                )

        if cross_lingual_pairs:
            alt_scores = reranker.predict(cross_lingual_pairs)
            for idx, alt_score in zip(cross_lingual_indices, alt_scores):
                scores[idx] = max(scores[idx], alt_score)
            log.debug(
                "Cross-lingual reranking: %d hits re-scored with translated queries",
                len(cross_lingual_pairs),
            )

        # C1: normalize scores
        raw_scores = list(scores)
        normalized = _normalize_scores(raw_scores, RERANKER_NORMALIZE_METHOD)

        # Build ranked list with both raw and normalized scores
        ranked = sorted(
            zip(pool, raw_scores, normalized),
            key=lambda x: x[2],
            reverse=True,
        )

        # C2: filter low-score hits (keep at least 1)
        reranked: list[dict] = []
        for hit, raw, norm in ranked[:RERANKER_TOP_K]:
            if norm >= RERANKER_MIN_SCORE or not reranked:
                reranked.append(
                    {**hit, "rerank_score": float(norm), "rerank_score_raw": float(raw)}
                )

        log.info(
            "Reranked %d -> %d hits (method=%s, min_score=%.2f, dedup=%s)",
            len(state.get("candidate_pool", [])),
            len(reranked),
            RERANKER_NORMALIZE_METHOD,
            RERANKER_MIN_SCORE,
            RERANKER_DEDUP_BY_PARENT,
        )
        return {**state, "reranked": reranked, "reranker_failed": False}

    except Exception:
        log.warning(
            "Reranker failed for query '%s' (pool size=%d); falling back to retrieval order",
            question[:80],
            len(pool),
            exc_info=True,
        )
        reranked = pool[:RERANKER_TOP_K]
        return {**state, "reranked": reranked, "reranker_failed": True}
