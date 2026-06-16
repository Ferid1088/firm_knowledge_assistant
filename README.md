# Local RAG — Enterprise Document Intelligence

> Air-gapped, local-only Retrieval-Augmented Generation over PDFs and office documents.  
> Answers in the user's language with verified, clickable source citations.  
> Nothing leaves the company network.

---

## Agent Purpose

### What it does

This agent is a **private document intelligence workspace**. You upload internal documents (PDFs, Word files, spreadsheets, drawings, emails …), ask questions in German or English, and receive precise answers with highlighted citations that link back to the exact page and passage in the original file.

### Why it is useful

| Problem | How this agent solves it |
|---|---|
| Sensitive documents cannot leave the network | 100 % local inference — Ollama LLM, local Qwen3 embedding, self-hosted Qdrant vector store |
| Answers must be verifiable, not hallucinated | Every claim is quote-verified against the source chunk before the answer is returned |
| Tables and structured data are lost in plain-text pipelines | Docling TableFormer pipeline extracts table structure from the PDF layer; numbers are never hallucinated |
| Users write in different languages | Bidirectional DE ↔ EN retrieval; answer language follows the question language |
| Multiple staff need access to the same knowledge base | Multi-user IAM with departments, roles, per-user conversation isolation, and conversation sharing |

### Target users

Internal enterprise users on managed devices. Typical roles:

- **Technical staff** — query DIN/ISO norms, operating manuals, technical drawings
- **Legal / compliance** — search contracts, clauses, regulatory documents
- **HR / management** — policy documents, guidelines, project plans
- **Administrators** — manage users, departments, document types via the admin panel

---

## Quick start

```bash
# 1. Clone and enter the project
git clone <internal-repo-url>
cd general_RAG_pilot

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Install all dependencies (Python + Node)
make install

# 4. Copy and fill in the Langfuse credentials (optional — observability)
cp .env.langfuse.example .env.langfuse   # edit with your self-hosted keys

# 5. Start both backend and frontend
make dev
```

Open **http://localhost:3000** in your browser.  
The backend API is at **http://localhost:8000**.

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
| `make install` | `pip install -r requirements.txt` + `npm install` in `frontend/` |
| `make test` | Run the full pytest test suite (`tests/`) |

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (PWA)                            │
│   Next.js + assistant-ui  │  PDF.js viewer  │  Admin panel      │
└────────────────┬───────────────────────┬────────────────────────┘
                 │  REST / cookie auth   │
┌────────────────▼───────────────────────▼────────────────────────┐
│                    FastAPI Backend  :8000                        │
│  /api/conversations  /api/ingest  /api/originals  /api/admin    │
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │   LangGraph     │   stateful orchestration
        │   RAG Graph     │
        └────────┬────────┘
                 │
    ┌────────────┼───────────────┐
    │            │               │
┌───▼───┐  ┌────▼────┐  ┌──────▼──────┐
│Qdrant │  │ Qwen3   │  │Ollama / vLLM│
│(local)│  │Embed +  │  │(local LLM)  │
│vector │  │Reranker │  │             │
│store  │  └─────────┘  └─────────────┘
└───────┘
    │
┌───▼────────────────┐
│ SQLite (app.db)    │  users, conversations, messages
│ AES-256-GCM msgs   │  (encrypted + Ed25519 signed)
└────────────────────┘
```

---

## Ingestion pipeline

Documents go through a five-stage offline pipeline before they are searchable.

```
Upload
  │
  ▼
┌─────────────┐
│  1. DETECT  │  type_detector.py — identify format by MIME + extension
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  2. READ    │  reader selected from ToolRegistry (14 formats, see table below)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  3. PARSE   │  Docling DocumentConverter — TableFormer pipeline
│             │  do_ocr=False; scanned pages quarantined automatically
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  4. CHUNK   │  chunker selected by document type (see table below)
│             │  structural parent-child tree; atomic leaves for tables & clauses
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  5. EMBED   │  Qwen3-Embedding-0.6B (dense) + BM25 sparse vectors
│  & INDEX    │  named sparse fields per language: sparse_de, sparse_en
│             │  stored in Qdrant collection "rag_chunks"
└─────────────┘
```

### Supported file formats

| Format | Extension | Reader | Dependency | Notes |
|---|---|---|---|---|
| PDF | `.pdf` | `readers/pdf.py` | pdfplumber (via Docling) | Default; TableFormer for tables |
| Word | `.docx` | `readers/docx.py` | python-docx | Text + tables |
| Excel | `.xlsx` | `readers/xlsx.py` | openpyxl | All sheets |
| CSV | `.csv` | `readers/csv.py` | stdlib | Auto-detect delimiter |
| Plain text | `.txt` | `readers/txt.py` | stdlib | UTF-8 / Latin-1 |
| Email | `.eml` | `readers/eml.py` | stdlib email | Headers + body |
| Mailbox | `.mbox` | `readers/mbox.py` | stdlib mailbox | Multiple messages |
| Outlook | `.msg` | `readers/msg.py` | extract-msg *(opt)* | Optional dep |
| OpenDocument text | `.odt` | `readers/odt.py` | stdlib xml | |
| OpenDocument sheet | `.ods` | `readers/ods.py` | stdlib xml | |
| PowerPoint | `.pptx` | `readers/pptx.py` | python-pptx | Slide text + notes |
| SVG | `.svg` | `readers/svg.py` | stdlib xml | Text elements only |
| DXF drawing | `.dxf` | `readers/dxf.py` | ezdxf *(opt)* | Entity text extraction |
| DWG drawing | `.dwg` | `readers/dwg.py` | — | Stub; no open-source parser yet |
| Image | `.png/.jpg/…` | `readers/image.py` | Pillow | Metadata only (no OCR) |

### Chunking strategies by document type

| Document type | Chunker | Strategy |
|---|---|---|
| Authority document (DIN/ISO, norm, regulation) | `document_structure.py` | Parent heading → child prose leaves via HybridChunker (max 512 tokens); tables kept atomic |
| Table-heavy document | `table_atomic.py` | Every Docling table extracted as one atomic leaf; prose uses HybridChunker |
| Legal contract | `clause_atomic.py` | Article/Clause/Numbered paragraph → atomic leaf; nested prose windowed |
| Technical plan / work packages | `plan_chunker.py` | Phase → Work Package → Task/Milestone hierarchy; milestones atomic |
| Project document | `project_chunker.py` | Project items and milestones as atomic leaves with temporal metadata |
| Email thread | `thread_chunker.py` | Each message as one chunk; thread header as parent context |
| Image / drawing | `image_chunker.py` | Metadata + alt-text chunk; no OCR (scanned guard fires) |
| Generic prose | `hybrid.py` | HybridChunker windowed within section boundaries |

> **Scanned-PDF guard:** pages without an extractable text layer are flagged and quarantined automatically — blank chunks are never indexed.

---

## Query pipeline (LangGraph)

Every question flows through a bounded stateful graph with a hard loop cap (`MAX_ATTEMPTS = 3`).

```
User question
      │
      ▼
┌─────────────────┐
│ prepare_query   │  language detect → answer_lang
│                 │  translate query once per active language (cached)
│                 │  decompose multi-part questions into sub-questions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    retrieve     │  dense pass (Qwen3 cross-lingual, all docs)
│                 │  + BM25 pass per active language (sparse_de, sparse_en …)
│                 │  Reciprocal Rank Fusion → deep pool (~50 candidates)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     rerank      │  Qwen3-Reranker → top-8 scored candidates
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│score_confidence │  top-1 score vs threshold (0.55)
│                 │  gap to top-2 for uncertainty signal
└────────┬────────┘
         │
    ┌────┴──────────────────┐
    │ ROUTER                │
    ▼                       ▼                    ▼
┌────────┐          ┌──────────────┐      ┌──────────┐
│ answer │          │   escalate   │      │  abstain │
│        │          │ widen pool   │      │ (no      │
│ local  │          │ rewrite query│      │ answer   │
│ LLM in │          │ loop back    │      │ grounded)│
│ answer │          │ to retrieve  │      └──────────┘
│ _lang  │          └──────────────┘
└────────┘
    │
    ▼
JSON contract
  { answer, claims: [{text, source, quote, verified}] }
    │
    ▼
Quote verification  ←  checks each quote against source chunk text
    │
    ▼
artifact_chunks     ←  {chunk_id, text, boxes, address, quote}
    │
    ▼
Response cache      ←  SHA-256 keyed; TTL 1 h; skips pipeline on hit
    │
    ▼
Persist to SQLite   ←  encrypted (AES-256-GCM) + Ed25519 signed
    │
    ▼
ChatResponse → UI
```

### Retrieval parameters

| Parameter | Default | Description |
|---|---|---|
| `RETRIEVE_DEEP_POOL` | 50 | Candidates retrieved before reranking |
| `RERANKER_TOP_K` | 8 | Candidates passed into reranker |
| `RETRIEVE_K` | 5 | Final top-k sent to answer node |
| `CONFIDENCE_THRESHOLD` | 0.55 | Below this → escalate |
| `CONFIDENCE_GAP_MIN` | 0.05 | Small top-1/top-2 gap adds uncertainty |
| `MAX_ATTEMPTS` | 3 | Hard escalation loop cap |

### Language handling

| Scenario | Behaviour |
|---|---|
| German question, German docs | German BM25 pass (with decompounding) + dense retrieval |
| English question, English docs | English BM25 pass + dense retrieval |
| German question, mixed DE+EN docs | Dense retrieval (cross-lingual) + BM25 in both languages |
| Exact part number / code in query | Code never translated; BM25 matches verbatim across all languages |
| Low confidence after 3 attempts | Abstain response in the user's language |

---

## Security & air-gap

| Layer | What is enforced |
|---|---|
| **Inference** | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`; all models loaded from local paths; no cloud base_url anywhere |
| **Observability** | LangSmith OFF; Langfuse self-hosted only (port 3001); traces never leave the network |
| **Telemetry** | Qdrant telemetry OFF, HF telemetry OFF, `NEXT_TELEMETRY_DISABLED=1` |
| **Frontend assets** | All JS/CSS/fonts bundled locally; no CDN; strict same-origin CSP |
| **Auth** | Cookie-based sessions (PBKDF2-SHA256 passwords); session TTL 1 h; rate-limited (50 msg/h, 10 conv/day) |
| **Data at rest** | Messages AES-256-GCM encrypted + Ed25519 integrity signatures in SQLite |
| **Key material** | `database/keys/` generated on first run, `0600`, never committed |
| **Network** | Default-deny egress firewall is the provable guarantee; all other layers are defence-in-depth |

---

## Project structure

```
.
├── Makefile                    # developer entry point
├── requirements.txt            # Python dependencies (pinned)
├── backend/
│   ├── config.py               # ALL configuration — models, thresholds, flags, IAM
│   ├── api/
│   │   ├── main.py             # FastAPI app + all endpoints
│   │   └── routes/             # auth, admin sub-routers
│   ├── adapters/               # embedder.py, reranker.py (Qwen3 wrappers)
│   ├── core/                   # ToolRegistry, config_loader, tool_base
│   ├── database/               # schema.sql, __init__.py (init_db)
│   ├── graph/
│   │   ├── graph.py            # LangGraph compiled graph + run()
│   │   ├── state.py            # RAGState TypedDict
│   │   └── nodes/              # one file per node: prepare_query, retrieve, rerank …
│   ├── services/               # iam, auth, conversations, security, sharing,
│   │                           # sessions, rate_limit, audit, observability,
│   │                           # response_cache, admin, language, store, sparse
│   └── tools/
│       ├── readers/            # 14 format readers
│       ├── parsers/            # docling_parser, eml_parser, ocr_parser
│       └── chunkers/           # 8 domain chunkers
├── config/
│   └── tools.yaml              # enable / disable individual file-reader tools
├── prompts/                    # external prompt templates (answer_de/en, abstain, hyde)
├── frontend/
│   └── src/
│       ├── app/                # Next.js pages: login, chat, admin, change-password
│       ├── components/         # ConversationSidebar, PdfViewer, UploadPdf, icons
│       └── lib/                # chatAdapter, auth, types
├── tests/                      # pytest: access control, encryption, rate limit,
│                               # sessions, integrity
├── eval/                       # recall_harness.py — recall@k evaluation
└── scripts/                    # setup.py (first-run admin), random_chunks.py
```

---

## Configuration reference

All behaviour is controlled from **`backend/config.py`** — no values are hardcoded elsewhere.

| Section | Key variables |
|---|---|
| Embedding | `EMBED_MODEL_ID`, `EMBED_DIM`, `EMBED_MAX_SEQ`, `EMBED_QUERY_INSTRUCTION` |
| Reranker | `RERANKER_MODEL_ID`, `RERANKER_TOP_K` |
| LLM | `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TEMPERATURE` |
| Chunking | `CHUNK_MAX_TOKENS`, `OVERSIZE_EMBED_THRESHOLD` |
| Retrieval | `RETRIEVE_K`, `RETRIEVE_DEEP_POOL`, `MAX_ATTEMPTS`, `CONFIDENCE_THRESHOLD` |
| Languages | `AVAILABLE_LANGUAGES`, `DEFAULT_ANSWER_LANG`, `ENABLE_TRANSLATED_BM25` |
| IAM | `SEED_DEPARTMENTS`, `SESSION_TTL_SECONDS`, `RATE_LIMIT_MSGS_PER_HOUR` |
| Cache | `CACHE_ENABLED`, `CACHE_TTL_SECONDS`, `CACHE_MAX_ENTRIES`, `CACHE_MIN_CONFIDENCE` |
| Observability | `LANGFUSE_ENABLED`, `LANGFUSE_HOST` (read from `.env.langfuse`) |
| Storage | `DATABASE_PATH`, `QDRANT_DIR`, `ORIGINALS_DIR` |

To swap a model: change one value in `config.py`. To add a language: add one entry to `AVAILABLE_LANGUAGES` and provide `prompts/answer_<code>.txt` + `prompts/abstain_<code>.txt`.

---

## Tool registry

All file readers, parsers, and chunkers are discovered automatically from their directories and registered in the `ToolRegistry` ([backend/core/tool_registry.py](backend/core/tool_registry.py)). Enable or disable individual tools at runtime without touching code — edit [config/tools.yaml](config/tools.yaml).

### File readers

| Tool key | File | Extensions | Enabled | Timeout | Max size | Dep |
|---|---|---|---|---|---|---|
| `reader:pdf` | `readers/pdf.py` | `.pdf` | ✅ | 60 s | 100 MB | Docling |
| `reader:docx` | `readers/docx.py` | `.docx` | ✅ | 30 s | 50 MB | python-docx |
| `reader:xlsx` | `readers/xlsx.py` | `.xlsx` | ✅ | 30 s | 50 MB | openpyxl |
| `reader:csv` | `readers/csv.py` | `.csv` | ✅ | 15 s | 100 MB | stdlib |
| `reader:txt` | `readers/txt.py` | `.txt` | ✅ | 10 s | 20 MB | stdlib |
| `reader:eml` | `readers/eml.py` | `.eml` | ✅ | 15 s | 25 MB | stdlib |
| `reader:mbox` | `readers/mbox.py` | `.mbox` | ✅ | 60 s | 200 MB | stdlib |
| `reader:msg` | `readers/msg.py` | `.msg` | ✅ | 15 s | 25 MB | extract-msg |
| `reader:odt` | `readers/odt.py` | `.odt` | ✅ | 30 s | 50 MB | stdlib xml |
| `reader:ods` | `readers/ods.py` | `.ods` | ✅ | 30 s | 50 MB | stdlib xml |
| `reader:pptx` | `readers/pptx.py` | `.pptx` | ✅ | 60 s | 100 MB | python-pptx |
| `reader:svg` | `readers/svg.py` | `.svg` | ✅ | 10 s | 10 MB | stdlib xml |
| `reader:dxf` | `readers/dxf.py` | `.dxf` | ✅ | 30 s | 100 MB | ezdxf |
| `reader:image` | `readers/image.py` | `.png .jpg .webp …` | ✅ | 30 s | 50 MB | Pillow |
| `reader:dwg` | `readers/dwg.py` | `.dwg` | ❌ | 30 s | 100 MB | *(stub — no open-source parser)* |

To disable a reader: set `enabled: false` under its key in [config/tools.yaml](config/tools.yaml). The type-detector will reject that extension at upload time.

### Parsers

| Tool | File | Purpose |
|---|---|---|
| `docling_parser` | `parsers/docling_parser.py` | Primary parser — Docling TableFormer pipeline, `do_ocr=False`; produces `DoclingDocument` used by all structural chunkers |
| `eml_parser` | `parsers/eml_parser.py` | Email-specific extraction (headers, MIME parts, inline attachments) before threading |
| `ocr_parser` | `parsers/ocr_parser.py` | Stub for future scanned-PDF path — currently raises if called; scanned pages are quarantined, not silently ingested |

### Chunkers

| Tool | File | Input | Chunk types produced |
|---|---|---|---|
| `document_structure` | `chunkers/document_structure.py` | DoclingDocument | `heading` (parent) + `prose` leaves via HybridChunker |
| `table_atomic` | `chunkers/table_atomic.py` | DoclingDocument | `table` (atomic, whole — never split even if > 512 tokens) |
| `clause_atomic` | `chunkers/clause_atomic.py` | DoclingDocument | `recommendation` / clause (atomic); nested prose windowed |
| `hybrid` | `chunkers/hybrid.py` | DoclingDocument / text | `prose` (HybridChunker, max 512 tokens, section-windowed) |
| `plan_chunker` | `chunkers/plan_chunker.py` | Project-plan docs | `plan_item`, `milestone` (atomic with temporal metadata) |
| `project_chunker` | `chunkers/project_chunker.py` | Project documents | `project_item`, `milestone` (atomic) |
| `thread_chunker` | `chunkers/thread_chunker.py` | Email / forum threads | one chunk per message; thread header as parent context |
| `image_chunker` | `chunkers/image_chunker.py` | Image / drawing files | metadata + alt-text chunk (no OCR; scanned guard fires) |

---

## Authentication & access policy

### Login flow

```
Browser                   Next.js middleware           FastAPI
  │                             │                          │
  │── GET /any-protected-page──▶│                          │
  │                             │── check session cookie──▶│
  │                             │◀── 401 Unauthorized ─────│
  │◀── redirect /login ─────────│                          │
  │                             │                          │
  │── POST /api/auth/login ─────────────────────────────▶  │
  │                             │  PBKDF2-SHA256 verify     │
  │                             │  create session (SQLite)  │
  │◀── Set-Cookie: session=… ───────────────────────────── │
  │                             │                          │
  │── GET /any-protected-page──▶│                          │
  │                             │── validate cookie ──────▶│
  │                             │◀── 200 OK + user object ─│
  │◀── serve page ──────────────│                          │
```

### Session management

| Property | Value |
|---|---|
| Storage | SQLite `sessions` table (no Redis needed at pilot scale) |
| Cookie name | `session` |
| TTL | 3 600 s (1 hour); refreshed on each request |
| Scope | `HttpOnly`, `SameSite=strict`, served over internal network |
| Termination | `POST /api/auth/logout` deletes the session row |
| First-run setup | `POST /api/auth/setup` — only callable when zero users exist; creates the first superadmin |

### Roles & permissions

Two built-in roles. All roles and permissions are seeded idempotently on startup from [backend/services/iam.py](backend/services/iam.py); no migration scripts needed.

| Role | Display name | Who gets it |
|---|---|---|
| `superadmin` | Super Admin | First user created via setup wizard; additional admins promoted in the admin panel |
| `member` | Member | All other users created by an admin |

Permission matrix:

| Permission | Resource | Action | superadmin | member |
|---|---|---|---|---|
| `perm_conv_read_own` | conversations | read own | ✅ | ✅ |
| `perm_conv_create` | conversations | create | ✅ | ✅ |
| `perm_doc_read` | documents | read | ✅ | ✅ |
| `perm_doc_upload` | documents | upload | ✅ | ✅ |
| `perm_admin_access` | admin panel | access | ✅ | ❌ |
| `perm_audit_view` | audit log | view | ✅ | ❌ |

### Document-type access control

Each user can be restricted to a subset of document types (e.g., only `HR`, not `Technical`). The `user_doc_type_permissions` table stores the allow-list. If the table has no row for a user, they see all document types. The `allowed_doc_type_ids` list is embedded in every response-cache key so cross-filter cache pollution is impossible.

### Rate limiting

| Limit | Default | Config key |
|---|---|---|
| Messages per hour | 50 | `RATE_LIMIT_MSGS_PER_HOUR` |
| Conversations per day | 10 | `RATE_LIMIT_CONVERSATIONS_PER_DAY` |
| Enforcement | SQLite counters reset on the hour / midnight UTC | — |

### Password policy

| Property | Implementation |
|---|---|
| Hashing | `hashlib.pbkdf2_hmac` (SHA-256, 260 000 iterations) — stdlib, no bcrypt dep |
| Salt | 32-byte random per user, stored alongside hash |
| Change | `POST /api/auth/change-password` — requires current password |
| Reset | Admin sets a temporary password in the admin panel; user must change on next login |

### Audit log

Every significant action (login, logout, user create/delete, permission change, failed auth) is appended to the `audit_log` SQLite table with `user_id`, `action`, `target`, `ip_address`, and `timestamp`. Superadmins can browse the full log in the **Admin → Audit** tab.

### Conversation isolation & sharing

- Each conversation belongs to exactly one `user_id`; the API enforces ownership on every read/write/delete.
- A superadmin can view any conversation.
- Owners can generate a share token (`POST /api/conversations/{id}/share`) that grants read-only access to a specific recipient user. The `conversation_shares` table stores `(share_id, conversation_id, owner_id, recipient_id, created_at)`.
- Messages are stored AES-256-GCM encrypted with an Ed25519 integrity signature. Keys live in `database/keys/` (mode `0600`, never committed).

---

## Hardware

| Environment | Models | Notes |
|---|---|---|
| **Pilot** (M1 Pro / 16 GB) | Qwen3-Embedding-0.6B, Qwen3-Reranker-0.6B, Ollama qwen3:8b | CPU inference; enrichment limited to contextual headers |
| **Production** (GPU server, on-prem) | Qwen3-Embedding-4B/8B, Qwen3-Reranker via vLLM | Same code, swap model IDs in `config.py` |
