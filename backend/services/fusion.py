"""Reciprocal Rank Fusion over retrieval hit dicts (keyed by chunk_id).

Mirrors src.common.store._rrf_fuse, which fuses Qdrant point-id rankings
within a single search() call. This variant fuses ACROSS multiple search()
calls (e.g. original query vs. rewritten query), each returning hit dicts.
"""
from __future__ import annotations


def rrf_fuse_hits(result_lists: list[list[dict]], key: str = "chunk_id", k: int = 60) -> list[dict]:
    """Fuse multiple ranked hit-dict lists into one, ranked by RRF score."""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for ranked in result_lists:
        for rank, hit in enumerate(ranked):
            cid = hit.get(key)
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in items:
                items[cid] = hit

    fused = []
    for cid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        hit = {**items[cid], "score": score}
        fused.append(hit)
    return fused
