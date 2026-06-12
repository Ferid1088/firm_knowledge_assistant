"""Print sample chunks currently stored in the Qdrant collection.

Usage:
    python -m scripts.show_chunks [--limit N] [--all-versions]
"""
from __future__ import annotations
import argparse
import json

from qdrant_client.models import Filter, FieldCondition, MatchValue

from backend.services.store import get_collection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="number of chunks to show (default: 10)")
    parser.add_argument("--all-versions", action="store_true", help="include superseded (is_current=False) chunks")
    args = parser.parse_args()

    client, collection = get_collection()

    scroll_filter = None
    if not args.all_versions:
        scroll_filter = Filter(must=[FieldCondition(key="is_current", match=MatchValue(value=True))])

    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        limit=args.limit,
        with_payload=True,
    )

    if not points:
        print(f"No chunks found in collection '{collection}'.")
        return

    for i, point in enumerate(points, start=1):
        p = point.payload
        heading_path = json.loads(p.get("heading_path", "[]"))
        text = (p.get("text") or "")[:200].replace("\n", " ")
        print(f"--- chunk {i}/{len(points)} ---")
        print(f"chunk_id:     {p.get('chunk_id')}")
        print(f"doc_id:       {p.get('doc_id')}")
        print(f"chunk_type:   {p.get('chunk_type')}")
        print(f"lang:         {p.get('lang')}")
        print(f"page:         {p.get('page')}")
        print(f"heading_path: {' > '.join(heading_path)}")
        print(f"version_id:   {p.get('version_id')}")
        print(f"is_current:   {p.get('is_current')}")
        print(f"text:         {text}{'...' if len(p.get('text') or '') > 200 else ''}")
        print()


if __name__ == "__main__":
    main()
