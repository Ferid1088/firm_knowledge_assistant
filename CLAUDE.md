# Local RAG — Implementation Spec (CLAUDE.md)

Read this fully before any task. Source of truth; supersedes earlier versions. Build in the
order at the bottom, one slice at a time, STOP for review after each. Do not reduce scope for
"small data" — commercial target. Do not introduce tools outside the stack without asking.

## Goal & scope
Commercial-grade, air-gapped local RAG over PDFs with text + tables; answers in the user's
language with verified, clickable source citations.
- IN now: native (born-digital) PDFs, text + tables; German (HOUSE/default) + English (bidirectional).
- OUT now (designed-for, not built): scanned/handwritten/drawings, cloud. Keep interfaces ready.
- HARD REQUIREMENT: air-gapped — nothing leaves the company network (see Security).

## Fixed tool stack (do not substitute)
- Parsing: **Docling** (default TableFormer pipeline)
- Chunking: Docling document tree -> custom structural parent-child; **HybridChunker** used only
  as the token-aware splitter for PROSE leaves (see Chunking)
- Embedding: **Qwen3-Embedding** (pilot: 0.6B/4B; production: 4B/8B), Apache-2.0, multilingual
- Reranker: **Qwen3-Reranker**
- Vector store: **Qdrant**, self-hosted, local
- Lexical: BM25 sparse vectors in Qdrant, **named per language** (sparse_de, sparse_en);
  tokenization (incl. German decompounding) owned in OUR pipeline (see Embed & index)
- Query translation: **local** MT/LLM — query-time only, cached per query
- Original-document store: source PDFs on local storage, served by an internal endpoint
- Answering LLM: **local** — Ollama (pilot) / vLLM (production); model id is one config value
- Orchestration: **LangGraph** (self-hosted)
- Frontend: **Next.js + assistant-ui** (LangGraph runtime), responsive/PWA, internal; **PDF.js**
  viewer (assets bundled locally).
- Optional self-hosted only: Postgres (persistence), Langfuse (observability). NEVER cloud.

## Architecture principles
- Swappable interfaces; models + store are config values. LangGraph orchestrates; tools live in nodes.
- Pin model/store versions; record in collection metadata; re-embedding rebuilds the index.
- Local-first, enforced by Security (offline flags + egress firewall).
- Deterministic over generative for anything numeric (tables, citations, extracted facts).
- Backend is frontend-agnostic: engine = API; UI is a thin layer over artifact_chunks.

## Configuration & extensibility
ONE place controls behavior; code reads it and hardcodes NONE of: model ids, paths, thresholds,
flags, languages, or prompts. Two homes: `config.py` (values/wiring) and `prompts/` (text).

### config.py — central control
- Models + revisions + local paths (embedder, reranker, LLM, MT), each selectable by name; a new
  model = one value here (a new model *family* with a different API = one new adapter behind the
  existing interface, nothing else touched).
- Qdrant settings; thresholds (max_tokens, confidence cutoffs, max_attempts, deep-pool size);
  feature flags (enable_translated_bm25, sibling expansion).
- The LANGUAGE registry (below).
- A new *capability* (new parser/store) still needs code, but lives behind an interface so adding
  it never forces edits elsewhere. "Config-driven" = every CHOICE is config; new capabilities are
  isolated additions.

### Language registry (in config.py) + LanguageRegistry handler
- AVAILABLE_LANGUAGES: the languages whose analyzer + MT coverage exist (famous European set:
  de, en, fr, es, it, pt, nl, sv, da, no, fi, ru, el, ro, hu; verify pl/cs before offering).
  German default-ON (house base). Available is an INGESTION-time decision (sets which sparse_X
  fields exist).
- Per-language def: analyzer, decompound(bool), sparse_field (sparse_de/_en/_fr/...), prompt set.
- A `LanguageRegistry` class is the SINGLE thing the pipeline consults — no node ever writes
  "de"/"en" literally. It builds the Qdrant schema (one named sparse vector per available lang),
  drives the retrieve fan-out (others(query_lang) -> translated passes), resolves answer_lang, and
  loads prompts by (purpose, lang). Iterating the registry is how N languages work with no code change.
- Startup validation: every available language MUST have an analyzer, sparse field, prompt files,
  and MT coverage — warn loudly otherwise; never half-support silently.

### prompts/ — external, language-keyed
- ALL prompts are external templates loaded at runtime, keyed by (purpose, language): answer,
  abstain, HyDE, decompounding hints, etc. NO prompt string literals in .py.
- Keep the machine-readable STRUCTURE (JSON contract, verification rules) stable in templates with
  variables, so wording can be tuned by non-engineers without breaking the answer node's contract.
- Every prompt change passes the eval set before shipping (external = easy to change = easy to regress).

### Security of config (ties to the Security section)
- config.py and prompts/ are EXECUTABLE/behavioral configuration on an air-gapped system: keep them
  under version control + review, NOT writable by the running service, and NEVER populated from user
  input. Centralized control only helps security if the central files are themselves protected.

## Security & network isolation — HARD REQUIREMENT (nothing leaves the network)
Two senses of "token": document CONTENT (text flowing through models) and CREDENTIALS
(keys/auth). Both can leak, by different paths. Assume every tool phones home until verified
otherwise. Defense-in-depth across six layers; the egress firewall is what makes it provable.

**Layer 1 — Inference path (severity: HIGHEST — this is your document content).**
- Every model client (Docling, Qwen3 embed, reranker, MT, LLM) is LOCAL, pinned to a local
  path, offline mode forced (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1). NO cloud base_url, NO
  "fallback to API" anywhere in config.
- Query translation MUST be local (MT model or local LLM). NEVER DeepL/Google Translate — that
  ships query text (derived from documents) out. This is the most tempting leak; forbid it.

**Layer 2 — Observability & logging (also content — traces/prompts carry document text).**
- LangSmith OFF (LANGCHAIN_TRACING_V2=false). Any OTel exporter -> internal collector only.
- Langfuse self-hosted only (never its cloud). Crash reporting (Sentry etc.) OFF or self-hosted.
- App logs stay internal; never ship logs to an external aggregator. Scrub prompts from logs.

**Layer 3 — Default-ON tool telemetry (metadata; each is a separate switch to find + flip).**
- Disable explicitly and VERIFY per version: Qdrant telemetry, Hugging Face telemetry,
  Next.js (NEXT_TELEMETRY_DISABLED=1), Gradio analytics, Chroma/PostHog.
  Do not assume any are off by default.

**Layer 4 — Browser / client (leaks from the device, bypassing the server firewall).**
- Bundle ALL assets locally — no public CDNs, NO external web fonts (Google Fonts), no GA /
  Vercel Analytics / Sentry. Enforce a strict same-origin **Content-Security-Policy** (the
  browser-side egress firewall).
- NEVER put a secret behind NEXT_PUBLIC_ — that prefix ships it into the browser bundle.

**Layer 5 — Network & OS (what makes "nothing leaves" PROVABLE).**
- Default-deny egress firewall / air-gapped subnet. Internal DNS and internal NTP (DNS and NTP
  are real exfiltration channels). Disable OS/app update + license checks.
- This firewall is the single thing an auditor can verify; Layers 1–4 ensure it isn't a single
  point of failure.

**Layer 6 — Credentials & build-time supply chain.**
- Secrets in a manager, never in client-visible env, URLs, git, or logs. DB/Postgres/LangGraph
  creds rotated and internal.
- Builds run INSIDE the network against the internal PyPI/npm mirror, with egress BLOCKED during
  build too (npm/pip postinstall scripts can phone home at install time).

**Verification (do not skip).** CI runs the full ingest+query+answer+viewer path AND a build
with egress BLOCKED -> assert zero outbound connections. Any breakage with the internet cut is a
leak to fix, never a reason to open the firewall. Run the same check before every release.

**Client distribution:** internal responsive web/PWA to managed devices; no app-store native
client for now (puts the client on personal devices + adds third-party distribution/push).

---

## INGESTION pipeline (offline, linear)

### 1. Parse — Docling, default TableFormer, do_ocr=False
TableFormer: structure from model, cell text from PDF layer -> numbers never hallucinated.
NOT the VLM pipeline. Parse once into a DoclingDocument; chunk the object, never a flattened string.
- **Scanned-PDF guard:** since do_ocr=False, check each page has an extractable text layer.
  If a page/doc is empty or near-empty, FLAG and quarantine it (do NOT index empty chunks);
  surface for the future OCR path. Never silently ingest blank text.
- Also capture page sizes (for bbox normalization) and store the source PDF in the originals store.

### 2. Chunk — structural parent-child (clear division of labor)
- From the Docling tree, classify each unit -> StructuralUnit: heading | table | recommendation | prose.
  - heading -> **parent** node (is_leaf=False); carries children's heading path.
  - table -> **atomic leaf** (chunk_type=table), kept WHOLE.
  - recommendation/clause -> **atomic leaf** (chunk_type=recommendation). NOTE: Docling has no
    "recommendation" type — this is CUSTOM domain classification (heuristic/regex/local-LLM);
    define it explicitly per the document family. If undefined, treat as prose.
  - prose -> leaves produced by **HybridChunker** (token-aware), windowed ONLY within a section.
- **HybridChunker's role is limited to prose**: tokenizer = Qwen3; max_tokens ~= 512 (tune on
  eval); merge_peers=True. It does NOT touch atomic leaves.
- **Token-size policy (resolves the whole/512 conflict):** max_tokens governs PROSE windowing
  only. Atomic leaves (table/recommendation) are kept whole even if > 512. For EMBEDDING an
  oversize atomic leaf: if it exceeds the embedding model's effective window, embed a generated
  CONTEXTUAL DESCRIPTION of it (the parent-child "embed a description, return the full unit"
  pattern) — the full unit is still stored and returned; only the embedded text differs. Whole
  units under the window embed normally.

### 3. Metadata / chunk payload (Qdrant structured payload)
- vectors: dense (Qwen3) + ONE named sparse vector for the chunk's language (sparse_de OR sparse_en;
  mixed-language chunk -> dominant language, and also populate the other if clearly bilingual)
- geometry: boxes=[{page,rect:[x0,y0,x1,y1]}] from Docling prov, top-left origin, normalized 0..1
- pages; address (doc_id, chapter, §, subsection, point, section_title)
- system: lang, parent_id, is_current, version_id, chunk_id, chunk_type, chunk_index_in_parent
- references (OPTIONAL, best-effort): clause->clause cross-refs extracted by regex on reference
  patterns (e.g. "siehe §..."); never block ingestion on these.
- Versioning: version_id is REQUIRED on every chunk. On re-ingest of a doc the new version
  supersedes the old — set the prior points' is_current=False; NEVER keep two active versions
  silently. Retrieval filters is_current=True by default; superseded versions remain queryable
  only via an explicit version_id.
- optional alternate-representation fields under the SAME id (contextual header; oversize-leaf
  description; later a translated field) — NEVER replace the original, NEVER on the citation path.

### 4. Embed & index
- Qwen3-Embedding on the contextualized text (same text at index and query time); query-side
  instruction prefix on QUERIES only.
- **Lexical: own the tokenization.** Do NOT assume Qdrant's built-in analyzer does German
  compound-splitting — verify for the version; if absent (likely), run OUR German pipeline
  (lowercase, stopwords, stemming, **decompounding**) and English pipeline in ingestion code,
  build BM25 sparse vectors there, and store them as the named sparse vectors (sparse_de/sparse_en).
  This guarantees decompounding regardless of Qdrant's analyzer.
- One Qdrant collection holds dense + one named sparse vector PER AVAILABLE LANGUAGE (sparse_de,
  sparse_en, ...) created by iterating the LanguageRegistry + payload. Each chunk populates ONLY
  its detected language's sparse field (mixed -> dominant, + the other if clearly bilingual).

### 5. Enrich — tiered, LOCAL only (heavy; DEFER on the 16 GB pilot)
- Always (cheap): contextual header prepended before embedding.
- Selectively, high-value chunk types only (tables, recommendations): description for oversize
  leaves (see step 2), HyDE, constrained semantic tags (controlled vocabulary). Tags are SOFT
  hints, never authoritative. All on the local LLM. On the Mac pilot, run only the contextual
  header; defer HyDE/tags to the GPU server.

---

## QUERY pipeline — LangGraph stateful graph

### State
- query, query_lang, translated_queries (per active language; cached, computed ONCE)
- answer_lang — rule: explicit in-query instruction WINS (needs a small instruction-parse, not
  just langdetect) > detected query_lang > German default
- active_languages — German (always) + the languages the user ticked in the UI dropdown
- sub_questions, sub_results — present only for multi-part queries (see Complex-query handling)
- candidate_pool, reranked, confidence (top-1 + gap-to-tail), attempts
- answer, claims (each: text, source, quote, verified[bool])
- artifact_chunks (UI-only: boxes, address, source, chunk_id, text) — STATE field, invisible to model

### Nodes
- prepare_query — language detect; set answer_lang; read active_languages (German + UI ticks);
  translate the query ONCE into each active language -> translated_queries (cached);
  detect multi-part queries and decompose into sub_questions (see Complex-query handling)
- retrieve — bidirectional hybrid fan-out -> deep candidate_pool
- rerank — Qwen3-Reranker -> top-k
- score_confidence
- escalate — widen pool (k up) / rewrite or decompose query / broaden over-strict filters
  (NOT translate — that is already baseline)
- answer — assemble parent-child context (see below); local LLM in answer_lang, JSON contract, quote-verification
- abstain — "I can't ground this in the documents" (answer_lang)

### Edges (controller)
- START -> prepare_query -> retrieve -> rerank -> score_confidence
- score_confidence -> ROUTER: OK -> answer -> END | low & attempts<max -> escalate -> retrieve (LOOP)
  | attempts exhausted -> abstain -> END
- Hard max_attempts; log every hop; track abstain rate; LangGraph checkpointing for memory/replay.
- retrieve uses the CACHED translated_query (no re-translation on loops).

### Complex-query handling (stays inside the bounded graph)
Four kinds of "hard" query, handled differently — do NOT collapse them into one agentic loop:
- **Scattered** (answer spans many chunks): ALREADY handled by the deep pool + rerank +
  parent-child expansion. No new machinery.
- **Vague / underspecified** ("is this safe?"): low confidence -> escalate -> abstain is the
  CORRECT terminal. Abstaining and asking to specify beats a confident ungrounded answer.
- **Multi-part** ("compare A and B on X, and which fits C"): a single embedding retrieves a muddy
  average. DECOMPOSE: in prepare_query, detect multi-part (cheap classifier or the LLM) and split
  into sub_questions; run the EXISTING retrieve->rerank once per sub-question -> sub_results; the
  answer node synthesizes across them with verified citations per part. Decomposition is also
  reachable REACTIVELY via escalate when a single-shot retrieval comes back weak — but prefer
  proactive (don't waste a loop failing first).
- **Multi-hop** (part 2 depends on part 1's finding): DEFERRED. Needs an iterative variant
  (retrieve hop 1 -> extract bridge entity -> query hop 2). Build ONLY if the eval set shows real
  multi-hop questions failing; do not build a general agentic planner on spec.
Bound everything with max_attempts; decomposition is a FIXED fan-out of sub-questions, not
open-ended planning — the graph stays bounded, terminating, and inspectable.

### retrieve — registry-driven N-language hybrid fan-out
- **dense over ALL docs** (cross-lingual backbone — already finds any-language content; the
  dropdown does NOT gate this).
- **One BM25 pass per active language** (driven by LanguageRegistry, not hardcoded de/en):
  - Each pass uses the query EXPRESSED IN THAT LANGUAGE: original for the query's own language,
    else translated_queries[L]. It searches that language's chunks only — structurally, by
    querying the `sparse_L` field (which only the lang=L chunks populate); `lang` metadata is the
    belt-and-suspenders filter.
  - German pass always runs. English/French/... run only if in active_languages (the user's ticks).
- Translate ONLY the natural-language part; exact codes/part numbers are NEVER translated (they
  match across languages verbatim). A pure-code query skips translation; BM25 still runs per language.
- **No re-index to toggle a language:** lang metadata + sparse_L were written at ingestion, so a
  toggle just adds/removes a query-time pass. Caveat: a language must have been AVAILABLE at
  ingestion for its sparse_L to exist; selectable-at-query ⊆ available-at-ingestion. Dense still
  covers any language regardless.
- `enable_translated_bm25` flag still gates the translated passes globally (default ON).
- Fuse all passes with RRF; retrieve a DEEP pool (~50–100) for the reranker.
- UI: a corner dropdown ("power up search — add languages") lists AVAILABLE_LANGUAGES from the
  registry (German shown always-on); ticks set active_languages. Frame copy as sharper *keyword*
  search per language — dense is always cross-lingual, so this adds lexical precision, not access.

### Parent-child context expansion (post-rerank, before answer)
Rerank on the precise CHILD leaves (good precision), then expand the winners for the answer's
context (good completeness) — the small-to-big pattern:
- For each top child, prepend its **parent heading / section context** (via parent_id).
- **Siblings (±1) are OFF by default** — enable only for continuous prose where eval shows a lift,
  and never for tables; cap the added context by token budget to avoid diluting the prompt.
- Expansion feeds the ANSWER node's context ONLY. Citations and boxes still resolve to the precise
  CHILD that was retrieved + verified — never highlight the whole parent.

### answer — verified citation (robust)
- JSON contract {answer, claims:[{text, source, quote}]}; generate in answer_lang.
- Verify each quote against its cited chunk's text after NORMALIZING (whitespace, case; for
  numbers, check the value is present). Instruct the model to quote VERBATIM.
- On failure: mark claim verified=False and surface it as "unverified" — do NOT silently delete
  the answer; only ungrounded *citations* are withheld from the highlight, not the prose.
- Verification ALWAYS runs against the source chunk's ORIGINAL language (decoupled from answer_lang).
- Populate artifact_chunks here (chunk_id + text + boxes all present), only for verified claims.

### Source viewer — PDF.js (local assets)
- UI reads artifact_chunks; fetches the source PDF from the internal originals endpoint by doc_id;
  jumps to page; draws overlay rectangles = normalized boxes × render scale. Surface references.
- Keep the data contract (normalized fractions + artifact_chunks) framework-agnostic.

---

## Eval set (highest-priority deliverable — a real build step, see order)
German/English retrieval test set WITH cross-lingual cases (DE question <-> EN source),
exact-code queries, AND complex queries (one each: multi-part, vague, scattered, multi-hop) to
measure where the graph fails and decide what to build. Provides recall@k and the score
distributions that set score_confidence thresholds and validate enable_translated_bm25. Every
model/threshold/upgrade decision is measured against it, not guessed.

## Do NOT
- No outbound connection in the serving path; enforce default-deny egress (flags alone insufficient).
- No public-CDN assets; no LangSmith / Assistant Cloud / cloud APIs.
- No VLM pipeline for numeric tables; no silent ingest of empty (scanned) text.
- No generic splitter on flattened Markdown; no plain whitespace BM25 (German needs decompounding).
- No index-time chunk translation replacing originals; translate query-time, once, cached.
- No "always to German" translation; translate toward the OTHER index. Never translate exact codes.
- Don't couple answer language to verification language. Don't silently delete answers on a failed
  quote-check (flag instead). Don't put artifact_chunks into the model prompt.
- Don't hardcode model ids, languages, thresholds, flags, or prompts in code — read them from
  config.py / the LanguageRegistry / prompts/. Don't let config.py or prompts/ be user-writable.

## Hardware
- Pilot: M1 Pro / 16 GB — small models: Qwen3-Embedding 0.6B/4B, small answering LLM via Ollama,
  enrichment limited to the contextual header. A 119B model will NOT fit.
- Production: GPU server, on-prem — Qwen3-Embedding 8B + reranker via vLLM; answering LLM
  (Mistral Small 4 or Qwen3) chosen by eval. Same code, config swap.

## Build order (tracer-bullet — STOP after each)
0. Eval set scaffold: a small DE/EN Q->expected-chunk set incl. cross-lingual + exact-code cases,
   and a recall@k harness. (Prerequisite for thresholds and every later decision.)
1. Qdrant + originals store + Retriever interface. Parse (with scanned guard) -> structural
   parent-child chunk -> metadata (normalized boxes, lang, parent_id, address) -> embed ->
   index dense + named per-language BM25 sparse (own decompounding). Print chunks on a sample PDF.
2. Minimal LangGraph (linear): prepare_query (detect+answer_lang+cached translate) -> retrieve
   (bidirectional fan-out, RRF) -> rerank (Qwen3, deep pool) -> answer. On a German query (with
   one exact code + one paraphrase) show BOTH DE and EN chunks retrieved and both channels firing.
3. answer node: local LLM in answer_lang, JSON contract, robust quote-verification; populate
   artifact_chunks.
4. Frontend: Next.js + assistant-ui (LangGraph runtime) + local PDF.js viewer fetching the source
   PDF from the originals endpoint; click source -> page jump -> overlay from normalized fractions.
5. Turn the controller ON: score_confidence (thresholds from step 0) + ROUTER edges + escalate +
   loop-back + abstain; max_attempts, logging, checkpointing.
6. Tiered local enrichment (contextual header always; descriptions for oversize leaves; HyDE +
   tags on high-value chunks — on the GPU server, not the pilot).
7. Air-gap hardening: offline flags, telemetry off, no-CDN bundling, CI egress-blocked check.

#Ask before installing anything or running Docker. Manage your own venv + requirements.txt.