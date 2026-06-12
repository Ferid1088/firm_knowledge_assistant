"""Query-rewrite module: reactive escalation rung that closes the vocabulary
gap between colloquial queries and corpus terminology.

See Query_Rewrite Module_Implementation_Spec.md for the full design.
"""
from src.rewrite.rewriter import rewrite_query
from src.rewrite.fusion import rrf_fuse_hits

__all__ = ["rewrite_query", "rrf_fuse_hits"]
