# Structure-Correction Layer — Implementation Spec

Hand this to Claude Code as a standalone task. Pairs with CLAUDE.md (same stack/rules:
local-only, air-gapped, config-driven, deterministic over generative for content). Build in
the order at the bottom, one slice at a time, STOP after each for review. DOCUMENT-AGNOSTIC:
the mechanism is fixed; all corpus-specific patterns/heuristics live in config the user fills
per document family. No domain terms or doc-specific patterns in code.

## Problem this fixes
Docling derives structure from LAYOUT, which is unreliable on semi-structured documents
(forms, government/admin PDFs). Observed defects:
- Tiny fragment chunks (e.g. text = "-").
- Pseudo-headers (e.g. heading_path = ["Antwort:"]) — form labels mis-detected as headings.
- Weak metadata (no real reference hierarchy like "§ 16 Abs. 3").

## Root-cause insight (drives the ordering)
The tiny chunks are CAUSED by the false headers. The chunker merges prose within a section but
NEVER merges across a heading boundary. A pseudo-header ("Antwort:") is an artificial boundary,
so the merge is blocked and fragments are trapped under it. Therefore: **header correction MUST
run BEFORE the chunker merges** — fix the boundaries first, and most tiny chunks merge away on
their own. Cleanup of leftovers runs AFTER chunking. The layer is thus two-phase.

## Architecture: deterministic-first + LLM-as-classifier-only
- **Deterministic rules carry ~90%** (regex/heuristic/statistical): fast, free, offline,
  auditable. They JUDGE structure (header vs label, empty leaf, reference hierarchy, lists).
- **LLM only on flagged ambiguous cases (~10%)**: local model, low temp, BATCHED. It outputs a
  LABEL ONLY (e.g. "heading" | "label" | "belongs_with_previous"). It MUST NOT rewrite content,
  touch numbers, or "smooth" text — classifier, never editor. Source fidelity (exact values,
  § references) is sacred.
- This layer CORRECTS structure; it does NOT invent or enrich semantics (tags/HyDE belong to the
  separate enrichment stage) and never edits chunk text.

## Pipeline position
```
Docling parse  ->  [PHASE 1: pre-chunk structure correction]  ->  HybridChunker (prose merge)
               ->  [PHASE 2: post-chunk cleanup]  ->  metadata/embed/index
```

## PHASE 1 — pre-chunk (structure & hierarchy), deterministic + flagged-LLM
1. **Pseudo-header filter (the key fix).** Demote a "heading" to normal text when it looks like a
   label, not a section title: ends with ":", very short (≤ N chars / ≤ M words, config),
   is a single stopword, appears mid-text-flow rather than above a block, or its font size is not
   larger than body text (use Docling style info if available). Demoting removes the artificial
   boundary so the chunker can merge. Ambiguous cases (short but plausibly a real heading) ->
   flag for the LLM classifier.
2. **Reference-based hierarchy.** Extract the document's OWN reference scheme via config patterns
   (e.g. `§\s*\d+`, `Abs\.?\s*\d+`, `Art\.\s*\d+`, "1.2.3" section numbers) and build the
   parent-child tree from THAT, not from layout. This yields reliable hierarchy + metadata at once
   (e.g. paragraph="§ 16", absatz="3"). Pattern set is config per corpus; the mechanism is generic.
3. **List/enumeration cohesion.** Detect list runs (markers from config: `a)`, `b)`, `1.`, `–`)
   and keep them as one cohesive unit so "c)" is never separated from "a)/b)".

## PHASE 2 — post-chunk (cleanup), deterministic + flagged-LLM
4. **Empty / low-substance leaf filter.** Drop PROSE leaves whose cleaned text is only
   punctuation/whitespace (e.g. "-", "–", "n/a") or below a min length (config). TABLES ARE
   EXEMPT — a "-" cell can mean "no value" and the table is kept whole.
5. **Orphan attachment.** Captions, footnotes, a stray sentence belonging to the previous list/
   block: attach to the correct parent by proximity/type (deterministic); flag genuinely unclear
   orphans for the LLM ("belongs_with_previous?"). Do not index context-less micro-chunks.
6. **Cross-reference extraction.** Pull references like "siehe § 17 Abs. 2" into the `references`
   metadata (best-effort, never block ingestion) for the viewer's "related sections".
7. **Language inheritance.** For very short/empty fragments where langdetect is unreliable, inherit
   `lang` from the parent/neighbor instead of guessing on meaningless text (protects per-language
   BM25 routing).
8. **Contextual header rebuild.** After headers are corrected, rebuild the prepended contextual
   header from the CORRECTED hierarchy (e.g. "§ 16 Stufenlaufzeit > Abs. 3"), improving embeddings.
9. **Per-document quality metric.** Emit counts: leaves dropped, pseudo-headers demoted, orphans
   attached, fragments merged. Log it; a bad-parse document is then visible, not silent garbage.

## LLM classifier (flagged cases only)
- Local model, low temperature, batched over the flagged items only.
- Returns a single label per item from a fixed set. NO free text, NO content edits, NO numbers.
- Prompt lives in `prompts/`, keyed `(structure_classify, <lang>)`.
- If the LLM is unavailable/offline-restricted at build time, fall back to the deterministic
  decision (default the flagged item to "text"/"keep") — never block ingestion on the LLM.

## Config (per corpus; mechanism generic)
```python
STRUCTURE = {
    "header": {
        "max_label_chars": 25, "max_label_words": 3,
        "label_suffixes": [":"], "demote_single_stopword": True,
        "require_larger_font_than_body": True,   # if style info present
    },
    "reference_patterns": [r"§\s*\d+", r"\bAbs\.?\s*\d+", r"\bArt\.\s*\d+", r"\b\d+(\.\d+)+\b"],
    "list_markers": [r"^[a-z]\)", r"^\d+\.", r"^[-–]\s"],
    "min_prose_chars": 3,                # below -> drop (prose only)
    "tables_exempt_from_empty_filter": True,
    "use_llm_classifier": True,          # flagged-only
    "xref_patterns": [r"siehe\s+§\s*\d+", r"vgl\.\s+§\s*\d+"],
}
```
All corpus knowledge is here (or in per-corpus variants); none in code. Config/prompts are
version-controlled, reviewed, not user-writable at runtime.

## Module layout
```
structure/
  __init__.py
  pre_chunk.py     # phase 1: header demotion, reference hierarchy, list cohesion
  post_chunk.py    # phase 2: empty filter, orphans, xref, lang inheritance, header rebuild, metric
  classify.py      # LLM classifier on flagged items (label-only)
  rules.py         # shared deterministic predicates driven by STRUCTURE config
prompts/
  structure_classify.<lang>.txt
```

## Build order (STOP after each)
1. `rules.py` + pseudo-header filter (phase 1 step 1) ONLY. Re-run ingestion on a real messy PDF
   and CONFIRM the tiny-chunk count drops sharply (the "Antwort:" boundary is gone, fragments
   merge). Print before/after chunk counts.
2. Empty/low-substance leaf filter (phase 2 step 4), tables exempt. Confirm the "-" chunk is gone.
3. Reference-based hierarchy (phase 1 step 2): extract §/section metadata, build parent-child from
   it, rebuild contextual header (step 8). Inspect heading_path on 50 chunks.
4. Orphan attachment + list cohesion (steps 3,5); language inheritance (step 7).
5. Cross-reference extraction (step 6) into `references`.
6. LLM classifier (classify.py) on flagged header/orphan cases only; label-only; offline fallback.
7. Per-document quality metric (step 9) + a MANDATORY inspection dump (first 50 chunks: text,
   chunk_type, heading_path, metadata) wired into ingestion validation.

## Do NOT
- Do not run header correction AFTER chunking — it must precede the merge (root cause).
- Do not let the LLM rewrite/smooth content or touch numbers — classifier (label) only, flagged only.
- Do not apply the empty-leaf filter to tables — tables are kept whole.
- Do not hardcode reference patterns / header heuristics / list markers in code — config per corpus.
- Do not add semantic enrichment (tags/HyDE) here — that's the separate enrichment stage.
- Do not index context-less micro-chunks; attach orphans or drop empties.
- Do not block ingestion on the LLM; fall back to deterministic decisions offline.
- No cloud calls; local model only.

## Acceptance criteria
- On a real messy PDF, tiny-fragment chunk count drops substantially after the pseudo-header fix.
- The "-" / whitespace-only prose chunks no longer appear in the index; table cells with "-" remain.
- heading_path reflects the document's real reference hierarchy (e.g. "§ 16 ... > Abs. 3"), not
  form labels like "Antwort:".
- `references` carries extracted cross-references where present.
- Every behavior is driven by STRUCTURE config + prompts; zero domain patterns in code; runs offline.
- Ingestion prints a per-document quality metric and a 50-chunk inspection dump for review.