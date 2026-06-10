"""Recall@k harness for the RAG retrieval pipeline.

Usage:
    python -m eval.recall_harness --k 5

Measures: for each eval case, is at least one expected keyword present in the top-k chunks?
Prints per-case results and aggregate recall@k.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import QDRANT_DIR, RETRIEVE_DEEP_POOL
from src.common.embed import load_embedder
from src.common.store import get_collection, search as store_search
from src.ingest.pipeline import rebuild_bm25_indices
from src.common.language import registry


def load_eval_set(path: str = "eval/eval_set.json") -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data["cases"]


def hits_contain_keyword(hits: list[dict], keywords: list[str]) -> bool:
    if not keywords:
        return True  # vague queries — no keyword requirement
    for h in hits:
        text = (h.get("text", "") + " " + h.get("context_text", "")).lower()
        if any(kw.lower() in text for kw in keywords):
            return True
    return False


def run_eval(k: int = 5, verbose: bool = True) -> dict:
    embedder = load_embedder()
    collection_tuple = get_collection(QDRANT_DIR)
    bm25_indices = rebuild_bm25_indices(QDRANT_DIR)
    active_codes = [ld.code for ld in registry.all()]

    cases = load_eval_set()
    results = []
    hit_count = 0

    for case in cases:
        qid = case["id"]
        query = case["query"]
        keywords = case.get("expected_keywords", [])
        expected_abstain = case.get("expected_abstain", False)

        hits = store_search(
            collection_tuple,
            embedder,
            query,
            bm25_indices,
            active_codes,
            k=k,
        )

        if expected_abstain:
            # For vague queries just check that we get low scores
            top_score = hits[0]["score"] if hits else 0.0
            ok = top_score < 0.5
            label = "abstain_expected"
        else:
            ok = hits_contain_keyword(hits[:k], keywords)
            label = "HIT" if ok else "MISS"

        if ok:
            hit_count += 1

        if verbose:
            top_score = hits[0]["score"] if hits else 0.0
            print(f"[{label}] {qid:20s} | score={top_score:.3f} | {query[:60]}")
            if not ok and not expected_abstain:
                print(f"         expected one of: {keywords}")
                print(f"         top chunk: {hits[0]['text'][:120] if hits else '(none)'}")

        results.append({"id": qid, "hit": ok, "type": case.get("case_type", "")})

    total = len(cases)
    recall = hit_count / total if total else 0.0
    print(f"\nRecall@{k}: {hit_count}/{total} = {recall:.1%}")

    # Per-type breakdown
    by_type: dict[str, list[bool]] = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r["hit"])
    for t, hits_list in by_type.items():
        n = len(hits_list)
        h = sum(hits_list)
        print(f"  {t:20s}: {h}/{n} = {h/n:.1%}")

    return {"recall_at_k": recall, "k": k, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    run_eval(k=args.k)
