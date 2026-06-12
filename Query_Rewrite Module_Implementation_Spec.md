# Query-Rewrite Module — Implementation Spec

Hand this to Claude Code as a standalone task. It pairs with CLAUDE.md (same stack, same
rules: local-only, air-gapped, config-driven, prompts external). Build in the order at the
bottom, one slice at a time, STOP after each for review. This module is DOCUMENT-AGNOSTIC:
the mechanism is fixed; all corpus-specific knowledge lives in external data files the user
fills per document family. Do not bake any domain terms into code.

## Purpose
Close the vocabulary gap between how users ask (colloquial, short) and how documents are
written (formal, domain terminology, reference schemes). The rewrite expands/translates the
query into the corpus register BEFORE retrieval, lifting lexical (BM25) recall. Dense already
carries semantics; rewrite sharpens exact-term matching.

## Where it fits
- It is a REACTIVE escalation step inside the existing LangGraph `escalate` node — runs only
  when the first retrieval came back weak (low confidence), NOT on every query.
- It AUGMENTS, never replaces: always also search with the original query and fuse via RRF.
- It runs on the LOCAL LLM, low temperature. No cloud. Prompt lives in `prompts/`.

## Architecture (fixed mechanism)
Three rewrite operations, mapped to escalation rungs:

1. **Terminology expansion** (primary; first rewrite rung)
   - Enrich the query with the corpus's domain terms. ADD, do not replace; keep original terms.
2. **HyDE — hypothetical document** (strong second probe)
   - Local LLM generates a hypothetical answer passage IN THE CORPUS STYLE; embed THAT instead
     of the question for the dense channel.
   - INVARIANT: the HyDE text is a SEARCH PROBE, never shown, never an answer. Hallucinated
     details in it are irrelevant — it only helps find the real chunk, which is then verified.
3. **Multi-query** (later rung)
   - 3–4 paraphrases, one search each, RRF-fused. N× cost → only late in the ladder.

## Protected-token safety (MANDATORY — the #1 failure mode)
LLMs "fix" exactly the tokens that must stay exact: references (§/Art./section/clause),
identifiers (codes, norm numbers, part numbers, file numbers), proper names, numbers. This
destroys the exact match. Four guards, all required:

1. **Skip rewrite** when the query is primarily identifiers/codes (regex pre-check).
2. **Prompt instruction**: copy references, identifiers, proper names, numbers VERBATIM.
3. **Regex post-check (auditable)**: every protected pattern present in the ORIGINAL query
   must also be present, unchanged, in the rewrite. If any is missing/altered → DISCARD the
   rewrite, fall back to the original query. The pattern list is CONFIG per corpus
   (e.g. `§\s*\d+`, `DIN\s*\d+`, `[A-Z]{2,}-\d+`); the mechanism is generic.
4. **Augment, never replace**: original query is always searched too; RRF-fuse. A bad rewrite
   must never lose a hit the original would have found.

## Hybrid: dictionary + LLM (both external data, per corpus)
- **Synonym/terminology dictionary** (deterministic, versioned, no LLM call): a map
  "colloquial → domain term(s)" per corpus. Apply it first; cheap, auditable, offline.
- **LLM rewrite** handles only what the dictionary doesn't cover.
- Both are DATA, not code — swappable per corpus. Code loads and applies them generically.

## Module layout
```
rewrite/
  __init__.py
  rewriter.py          # generic: orchestrates skip-check, dictionary, LLM, post-check
  protected.py         # regex skip-check + post-check, patterns from config
  fusion.py            # RRF over {original, rewritten, hyde} result lists (reuse existing RRF if present)
config/
  rewrite_dictionary.<corpus>.yaml   # user-filled per corpus (template below)
  rewrite_fewshots.<corpus>.yaml     # user-filled per corpus (template below)
prompts/
  rewrite.<lang>.txt   # generic prompt template (below), holds {domain_hint} {few_shots} {query}
```

## config.py additions
```python
REWRITE = {
    "enabled": True,
    "trigger": "reactive",          # only on low-confidence escalation
    "use_dictionary": True,
    "use_llm": True,
    "use_hyde": False,              # enable per eval
    "use_multiquery": False,        # later rung, per eval
    "temperature": 0.1,
    "protected_patterns": [         # per corpus; generic engine
        r"§\s*\d+", r"\bAbs\.?\s*\d+", r"\b[A-Z]{1,3}-?\d+\b", r"\b\d+([.,]\d+)?\b",
    ],
    "dictionary_path": "config/rewrite_dictionary.default.yaml",
    "fewshots_path": "config/rewrite_fewshots.default.yaml",
    "domain_hint": "",              # optional one line per corpus
}
```
Everything here is config; no domain terms in code. Files are version-controlled, reviewed,
not user-writable at runtime (same rule as the rest of config/prompts).

## prompts/rewrite.<lang>.txt (generic template)
```
Rolle: Du formulierst eine Suchanfrage für ein Fachdokument-Korpus um.
Ziel: Umgangssprachliche/kurze Begriffe um die im Korpus übliche Fachterminologie ergänzen,
damit die Schlagwortsuche die einschlägige Stelle findet.

Regeln:
- Referenzen, Identifikatoren/Codes, Eigennamen und Zahlen UNVERÄNDERT übernehmen.
- Die Frage NICHT beantworten.
- Nur die erweiterte Suchanfrage ausgeben, ohne Vorrede.

{domain_hint}

Beispiele:
{few_shots}

Anfrage: {query}
```
(English instruction variants are fine too; keep one file per language, keyed via the
LanguageRegistry. Only {domain_hint} and {few_shots} carry corpus knowledge.)

## Data templates (scaffold these; user fills later)
`config/rewrite_dictionary.default.yaml`:
```yaml
# colloquial term: [domain term(s) to ADD]
# example (user replaces per corpus):
# "urlaub": ["Erholungsurlaub", "Urlaubsanspruch"]
{}
```
`config/rewrite_fewshots.default.yaml`:
```yaml
# 2-3 examples per corpus, colloquial -> expanded search query
# - in: "..."
#   out: "..."
[]
```

## Integration with retrieve (RRF)
- On the rewrite rung: produce up to three query forms — original (always), dictionary+LLM
  expanded, and (if enabled) HyDE probe for the dense channel.
- Run the existing hybrid retrieval for each form; **RRF-fuse all result lists** into the deep
  pool, then hand to the existing reranker. Reuse the existing RRF if the codebase has one.
- HyDE affects only the DENSE query embedding; lexical passes use the textual rewrite.

## Eval (per corpus)
Add a few colloquial↔formal pairs to the eval set (question in user words, expected chunk in
doc words). Measure recall@k with rewrite ON vs OFF. Decide per corpus whether each variant
(expansion / HyDE / multi-query) earns its cost. Do not enable HyDE/multi-query without a
measured lift.

## Build order (STOP after each)
1. `protected.py`: skip-check + post-check driven by `protected_patterns`. Unit-test with
   §/code/number queries: confirm a query that is just a code is skipped, and a rewrite that
   drops/alters a protected token is rejected.
2. Dictionary path: load `rewrite_dictionary.*.yaml`, apply additively to the query. Test with
   a filled sample dict.
3. LLM rewrite: load `prompts/rewrite.<lang>.txt` with {domain_hint}+{few_shots}, low temp,
   local model; run only what the dictionary didn't cover; pass output through post-check.
4. Wire into the `escalate` node as the reactive rewrite rung; produce original+rewritten
   query forms; RRF-fuse through existing retrieve→rerank.
5. (Optional, per eval) HyDE probe for the dense channel; then multi-query as a later rung.
6. Add eval pairs; measure recall@k ON vs OFF; record results.

## Do NOT
- Do not bake domain terms/synonyms into code — they live in the per-corpus YAML.
- Do not translate/alter protected tokens; reject such rewrites via the post-check.
- Do not replace the original query — always also search it and RRF-fuse.
- Do not show HyDE text or treat it as an answer — probe only.
- Do not run the rewrite on every query — reactive (low-confidence) only.
- Do not call any cloud API; local LLM only. Keep config/prompts non-user-writable.

## Acceptance criteria
- A code-only query skips rewrite entirely.
- A rewrite that alters/drops a §/code/number is discarded automatically (post-check).
- With a filled dictionary + few-shots, a colloquial query retrieves the formal chunk it
  previously missed, and the original query's hits are never lost (RRF).
- All rewrite behavior is controlled from config.py + YAML + prompts/, with zero domain terms
  in code, and runs fully offline.
