"""Node: enrich — VLM enrichment (GPU only, no-op on pilot)."""
from __future__ import annotations

import logging

from backend.config import ENABLE_VLM_ENRICHMENT
from backend.graph.ingestion.state import IngestionState

log = logging.getLogger("ingestion")


def enrich_node(state: IngestionState) -> IngestionState:
    if not ENABLE_VLM_ENRICHMENT:
        # Pilot path: use existing Ollama-based enrichment
        from backend.tools.pipeline import _enrich_embed_texts
        _enrich_embed_texts(state.get("leaf_chunks", []), state.get("verbose", True))
        return state

    # GPU path: VLM enrichment would go here (Qwen3-VL)
    # Deferred — same structure as docs/graph_update/ingestion_graph.py enrich_node
    log.info("VLM enrichment enabled but not yet integrated — using Ollama fallback")
    from backend.tools.pipeline import _enrich_embed_texts
    _enrich_embed_texts(state.get("leaf_chunks", []), state.get("verbose", True))
    return state
