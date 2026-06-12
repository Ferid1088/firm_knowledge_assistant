"""Recall@k comparison: query rewrite OFF vs ON.

Runs only the "rewrite_colloquial" cases from eval/eval_set.json. For each:
  - OFF: search with the original query only.
  - ON:  also rewrite the query (dictionary + LLM, post-checked) and
         RRF-fuse its results with the original — same mechanism used by the
         `escalate` -> `retrieve` rung in the LangGraph pipeline.

Requires exclusive access to .qdrant — stop the running backend first:
    ./run.sh stop   (or kill the uvicorn process)
    python -m eval.rewrite_eval --k 5
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import QDRANT_DIR, OLLAMA_MODEL, REWRITE
from backend.adapters.embedder import load_embedder
from backend.services.store import get_collection, search as store_search
from backend.tools.pdf_ingest import rebuild_bm25_indices
from backend.services.language import registry
from backend.tools.rewriter import rewrite_query
from backend.services.fusion import rrf_fuse_hits
from eval.recall_harness import load_eval_set, hits_contain_keyword


def run_eval(k: int = 5) -> None:
    embedder = load_embedder()
    collection_tuple = get_collection(QDRANT_DIR)
    bm25_indices = rebuild_bm25_indices(QDRANT_DIR)
    active_codes = [ld.code for ld in registry.all()]

    cases = [c for c in load_eval_set() if c.get("case_type") == "rewrite_colloquial"]
    if not cases:
        print("No 'rewrite_colloquial' cases in eval/eval_set.json.")
        return

    off_hits = 0
    on_hits = 0

    for case in cases:
        query = case["query"]
        keywords = case.get("expected_keywords", [])
        lang = case.get("query_lang", "de")

        baseline = store_search(collection_tuple, embedder, query, bm25_indices, active_codes, k=k)
        ok_off = hits_contain_keyword(baseline, keywords)
        off_hits += ok_off

        rewritten = rewrite_query(query, lang, REWRITE, OLLAMA_MODEL)
        if rewritten:
            rewrite_hits = store_search(collection_tuple, embedder, rewritten, bm25_indices, active_codes, k=k)
            fused = rrf_fuse_hits([baseline, rewrite_hits])[:k]
        else:
            fused = baseline
        ok_on = hits_contain_keyword(fused, keywords)
        on_hits += ok_on

        print(f"[{case['id']}] {query}")
        print(f"  rewritten: {rewritten!r}")
        print(f"  OFF: {'HIT' if ok_off else 'MISS'}   ON: {'HIT' if ok_on else 'MISS'}")

    total = len(cases)
    print(f"\nRecall@{k} OFF: {off_hits}/{total} = {off_hits/total:.1%}")
    print(f"Recall@{k} ON:  {on_hits}/{total} = {on_hits/total:.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    run_eval(k=args.k)
