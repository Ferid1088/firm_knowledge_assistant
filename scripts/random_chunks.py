#!/usr/bin/env python3
"""Print 10 random chunks from the current Qdrant collection.

Usage:
    python scripts/random_chunks.py
    python scripts/random_chunks.py --count 5
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qdrant_client.models import Filter, FieldCondition, MatchValue

from backend.services.store import get_collection


def format_payload(payload: dict[str, Any]) -> str:
    heading_path = payload.get("heading_path")
    if isinstance(heading_path, str):
        try:
            heading_path_list = json.loads(heading_path)
            heading_path = " > ".join(heading_path_list)
        except json.JSONDecodeError:
            heading_path = heading_path
    text = (payload.get('text') or '').replace('\n', ' ').replace('\r', ' ')
    preview = text[:300]
    ellipsis = '...' if len(text) > 300 else ''
    return (
        f"chunk_id:     {payload.get('chunk_id')}\n"
        f"doc_id:       {payload.get('doc_id')}\n"
        f"chunk_type:   {payload.get('chunk_type')}\n"
        f"lang:         {payload.get('lang')}\n"
        f"page:         {payload.get('page')}\n"
        f"heading_path: {heading_path}\n"
        f"version_id:   {payload.get('version_id')}\n"
        f"is_current:   {payload.get('is_current')}\n"
        f"text:         {preview}{ellipsis}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10, help="How many random chunks to show")
    args = parser.parse_args()

    client, collection = get_collection()
    total = client.count(collection_name=collection).count
    if total == 0:
        print(f"No chunks found in collection '{collection}'.")
        return

    count = min(args.count, total)
    indices = random.sample(range(total), count)
    indices.sort()

    chunks: list[dict[str, Any]] = []
    for offset in indices:
        results, _ = client.scroll(
            collection_name=collection,
            limit=1,
            offset=offset,
            with_payload=True,
            scroll_filter=Filter(must=[FieldCondition(key="is_current", match=MatchValue(value=True))]),
        )
        if results:
            chunks.append(results[0].payload)

    for i, payload in enumerate(chunks, start=1):
        print(f"--- chunk {i}/{len(chunks)} ---")
        print(format_payload(payload))


if __name__ == "__main__":
    main()
