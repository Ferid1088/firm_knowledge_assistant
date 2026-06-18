# Firm Knowledge Assistant

> Air-gapped, local-only Retrieval-Augmented Generation for enterprise documents.
> Answers in the user's language with verified, clickable source citations.
> Nothing leaves the company network.

---

## What it does

A **private document intelligence workspace**. Upload internal documents (PDFs, Word, Excel, PowerPoint, emails, drawings, and more), ask questions in German or English, and receive precise answers with highlighted citations linking back to the exact page and passage in the original file.

| Problem | How this agent solves it |
|---|---|
| Sensitive documents cannot leave the network | 100 % local inference — Ollama LLM, Qwen3 embedding, self-hosted Qdrant |
| Answers must be verifiable | Every claim is quote-verified against the source chunk before the answer is returned |
| Tables and structured data are lost in plain-text pipelines | Docling TableFormer extracts table structure from the PDF layer; numbers are never hallucinated |
| Users write in different languages | Bidirectional DE ↔ EN retrieval; answer language follows the question |
| Multiple staff need shared access | Multi-user IAM with departments, roles, conversation isolation, and sharing |

### Target users

Internal enterprise users on managed devices — technical staff, legal/compliance, HR/management, and administrators.

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | ≥ 0.7 | Python package & venv management |
| Python | 3.11+ | Backend runtime |
| Node.js | 20+ | Frontend (Next.js) |
| [Ollama](https://ollama.com/) | latest | Local LLM inference (`qwen3:8b`) |

---

## Quick start

```bash
# 1. Clone and enter the project
git clone https://github.com/Ferid1088/firm_knowledge_assistant.git
cd firm_knowledge_assistant

# 2. Create a virtual environment
uv venv .venv

# 3. Install all dependencies (Python + Node)
make install

# 4. Pull the answering model
ollama pull qwen3:8b

# 5. (Optional) Set up Langfuse observability
cp .env.langfuse.example .env.langfuse   # edit with your self-hosted keys

# 6. Start both backend and frontend
make dev
```

Open **http://localhost:3000** in your browser.
The backend API docs are at **http://localhost:8000/docs**.

On first launch, navigate to the setup wizard to create the initial superadmin account.

---

## Developer commands

| Command | What it does |
|---|---|
| `make dev` | Start backend + frontend together; stream combined logs; **Ctrl-C** stops both |
| `make stop` | Kill both services |
| `make status` | Show running / stopped + PID for each service |
| `make logs` | Tail combined log files (`.logs/backend.log` + `.logs/frontend.log`) |
| `make backend` | Start the FastAPI backend only (port 8000, `--reload`) |
| `make frontend` | Start the Next.js frontend only (port 3000) |
| `make install` | `uv pip install -r requirements.txt` + `npm install` in `frontend/` |
| `make test` | Run the full pytest test suite (`tests/`) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (PWA)                            │
│   Next.js + assistant-ui  │  PDF.js viewer  │  Admin panel       │
└─────────────┬──────────────────────────┬─────────────────────────┘
              │  REST / cookie auth      │
┌─────────────▼──────────────────────────▼─────────────────────────┐
│                     FastAPI Backend  :8000                        │
│  /api/conversations  /api/ingest  /api/originals  /api/admin     │
└─────────────┬────────────────────────────────────────────────────┘
              │
     ┌────────▼────────┐
     │   LangGraph     │   stateful orchestration
     │   RAG Graph     │
     └────────┬────────┘
              │
  ┌───────────┼───────────────┐
  │           │               │
┌─▼─────┐ ┌──▼───────┐ ┌─────▼───────┐
│Qdrant │ │ Qwen3    │ │Ollama/vLLM  │
│(local)│ │Embed +   │ │(local LLM)  │
│vector │ │Reranker  │ │             │
│store  │ └──────────┘ └─────────────┘
└───┬───┘
    │
┌───▼────────────────┐
│ SQLite (app.db)    │  users, conversations, messages
│ AES-256-GCM msgs   │  encrypted + Ed25519 signed
└────────────────────┘
```

---

## Ingestion pipeline — adaptive 11-step workflow

Every uploaded document flows through an **adaptive pipeline** that selects the right parser, chunker, and embedding strategy based on the detected document type. The pipeline is defined in `backend/tools/pipeline.py`.

```
                              ┌─────────────────────────┐
                              │      File Upload         │
                              │  (UI or POST /api/ingest)│
                              └────────────┬─────────────┘
                                           │
                              ┌────────────▼─────────────┐
                              │  0. READ                  │
                              │  ToolRegistry dispatches  │
                              │  a FileReaderTool by ext  │
                              │  (.pdf → PDFReader,       │
                              │   .docx → DOCXReader …)   │
                              │  Validates file integrity  │
                              └────────────┬─────────────┘
                                           │
                              ┌────────────▼─────────────┐
                              │  1. SCAN CHECK            │
                              │  Detect scanned/empty     │
                              │  pages (no text layer)    │
                              │  → quarantine if scanned  │
                              └────────────┬─────────────┘
                                           │
                              ┌────────────▼─────────────┐
                              │  2. TYPE RESOLUTION       │
                              │                           │
                              │  User-selected doc type?  │
                              │    YES → use directly     │
                              │    NO  → LLM classifier   │
                              │          samples 3 pages  │
                              │          (first/mid/last) │
                              │          → one of 10 types│
                              └────────────┬─────────────┘
                                           │
                          ┌────────────────▼────────────────┐
                          │                                  │
                          │   TypeRegistry.get_handler()     │
                          │   Maps doc_type → (parser,       │
                          │   chunker, embed_strategy)       │
                          │                                  │
                          └────────┬─────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │          ADAPTIVE DISPATCH               │
              │  Each doc_type gets a different          │
              │  parser + chunker + embed strategy       │
              ▼                                          ▼
┌─────────────────────────┐            ┌─────────────────────────┐
│  3. PARSE               │            │  4. CHUNK               │
│  Parser selected by type│            │  Chunker selected by    │
│                         │            │  type (see table below) │
│  • Docling (most types) │            │                         │
│  • EML parser (emails)  │            │  Structural parent-child│
│  • OCR parser (scanned) │            │  tree; atomic leaves    │
│    (stub on pilot)      │            │  for tables & clauses   │
└─────────────┬───────────┘            └─────────────┬───────────┘
              │                                      │
              └──────────────┬───────────────────────┘
                             │
                ┌────────────▼─────────────┐
                │  5. PAGE SIZES           │
                │  Extract bbox dimensions │
                │  for citation overlays   │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │  6. LANGUAGE DETECTION   │
                │  Per-chunk langdetect    │
                │  → assigns lang metadata │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │  7. BM25 SPARSE VECTORS  │
                │  Per-language BM25 index │
                │  (German decompounding)  │
                │  → sparse_de, sparse_en  │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │  8. EMBED                │
                │  Strategy from type:     │
                │  • text_dense (standard) │
                │  • description_dense     │
                │    (oversize tables)     │
                │  Qwen3-Embedding         │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │  9. QUALITY GATE         │
                │  Drop chunks < 10 chars  │
                │  or empty context_text   │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │  10. STORE → Qdrant      │
                │  Dense + named sparse    │
                │  vectors per language    │
                │  Versioning: is_current  │
                │  Re-ingest supersedes    │
                └──────────────────────────┘
```

### Step 2 — LLM-based type detection (`type_detector.py`)

When the user does not select a document type, the pipeline samples up to 3 pages (first, middle, last) and sends them to the local Ollama LLM for classification. The classifier returns one of 10 types with a confidence score. Below 80% confidence, the type falls back to `prose_text`.

| Type key | Description | Example |
|---|---|---|
| `prose_text` | General flowing text | Reports, articles, memos |
| `table_structured` | Primarily tabular data | Spreadsheets, data exports |
| `norm_standard` | Technical standard / norm | DIN, ISO, EN, VDE |
| `technical_manual` | Operating instructions | Equipment manuals, datasheets |
| `legal_contract` | Contracts, T&C, legal | Agreements, clauses, SLAs |
| `report_study` | Reports, analyses | Audit reports, studies |
| `form_template` | Forms, fillable templates | Application forms |
| `invoice_bill` | Invoices, delivery notes | Bills, purchase orders |
| `presentation` | Slide decks | Conference talks, pitches |
| `correspondence` | Emails, letters, memos | .eml, .msg, printed emails |

### Steps 3–4 — Adaptive parser × chunker dispatch (`type_registry.py`)

The `TypeRegistry` maps each detected type to a specific **(parser, chunker, embed strategy)** triple. Adding a new document type = one entry here + one parser/chunker module.

| Detected type | Parser | Chunker | Embed strategy | Table schemas |
|---|---|---|---|---|
| `prose_text` | Docling | HybridChunker | text_dense | — |
| `table_structured` | Docling | TableAtomic | description_dense | — |
| `technical_plan` | Docling | PlanChunker | text_dense | requirements, schedule, resources |
| `legal_contract` | Docling | ClauseAtomic | text_dense | parties, pricing, schedule, obligations |
| `authority_document` | Docling | DocumentStructureChunker | text_dense | obligations, penalties |
| `project_management` | Docling | ProjectChunker | text_dense | milestones, budget, risks |
| `knowledge_base` | Docling | HybridChunker | text_dense | — |
| `hr_personnel` | Docling | HybridChunker | text_dense | — |
| `email_thread` | Docling / Native EML | ThreadChunker | text_dense | — |
| `scanned_image` | OCR (stub on pilot) | ImageChunker | text_dense | — |

**Parsers:**
- **Docling** — primary parser for most types. Uses the TableFormer pipeline (`do_ocr=False`) to extract table structure from the PDF layer without hallucinating numbers.
- **EML parser** — native email extraction (headers, MIME parts, inline attachments) for `.eml`/`.msg` files.
- **OCR parser** — stub for future scanned-PDF support. Currently raises if called; scanned pages are quarantined, never silently ingested.

**Chunkers (8 domain strategies):**

| Chunker | Chunk types produced | Strategy |
|---|---|---|
| `HybridChunker` | `prose` | Token-aware windowing (max 512 tokens) within section boundaries. Default for generic text. |
| `TableAtomic` | `table` (atomic) | Each table kept whole — never split even if > 512 tokens. Prose sections windowed separately. |
| `DocumentStructureChunker` | `heading` (parent) + `prose` leaves | Heading nodes become parents; child prose leaves via HybridChunker. Tables kept atomic. |
| `ClauseAtomic` | `recommendation` / clause (atomic) | Article/clause/numbered paragraph → atomic leaf. Nested prose windowed. |
| `PlanChunker` | `plan_item`, `milestone` (atomic) | Phase → Work Package → Task/Milestone hierarchy with temporal metadata. |
| `ProjectChunker` | `project_item`, `milestone` (atomic) | Project items and milestones as atomic leaves with temporal metadata. |
| `ThreadChunker` | message chunks | One chunk per email message; thread header as parent context. |
| `ImageChunker` | metadata + alt-text | Metadata extraction only (no OCR on pilot); scanned guard fires. |

**Table schemas** provide per-type keyword lists (DE + EN) for classifying table roles. For example, a `legal_contract` table with headers containing "Preis" or "amount" is tagged `table_role=pricing`. This metadata feeds downstream filtering and retrieval.

**Embed strategies:**
- `text_dense` — standard Qwen3-Embedding on the chunk's context text (used by most types).
- `description_dense` — for oversize atomic leaves (tables): embed a generated contextual description; the full original text is still stored and returned for citations. (Description generation deferred on pilot; raw text used.)

### Supported file formats (15 readers)

The `ToolRegistry` auto-discovers readers from `backend/tools/readers/`. Enable/disable individual readers in `config/tools.yaml`.

| Format | Extension | Reader | Dependency |
|---|---|---|---|
| PDF | `.pdf` | `readers/pdf.py` | Docling (TableFormer) |
| Word | `.docx` | `readers/docx.py` | python-docx |
| Excel | `.xlsx` | `readers/xlsx.py` | openpyxl |
| PowerPoint | `.pptx` | `readers/pptx.py` | python-pptx |
| CSV | `.csv` | `readers/csv.py` | stdlib |
| Plain text | `.txt` | `readers/txt.py` | stdlib |
| Email | `.eml` | `readers/eml.py` | stdlib |
| Mailbox | `.mbox` | `readers/mbox.py` | stdlib |
| Outlook | `.msg` | `readers/msg.py` | extract-msg |
| OpenDocument text | `.odt` | `readers/odt.py` | stdlib xml |
| OpenDocument sheet | `.ods` | `readers/ods.py` | stdlib xml |
| SVG | `.svg` | `readers/svg.py` | stdlib xml |
| DXF drawing | `.dxf` | `readers/dxf.py` | ezdxf |
| DWG drawing | `.dwg` | `readers/dwg.py` | *(stub — no parser yet)* |
| Image | `.png/.jpg/…` | `readers/image.py` | Pillow |

### Scanned-PDF guard

Pages without an extractable text layer are detected in step 1. If a PDF is fully scanned, it is **quarantined** (not indexed). Partially scanned PDFs proceed with empty pages excluded. This prevents blank chunks from polluting the vector store.

---

## Query pipeline (LangGraph)

Every question flows through a bounded stateful graph with a hard loop cap.

```
User question
      │
      ▼
 prepare_query    → detect language, set answer_lang, translate once per active language
      │
      ▼
    retrieve      → dense (cross-lingual) + BM25 per active language → RRF → deep pool
      │
      ▼
    rerank        → Qwen3-Reranker → top-k
      │
      ▼
 score_confidence → threshold check
      │
  ┌───┴──────────────┐
  ▼                  ▼                  ▼
answer          escalate            abstain
(local LLM,     (widen pool /        (no grounded
 JSON contract,  rewrite query,       answer found)
 quote-verify)   loop back)
```

### Retrieval parameters

| Parameter | Default | Config key |
|---|---|---|
| Deep pool size | 50 | `RETRIEVE_DEEP_POOL` |
| Reranker candidates | 8 | `RERANKER_TOP_K` |
| Final top-k | 5 | `RETRIEVE_K` |
| Confidence threshold | 0.55 | `CONFIDENCE_THRESHOLD` |
| Max escalation attempts | 3 | `MAX_ATTEMPTS` |

### Language handling

- Dense retrieval is always cross-lingual (covers all indexed languages).
- BM25 runs per active language using the query translated into that language.
- German is always active; additional languages are toggled in the UI dropdown.
- Exact part numbers and codes are never translated.
- Answer language follows the query language (overridable by explicit instruction).

---

## Authentication & access control

### Session management

| Property | Value |
|---|---|
| Storage | SQLite `user_sessions` table |
| Cookie | `rag_session`, HttpOnly, SameSite=strict |
| TTL | 3 600 s (1 hour), refreshed per request |
| First-run setup | `POST /api/auth/setup` — creates the first superadmin when zero users exist |

### Roles & permissions

| Role | Who gets it |
|---|---|
| `superadmin` | First user via setup wizard; additional admins promoted in admin panel |
| `member` | All users created by an admin |

| Permission | superadmin | member |
|---|---|---|
| Read own conversations | ✅ | ✅ |
| Create conversations | ✅ | ✅ |
| Read / upload documents | ✅ | ✅ |
| Admin panel access | ✅ | ❌ |
| Audit log access | ✅ | ❌ |

### Additional access controls

- **Document-type filtering** — users can be restricted to specific document types (e.g. only HR, not Technical). No restriction rows = access to all types.
- **Department-based access** — per-user department permissions in `user_department_permissions`.
- **Conversation isolation** — each conversation belongs to one user; superadmins can view any.
- **Conversation sharing** — owners share with specific recipients (read-only via share tokens).
- **Rate limiting** — 50 messages/hour, 10 conversations/day (configurable).

### Data at rest

- Messages encrypted with AES-256-GCM + Ed25519 integrity signatures.
- Keys generated on first run in `database/keys/` (mode `0600`, never committed).
- Passwords hashed with PBKDF2-SHA256 (260 000 iterations, 32-byte salt per user).

### Audit log

Every significant action (login, logout, user CRUD, permission changes, failed auth) is appended to the `audit_log` table. Superadmins browse it in the Admin → Audit tab.

---

## Security & air-gap

| Layer | Enforcement |
|---|---|
| **Inference** | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`; all models from local paths; no cloud URLs |
| **Observability** | LangSmith OFF; Langfuse self-hosted only; traces stay internal |
| **Telemetry** | Qdrant telemetry OFF, HF telemetry OFF, `NEXT_TELEMETRY_DISABLED=1` |
| **Frontend** | All JS/CSS/fonts bundled locally; no CDN; strict same-origin CSP |
| **Network** | Default-deny egress firewall is the provable guarantee |

---

## Configuration

All behavior is controlled from `backend/config.py` — nothing is hardcoded elsewhere.

| Section | Key variables |
|---|---|
| Embedding | `EMBED_MODEL_ID`, `EMBED_DIM`, `EMBED_MAX_SEQ` |
| Reranker | `RERANKER_MODEL_ID`, `RERANKER_TOP_K` |
| LLM | `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TEMPERATURE` |
| Chunking | `CHUNK_MAX_TOKENS`, `OVERSIZE_EMBED_THRESHOLD` |
| Retrieval | `RETRIEVE_K`, `RETRIEVE_DEEP_POOL`, `MAX_ATTEMPTS`, `CONFIDENCE_THRESHOLD` |
| Languages | `AVAILABLE_LANGUAGES`, `DEFAULT_ANSWER_LANG`, `ENABLE_TRANSLATED_BM25` |
| IAM | `SEED_DEPARTMENTS`, `SEED_DOC_TYPES`, `SESSION_TTL_SECONDS`, `RATE_LIMIT_MSGS_PER_HOUR` |
| Cache | `CACHE_ENABLED`, `CACHE_TTL_SECONDS`, `CACHE_MAX_ENTRIES`, `CACHE_MIN_CONFIDENCE` |
| Observability | `LANGFUSE_ENABLED`, `LANGFUSE_HOST` (from `.env.langfuse`) |
| Storage | `DATABASE_PATH`, `QDRANT_DIR`, `ORIGINALS_DIR` |

To swap a model: change one value in `config.py`. To add a language: add one entry to `AVAILABLE_LANGUAGES` and provide `prompts/answer_<code>.txt` + `prompts/abstain_<code>.txt`.

---

## Project structure

```
.
├── Makefile                     # developer entry point (uv-based)
├── requirements.txt             # Python dependencies (pinned)
├── backend/
│   ├── config.py                # central configuration — models, thresholds, flags, IAM
│   ├── api/
│   │   ├── main.py              # FastAPI app + endpoints
│   │   └── routes/              # auth.py, admin.py, config.py
│   ├── adapters/                # embedder.py, reranker.py (Qwen3 wrappers)
│   ├── core/                    # ToolRegistry, tool_base, tool_pipeline, config_loader
│   ├── database/                # schema.sql, __init__.py (init_db), migrate_auth.py
│   ├── graph/
│   │   ├── graph.py             # LangGraph compiled graph
│   │   ├── state.py             # RAGState TypedDict
│   │   └── nodes/               # prepare_query, retrieve, rerank, score_confidence,
│   │                            # answer, escalate, abstain
│   ├── services/                # iam, auth, sessions, conversations, sharing, security,
│   │                            # rate_limit, audit, response_cache, admin, language,
│   │                            # store, sparse, citations, observability
│   └── tools/
│       ├── readers/             # 15 format readers (auto-discovered)
│       ├── parsers/             # docling_parser, eml_parser, ocr_parser
│       ├── chunkers/            # 8 domain chunkers (auto-discovered)
│       ├── pipeline.py          # ingestion orchestration
│       ├── type_detector.py     # MIME + extension detection
│       └── type_registry.py     # format → reader mapping
├── config/
│   └── tools.yaml               # enable/disable individual tools at runtime
├── prompts/                     # external prompt templates (answer, abstain, hyde × de/en)
├── frontend/
│   └── src/
│       ├── app/                 # Next.js pages: login, chat, admin, change-password, setup
│       ├── components/          # ConversationSidebar, PdfViewer, UploadPdf, icons
│       └── lib/                 # chatAdapter, auth, types, backend proxy
├── tests/                       # pytest: auth, API routes, graph nodes, tools
├── eval/                        # eval_set.json + recall_harness.py
├── scripts/                     # setup.py (first-run admin), random_chunks.py
└── database/                    # app.db + keys/ (generated at runtime, gitignored)
```

---

## Hardware

| Environment | Models | Notes |
|---|---|---|
| **Pilot** (M1 Pro / 16 GB) | Qwen3-Embedding-0.6B, Qwen3-Reranker-0.6B, Ollama qwen3:8b | CPU inference; enrichment limited to contextual headers |
| **Production** (GPU server, on-prem) | Qwen3-Embedding-4B/8B, Qwen3-Reranker via vLLM | Same code, swap model IDs in `config.py` |

---

## Tech stack

| Layer | Technology |
|---|---|
| Package management | [uv](https://docs.astral.sh/uv/) |
| Backend | FastAPI, Uvicorn, Pydantic |
| Orchestration | LangGraph |
| Embedding | Qwen3-Embedding (sentence-transformers) |
| Reranker | Qwen3-Reranker |
| Vector store | Qdrant (local) |
| Sparse search | BM25 with custom German decompounding |
| LLM | Ollama (pilot) / vLLM (production) |
| Parsing | Docling (TableFormer pipeline) |
| Frontend | Next.js 16, React 19, assistant-ui, PDF.js |
| Database | SQLite + AES-256-GCM encryption |
| Observability | Langfuse (self-hosted, optional) |
| Tests | pytest |
