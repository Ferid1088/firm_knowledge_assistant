"""Qdrant local vector store — dense + named sparse vectors per language, versioning, RRF.

Collection schema:
  vector "dense": Qwen3-Embedding cosine
  sparse vector "sparse_de": BM25 German pipeline
  sparse vector "sparse_en": BM25 English pipeline

Every chunk carries is_current=True; re-ingest sets the old version to False.
"""
from __future__ import annotations
import json
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    PointStruct, SparseVector, Filter, FieldCondition, MatchValue, MatchAny,
)

from backend.config import (
    QDRANT_DIR, QDRANT_COLLECTION, EMBED_DIM,
    RETRIEVE_DEEP_POOL,
)
from backend.services.language import registry

_CLIENT: QdrantClient | None = None
_CLIENT_DIR: str | None = None


def _client(persist_dir: str = QDRANT_DIR) -> QdrantClient:
    """Return a cached QdrantClient, re-opening if persist_dir changed."""
    global _CLIENT, _CLIENT_DIR
    if _CLIENT is None or _CLIENT_DIR != persist_dir:
        if _CLIENT is not None:
            _CLIENT.close()
        _CLIENT = QdrantClient(path=persist_dir)
        _CLIENT_DIR = persist_dir
    return _CLIENT


def get_collection(persist_dir: str = QDRANT_DIR, collection: str = QDRANT_COLLECTION):
    """Return (client, collection_name), creating the collection if it does not exist."""
    client = _client(persist_dir)
    existing = [c.name for c in client.get_collections().collections]
    if collection not in existing:
        sparse_cfg = {ld.sparse_field: SparseVectorParams(index=SparseIndexParams()) for ld in registry.all()}
        client.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=EMBED_DIM, distance=Distance.COSINE)},
            sparse_vectors_config=sparse_cfg,
        )
    return client, collection


def _make_point(
    point_id: int,
    chunk,             # StructuralChunk  # noqa: ANN001 — avoids circular import at module level
    dense_vec: list[float],
    sparse_vecs: dict[str, dict[int, float]],  # {sparse_field: {idx: val}}
    doc_id: str,
    version_id: str,
    sizes: dict,
) -> PointStruct:
    """Build a Qdrant PointStruct from a chunk, its embeddings, and doc-level metadata."""
    from backend.services.citations import chunk_address
    address = chunk_address(chunk, doc_id, sizes)

    vectors: dict[str, Any] = {"dense": dense_vec}
    for field_name, sv in sparse_vecs.items():
        if sv:
            indices = list(sv.keys())
            values = [sv[i] for i in indices]
            vectors[field_name] = SparseVector(indices=indices, values=values)

    # Detect chunk language for sparse field routing
    lang = chunk.metadata.get("lang", "de")
    department_ids = chunk.metadata.get("department_ids", [])
    tbl = chunk.metadata.get("table_structure", {})

    return PointStruct(
        id=point_id,
        vector=vectors,
        payload={
            "doc_id": doc_id,
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type,
            # Dual labels per adaptive parsing spec:
            "semantic_type": chunk.metadata.get("doc_type", ""),      # what is the document
            "structural_type": chunk.metadata.get("structural_type", chunk.chunk_type),  # what is this chunk
            "doc_type": chunk.metadata.get("doc_type", ""),           # alias kept for search() filter compat
            "doc_type_id": chunk.metadata.get("doc_type_id", ""),
            "is_leaf": chunk.is_leaf,
            "parent_id": chunk.parent_id or "",
            "heading_path": json.dumps(chunk.heading_path),
            "text": chunk.text,
            "context_text": chunk.context_text,
            "page": address.get("page") or 0,
            "boxes": json.dumps(address.get("boxes", {})),
            "lang": lang,
            "version_id": version_id,
            "is_current": True,
            "chunk_index_in_parent": chunk.chunk_index_in_parent,
            "department_ids": department_ids,
            # Table-specific structural metadata (only populated for chunk_type="table")
            "table_role": chunk.metadata.get("table_role", ""),
            "table_n_rows": tbl.get("n_rows", 0),
            "table_n_cols": tbl.get("n_cols", 0),
            "table_headers": json.dumps(tbl.get("headers", [])),
        },
    )


def mark_old_version(client: QdrantClient, collection: str, doc_id: str, new_version_id: str):
    """Set is_current=False for all prior versions of this doc."""
    # Scroll all points for this doc that are current and NOT the new version
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="is_current", match=MatchValue(value=True)),
            ]),
            limit=100,
            offset=offset,
        )
        ids_to_update = [r.id for r in results if r.payload.get("version_id") != new_version_id]
        if ids_to_update:
            client.set_payload(
                collection_name=collection,
                payload={"is_current": False},
                points=ids_to_update,
            )
        if offset is None:
            break


def index_chunks(
    collection_tuple,
    chunks,              # list[StructuralChunk]  # noqa: ANN001
    embedder,
    bm25_indices: dict,  # {lang_code: BM25Index}
    doc_id: str,
    sizes: dict,
) -> int:
    """Embed and upsert all leaf chunks; mark the previous version as not-current."""
    from backend.adapters.embedder import embed_texts
    from backend.services.language import registry

    client, collection = collection_tuple
    version_id = str(uuid.uuid4())

    # Mark old version before inserting new
    mark_old_version(client, collection, doc_id, version_id)

    leaf_chunks = [c for c in chunks if c.is_leaf]
    if not leaf_chunks:
        return 0

    texts = [c.context_text for c in leaf_chunks]
    dense_vecs = embed_texts(embedder, texts)

    # Get current max id for offset
    count = client.count(collection_name=collection).count

    points = []
    for i, chunk in enumerate(leaf_chunks):
        lang = chunk.metadata.get("lang", "de")
        ld = registry.get(lang)

        sparse_vecs: dict[str, dict[int, float]] = {}
        bm25 = bm25_indices.get(lang)
        if bm25:
            sparse_vecs[ld.sparse_field] = bm25.sparse_vector(chunk.context_text)

        point = _make_point(
            point_id=count + i,
            chunk=chunk,
            dense_vec=dense_vecs[i].tolist(),
            sparse_vecs=sparse_vecs,
            doc_id=doc_id,
            version_id=version_id,
            sizes=sizes,
        )
        points.append(point)

    client.upsert(collection_name=collection, points=points)
    return len(points)


def _rrf_fuse(result_lists: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion across multiple ranked lists of (point_id, score)."""
    scores: dict[int, float] = {}
    for ranked in result_lists:
        for rank, (pid, _) in enumerate(ranked):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def search(
    collection_tuple,
    embedder,
    query: str,  # noqa: ANN001
    bm25_indices: dict,          # {lang_code: BM25Index}
    active_lang_codes: list[str],
    k: int = RETRIEVE_DEEP_POOL,
    current_only: bool = True,
    allowed_doc_type_ids: list[str] | None = None,  # None = all types allowed
    structural_types: list[str] | None = None,       # e.g. ["table", "list"] — None = all
) -> list[dict]:
    """Dense + sparse BM25 hybrid search with RRF fusion; returns payload dicts."""
    from backend.adapters.embedder import embed_query
    from backend.services.language import registry

    client, collection = collection_tuple

    must_conditions = []
    if current_only:
        must_conditions.append(FieldCondition(key="is_current", match=MatchValue(value=True)))
    # Hard access-control filter: NEVER return chunks from types the user cannot see
    if allowed_doc_type_ids is not None:
        if not allowed_doc_type_ids:
            return []  # user has restrictions but none are active → return nothing
        must_conditions.append(
            FieldCondition(key="doc_type", match=MatchAny(any=allowed_doc_type_ids))
        )
    # Structural type filter: restrict retrieval to specific chunk structures
    if structural_types is not None:
        if not structural_types:
            return []
        must_conditions.append(
            FieldCondition(key="structural_type", match=MatchAny(any=structural_types))
        )
    current_filter = Filter(must=must_conditions) if must_conditions else None

    # ── Dense pass ────────────────────────────────────────────────────────
    q_vec = embed_query(embedder, query).tolist()
    dense_results = client.query_points(
        collection_name=collection,
        query=q_vec,
        using="dense",
        limit=k,
        query_filter=current_filter,
    ).points
    dense_ranked = [(r.id, r.score) for r in dense_results]

    # ── Sparse BM25 passes per active language ────────────────────────────
    all_ranked = [dense_ranked]

    for lang_code in active_lang_codes:
        ld = registry.get(lang_code)
        bm25 = bm25_indices.get(lang_code)
        if bm25 is None:
            continue
        sv = bm25.query_sparse_vector(query)
        if not sv:
            continue
        indices = list(sv.keys())
        values = [sv[idx] for idx in indices]
        try:
            sparse_results = client.query_points(
                collection_name=collection,
                query=SparseVector(indices=indices, values=values),
                using=ld.sparse_field,
                limit=k,
                query_filter=current_filter,
            ).points
            all_ranked.append([(r.id, r.score) for r in sparse_results])
        except Exception:
            pass  # sparse field may be empty for a new collection

    # ── RRF fusion ────────────────────────────────────────────────────────
    fused = _rrf_fuse(all_ranked)[:k]

    # ── Fetch payloads for fused top-k ────────────────────────────────────
    top_ids = [pid for pid, _ in fused]
    if not top_ids:
        return []

    id_to_score = {pid: score for pid, score in fused}
    fetched = client.retrieve(collection_name=collection, ids=top_ids, with_payload=True)

    hits = []
    for r in fetched:
        p = r.payload
        hits.append({
            "text": p.get("text", ""),
            "context_text": p.get("context_text", ""),
            "chunk_id": p.get("chunk_id", ""),
            "chunk_type": p.get("chunk_type", "prose"),
            "parent_id": p.get("parent_id", ""),
            "lang": p.get("lang", "de"),
            "address": {
                "doc_id": p.get("doc_id", ""),
                "page": p.get("page", 0),
                "heading_path": json.loads(p.get("heading_path", "[]")),
                "boxes": json.loads(p.get("boxes", "{}")),
            },
            "score": id_to_score.get(r.id, 0.0),
        })

    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits
