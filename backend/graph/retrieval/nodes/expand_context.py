"""Node: expand_context — parent-child context expansion (D3).

For each reranked hit, fetch its parent chunk by parent_id from Qdrant and
prepend the parent heading text.  Token budget is allocated proportionally to
rerank_score so the highest-scoring hits get the most context.

If ENABLE_SIBLING_EXPANSION is True, also fetch +/-1 siblings (OFF by default).
Citations still resolve to the precise child chunk — expanded text is for the
answer node's context only.
"""
from __future__ import annotations

import json
import logging

from backend.config import ENABLE_SIBLING_EXPANSION, EXPANSION_TOKEN_BUDGET
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import get_collection

log = logging.getLogger("retrieval.expand_context")


def _fetch_chunk_by_id(client, collection: str, chunk_id: str) -> dict | None:
    """Fetch a single chunk's payload from Qdrant by chunk_id field (payload filter)."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    results = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id)),
            FieldCondition(key="is_current", match=MatchValue(value=True)),
        ]),
        limit=1,
        with_payload=True,
    )[0]
    if results:
        return results[0].payload
    return None


def _fetch_siblings(client, collection: str, parent_id: str, doc_id: str, exclude_chunk_id: str) -> list[dict]:
    """Fetch siblings (children of the same parent) for sibling expansion."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    results = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="parent_id", match=MatchValue(value=parent_id)),
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="is_current", match=MatchValue(value=True)),
        ]),
        limit=10,
        with_payload=True,
    )[0]
    siblings = []
    for r in results:
        p = r.payload
        if p.get("chunk_id") != exclude_chunk_id:
            siblings.append(p)
    # Sort by chunk_index_in_parent for ordering
    siblings.sort(key=lambda x: x.get("chunk_index_in_parent", 0))
    return siblings


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed de/en text."""
    return max(1, len(text) // 4)


def expand_context(state: RAGState) -> RAGState:
    """Expand reranked hits with parent heading context (and optionally siblings).

    Produces expanded_context: list of dicts identical to reranked hits but with
    an additional 'expanded_text' field containing the parent heading + child text.
    The original fields (text, chunk_id, boxes, address) are preserved for citations.
    """
    reranked = state.get("reranked", [])
    if not reranked:
        return {**state, "expanded_context": []}

    try:
        client, collection = get_collection()
    except Exception:
        log.warning("Could not connect to Qdrant for context expansion; passing through reranked hits")
        return {**state, "expanded_context": reranked}

    # Allocate token budget proportionally to rerank_score
    total_score = sum(h.get("rerank_score", 0.0) for h in reranked) or 1.0
    budget_remaining = EXPANSION_TOKEN_BUDGET

    # Cache parent lookups to avoid duplicate fetches
    parent_cache: dict[str, dict | None] = {}

    expanded: list[dict] = []
    for hit in reranked:
        parent_id = hit.get("parent_id", "")
        chunk_id = hit.get("chunk_id", "")
        child_text = hit.get("context_text", "") or hit.get("text", "")

        # Proportional budget for this hit
        hit_score = hit.get("rerank_score", 0.0)
        hit_budget = int(EXPANSION_TOKEN_BUDGET * (hit_score / total_score))
        hit_budget = min(hit_budget, budget_remaining)

        expanded_parts: list[str] = []
        tokens_used = 0

        # Fetch parent heading if parent_id exists
        if parent_id and hit_budget > 0:
            if parent_id not in parent_cache:
                parent_cache[parent_id] = _fetch_chunk_by_id(client, collection, parent_id)

            parent = parent_cache[parent_id]
            if parent:
                # Use the parent's heading_path or text as context
                heading_path = parent.get("heading_path", "[]")
                try:
                    headings = json.loads(heading_path) if isinstance(heading_path, str) else heading_path
                except (json.JSONDecodeError, TypeError):
                    headings = []

                if headings:
                    heading_text = " > ".join(str(h) for h in headings)
                    heading_tokens = _estimate_tokens(heading_text)
                    if heading_tokens <= hit_budget:
                        expanded_parts.append(f"[Section: {heading_text}]")
                        tokens_used += heading_tokens
                else:
                    # Fall back to parent text snippet
                    parent_text = parent.get("text", "")
                    if parent_text:
                        available = hit_budget - tokens_used
                        snippet = parent_text[:available * 4]  # ~4 chars/token
                        snippet_tokens = _estimate_tokens(snippet)
                        if snippet_tokens > 0:
                            expanded_parts.append(f"[Parent: {snippet}]")
                            tokens_used += snippet_tokens

        # D3: optional sibling expansion (OFF by default)
        if ENABLE_SIBLING_EXPANSION and parent_id and (hit_budget - tokens_used) > 50:
            doc_id = (hit.get("address") or {}).get("doc_id", "")
            if doc_id:
                siblings = _fetch_siblings(client, collection, parent_id, doc_id, chunk_id)

                # Find this hit's index among siblings
                child_idx = hit.get("chunk_index_in_parent", 0)
                # Get +/-1 neighbors
                neighbor_texts: list[str] = []
                for sib in siblings:
                    sib_idx = sib.get("chunk_index_in_parent", 0)
                    if abs(sib_idx - child_idx) == 1:
                        sib_text = sib.get("context_text", "") or sib.get("text", "")
                        if sib_text:
                            # Never expand table chunks as siblings
                            if sib.get("chunk_type", "") != "table":
                                neighbor_texts.append(sib_text)

                for nt in neighbor_texts:
                    remaining = hit_budget - tokens_used
                    if remaining <= 0:
                        break
                    snippet = nt[:remaining * 4]
                    snippet_tokens = _estimate_tokens(snippet)
                    expanded_parts.append(f"[Sibling: {snippet}]")
                    tokens_used += snippet_tokens

        # Build expanded text: parent context + original child text
        if expanded_parts:
            expanded_text = "\n".join(expanded_parts) + "\n---\n" + child_text
        else:
            expanded_text = child_text

        budget_remaining -= tokens_used

        expanded.append({
            **hit,
            "expanded_text": expanded_text,
        })

    log.info(
        "Expanded context for %d hits (budget=%d, siblings=%s)",
        len(expanded), EXPANSION_TOKEN_BUDGET, ENABLE_SIBLING_EXPANSION,
    )
    return {**state, "expanded_context": expanded}
