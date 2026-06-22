# Phase 4 Report — Flow Optimizations D1, D2, D3

## D1. Progressive max_length + pool widening on escalation

**State fields added** (`state.py`):
- `reranker_max_length: Optional[int]` — current reranker window, doubles on escalation
- `retrieve_pool_size: Optional[int]` — current pool size, doubles on escalation

**Config constants added** (`config.py`):
- `RERANKER_MAX_LENGTH_CAP = 4096` — hard ceiling for reranker window
- `RETRIEVE_DEEP_POOL_CAP = 200` — hard ceiling for retrieval pool

**escalate.py**: Now doubles both `retrieve_pool_size` and `reranker_max_length` each
iteration, capped at the configured maximums. First escalation: 50→100 pool, 1024→2048
max_length. Second: 100→200 pool, 2048→4096 max_length.

**retrieve.py**: Reads `retrieve_pool_size` from state (fallback to `RETRIEVE_DEEP_POOL`).

**rerank.py**: Reads `reranker_max_length` from state (fallback to `RERANKER_MAX_LENGTH`),
passes it to `reranker.predict(max_length=...)`.

**reranker.py** (adapter): `predict()` now accepts an optional `max_length` parameter that
overrides the instance default for that call, clamped to `EMBED_MAX_SEQ`.

## D2. Cache reranker scores across escalation

**State field added** (`state.py`):
- `reranker_cache: Optional[dict]` — `{chunk_id: float}` mapping scores from prior iterations

**rerank.py**: Before scoring, checks each hit's `chunk_id` against the cache. Cached hits
skip the (expensive) reranker inference. After scoring, all results are written back to the
cache. The escalate node preserves the cache (does not clear it).

This means on escalation loop 2, only the *newly retrieved* chunks (from the wider pool) are
scored — chunks already scored in loop 1 are served from cache.

## D3. Parent-child context expansion (new node)

**New file**: `backend/graph/retrieval/nodes/expand_context.py`

For each reranked hit:
1. Fetches the parent chunk by `parent_id` from Qdrant (cached per parent to avoid duplicates)
2. Prepends the parent heading path (or text snippet) as context
3. Token budget (`EXPANSION_TOKEN_BUDGET = 1024`) allocated proportionally to rerank_score
4. If `ENABLE_SIBLING_EXPANSION` is True (OFF by default), fetches ±1 siblings (excluding tables)
5. Produces `expanded_context` list — identical to reranked but with `expanded_text` field added
6. Citations still resolve to the precise child chunk (original fields preserved)

**Graph topology** (`graph.py`):
```
prepare_query → retrieve → rerank → expand_context → score_confidence → router
```

## Files modified

| File | Change |
|------|--------|
| `backend/graph/retrieval/state.py` | +5 new state fields |
| `backend/config.py` | +3 new constants |
| `backend/adapters/reranker.py` | `predict()` accepts optional `max_length` |
| `backend/graph/retrieval/nodes/escalate.py` | Progressive doubling + cache preservation |
| `backend/graph/retrieval/nodes/retrieve.py` | Reads pool size from state |
| `backend/graph/retrieval/nodes/rerank.py` | max_length from state + score caching |
| `backend/graph/retrieval/nodes/expand_context.py` | **NEW** — parent-child expansion |
| `backend/graph/retrieval/nodes/__init__.py` | Export `expand_context` |
| `backend/graph/retrieval/graph.py` | Insert `expand_context` node in topology |

## Test results

All 96 tests pass (0 failures, 0 errors).
