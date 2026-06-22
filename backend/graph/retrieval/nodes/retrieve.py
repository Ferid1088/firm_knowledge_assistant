"""Node: retrieve — bidirectional hybrid (dense + per-language BM25) fan-out
with RRF fusion into a deep candidate pool."""
from __future__ import annotations

from backend.config import ENABLE_TRANSLATED_BM25, RETRIEVE_DEEP_POOL
from backend.graph.retrieval.state import RAGState
from backend.graph.retrieval.utils import get_collection, get_embedder, get_bm25_indices


def retrieve(state: RAGState) -> RAGState:
    """Run dense + per-language BM25 fan-out for every sub-question and fuse results with RRF."""
    from backend.services.store import search as store_search

    sub_questions = state.get("sub_questions", [state["question"]])
    active_codes = state.get("active_lang_codes", ["de"])
    translated = state.get("translated_queries", {})
    bm25_indices = get_bm25_indices()
    k = RETRIEVE_DEEP_POOL

    all_hits: list[dict] = []
    seen_ids: set[str] = set()

    allowed_doc_type_ids = state.get("allowed_doc_type_ids", None)
    structural_types = state.get("structural_types", None)
    date_from = state.get("date_filter_from")
    date_to = state.get("date_filter_to")

    for sub_q in sub_questions:
        # Dense pass uses the original query (cross-lingual model handles it)
        hits = store_search(
            get_collection(),
            get_embedder(),
            sub_q,
            bm25_indices,
            active_codes,
            k=k,
            allowed_doc_type_ids=allowed_doc_type_ids,
            structural_types=structural_types,
            date_from=date_from,
            date_to=date_to,
        )
        for h in hits:
            cid = h["chunk_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_hits.append(h)

    # For translated BM25 passes, run a second pass per language with the translated query
    if ENABLE_TRANSLATED_BM25:
        for lang_code, trans_q in translated.items():
            if trans_q == sub_questions[0]:
                continue  # already covered
            hits = store_search(
                get_collection(),
                get_embedder(),
                trans_q,
                bm25_indices,
                [lang_code],
                k=k // 2,
                allowed_doc_type_ids=allowed_doc_type_ids,
                structural_types=structural_types,
                date_from=date_from,
                date_to=date_to,
            )
            for h in hits:
                cid = h["chunk_id"]
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_hits.append(h)

    # Sort by score, keep deep pool
    all_hits.sort(key=lambda x: x["score"], reverse=True)
    return {**state, "candidate_pool": all_hits[:k]}
