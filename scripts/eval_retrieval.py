"""Retrieval eval harness: MRR, Recall@50, Hit@5 against a golden set.

Usage:
    python -m scripts.eval_retrieval [--golden eval/retrieval_golden.json] [--k 5]

Loads the golden set, runs each query through retrieve + rerank (no answer),
computes metrics, prints a table, and saves timestamped results to eval/results/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import QDRANT_DIR, RETRIEVE_DEEP_POOL, RERANKER_TOP_K
from backend.graph.retrieval.utils import (
    get_collection,
    get_embedder,
    get_bm25_indices,
    get_reranker,
)
from backend.services.store import search as store_search
from backend.services.language import registry
from backend.tools.pipeline import rebuild_bm25_indices
from backend.graph.retrieval.nodes import set_bm25_indices


def load_golden(path: str) -> list[dict]:
    """Load the golden eval set from JSON."""
    with open(path) as f:
        return json.load(f)


def _doc_id_from_hit(hit: dict) -> str:
    """Extract the doc_id from a search hit (nested under address or top-level)."""
    addr = hit.get("address", {})
    return addr.get("doc_id", "") or hit.get("doc_id", "")


def _reciprocal_rank(hits: list[dict], expected_doc_id: str) -> float:
    """Return 1/rank of the first hit matching expected_doc_id, or 0.0 if absent."""
    for i, h in enumerate(hits):
        if _doc_id_from_hit(h) == expected_doc_id:
            return 1.0 / (i + 1)
    return 0.0


def run_eval(golden_path: str, top_k: int = 5) -> dict:
    """Run retrieval eval and return metrics dict."""
    golden = load_golden(golden_path)
    if not golden:
        print("ERROR: golden set is empty")
        return {}

    # Bootstrap models and indices
    embedder = get_embedder()
    collection_tuple = get_collection(QDRANT_DIR)
    bm25 = rebuild_bm25_indices(QDRANT_DIR)
    set_bm25_indices(bm25)
    bm25_indices = get_bm25_indices()
    active_codes = [ld.code for ld in registry.all()]

    reranker = get_reranker()

    results = []
    mrr_sum = 0.0
    recall50_hits = 0
    hitk_hits = 0

    print(f"\n{'ID':<8} {'Lang':<4} {'Type':<16} {'MRR':>6} {'R@50':>5} {'H@{0}':>5} Query".format(top_k))
    print("-" * 100)

    for case in golden:
        query = case["query"]
        expected = case["expected_doc_id"]
        lang = case.get("lang", "de")
        case_type = case.get("case_type", "unknown")

        # Retrieve deep pool (Recall@50)
        pool = store_search(
            collection_tuple, embedder, query,
            bm25_indices, active_codes,
            k=RETRIEVE_DEEP_POOL,
        )

        recall50 = any(_doc_id_from_hit(h) == expected for h in pool)

        # Rerank the pool
        if pool and reranker:
            pairs = [(query, h["context_text"]) for h in pool]
            try:
                scores = reranker.predict(pairs)
                ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)
                reranked = [{**h, "rerank_score": float(s)} for h, s in ranked[:RERANKER_TOP_K]]
            except Exception as e:
                print(f"  WARNING: reranker failed for '{query[:40]}': {e}")
                reranked = pool[:RERANKER_TOP_K]
        else:
            reranked = pool[:RERANKER_TOP_K]

        # MRR on reranked list
        mrr = _reciprocal_rank(reranked, expected)

        # Hit@k on top-k of reranked
        hit_k = any(_doc_id_from_hit(h) == expected for h in reranked[:top_k])

        mrr_sum += mrr
        if recall50:
            recall50_hits += 1
        if hit_k:
            hitk_hits += 1

        r50_str = "Y" if recall50 else "N"
        hk_str = "Y" if hit_k else "N"
        print(f"{case_type:<16} {lang:<4} {case_type:<16} {mrr:>6.3f} {r50_str:>5} {hk_str:>5} {query[:50]}")

        results.append({
            "query": query,
            "expected_doc_id": expected,
            "lang": lang,
            "case_type": case_type,
            "mrr": mrr,
            "recall_at_50": recall50,
            "hit_at_k": hit_k,
            "pool_size": len(pool),
            "reranked_size": len(reranked),
        })

    n = len(golden)
    metrics = {
        "MRR": mrr_sum / n if n else 0.0,
        "Recall@50": recall50_hits / n if n else 0.0,
        f"Hit@{top_k}": hitk_hits / n if n else 0.0,
        "n_queries": n,
        "top_k": top_k,
    }

    print("-" * 100)
    print(f"\nAggregate metrics (n={n}):")
    print(f"  MRR:       {metrics['MRR']:.3f}")
    print(f"  Recall@50: {metrics['Recall@50']:.1%}")
    print(f"  Hit@{top_k}:    {metrics[f'Hit@{top_k}']:.1%}")

    # Per-type breakdown
    by_type: dict[str, list[dict]] = {}
    for r in results:
        by_type.setdefault(r["case_type"], []).append(r)

    print("\nPer-type breakdown:")
    for t, items in sorted(by_type.items()):
        t_mrr = sum(i["mrr"] for i in items) / len(items)
        t_r50 = sum(1 for i in items if i["recall_at_50"]) / len(items)
        t_hk = sum(1 for i in items if i["hit_at_k"]) / len(items)
        print(f"  {t:<16}: MRR={t_mrr:.3f}  R@50={t_r50:.0%}  H@{top_k}={t_hk:.0%}  (n={len(items)})")

    # Save timestamped results
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("eval/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_{ts}.json"
    with open(out_path, "w") as f:
        json.dump({"metrics": metrics, "results": results, "timestamp": ts}, f, indent=2)
    print(f"\nResults saved to {out_path}")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run retrieval eval against a golden set")
    parser.add_argument("--golden", default="eval/retrieval_golden.json", help="Path to golden set JSON")
    parser.add_argument("--k", type=int, default=5, help="Top-k for Hit@k metric")
    args = parser.parse_args()
    run_eval(args.golden, args.k)
