# Firm Knowledge Assistant — Local RAG Agent

**A commercial-grade, air-gapped Retrieval-Augmented Generation (RAG) system** for enterprise knowledge bases. This system ingests native PDFs (text + tables), stores embeddings locally, and answers user questions with verified, clickable source citations—all without any data leaving your network.

---

## Table of Contents

1. [What This Is](#what-this-is)
2. [Architecture Overview](#architecture-overview)
3. [How It Works: The Two Pipelines](#how-it-works-the-two-pipelines)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Directory Structure](#directory-structure)
7. [Security & Air-Gap Design](#security--air-gap-design)
8. [Using the System](#using-the-system)
9. [Advanced: How Each Component Works](#advanced-how-each-component-works)
10. [Troubleshooting](#troubleshooting)

---

## What This Is

This is a **local RAG agent**—a system that:

- **Ingests PDFs locally**: parses native PDFs (with text layers), extracts text and table structures, splits them into semantically coherent chunks with metadata
- **Embeds & indexes**: uses local embeddings (Qwen3-Embedding) + BM25 sparse search (with German compound decompounding) to create a searchable knowledge base
- **Retrieves in multiple languages**: supports German, English, French, and more; queries are translated once and cached; retrieval runs in all configured languages
- **Answers with citations**: uses a local LLM (Ollama or vLLM) to generate grounded answers; every claim is verified against the source text, and failing quotes are flagged
- **Shows source documents**: highlights the exact passages (with PDF page numbers and bounding boxes) that back each answer
- **Works completely offline**: no cloud APIs, no internet required; everything runs on local hardware (M1 Mac for pilot, GPU server for production)

### Target Use Cases

- Regulatory compliance (e.g., enterprise contracts, legal documents)
- Technical documentation (user manuals, specifications with tables)
- Internal knowledge bases (policies, processes, domain-specific guides)
- Anything requiring **audit trails** (who asked what, what sources were used)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER BROWSER (Next.js + PDF.js)              │
│  - Upload PDFs / Ask questions                                  │
│  - View answers with highlighted source passages                │
│  - Click to jump to page in source PDF                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    HTTP / JSON
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              FastAPI Backend (api.py)                           │
│  - /api/chat: query endpoint                                    │
│  - /api/ingest: document ingestion                              │
│  - /api/originals: serve source PDFs                            │
│  - /api/config: expose UI-relevant settings                     │
└──────────────────────┬───────────────────────────────────────────┘
                       │
        ┌──────────────┴────────────────┐
        │                               │
        ▼                               ▼
    LangGraph                     Ingest Pipeline
    (Query Engine)                 (Index Builder)
        │                               │
        │                               ▼
        │                         Docling
        │                    (parse PDFs)
        │                               │
        │                               ▼
        │                      Structural Chunking
        │                (parent-child hierarchy,
        │                 preserve tables whole)
        │                               │
        │                               ▼
        │                      Embedding & BM25
        │                 (Qwen3 dense + sparse)
        │                               │
        │                               ▼
        │                          Qdrant
        │                  (vector database)
        │                               │
        └───────────────┬───────────────┘
                        │
                        ▼
              (retrieve, rerank, answer)
```

### Core Components

| Component | Purpose | Tech |
|-----------|---------|------|
| **Docling** | Parse PDFs → document tree with structure | DoclingDocument (native PDF support, no OCR for now) |
| **Structural Chunker** | Preserve semantics: headings as parents, tables/prose as leaves | Custom (Python) |
| **Qwen3-Embedding** | Generate dense vectors for retrieval | 0.6B (pilot), 4B/8B (production) |
| **BM25 Sparse Indices** | Lexical search with German decompounding | Custom (own tokenization) |
| **Qdrant** | Store + retrieve dense + sparse vectors with metadata | Self-hosted, local |
| **LangGraph** | Orchestrate the query pipeline as a state machine | Python (graph-based control flow) |
| **Qwen3-Reranker** | Rank top candidates by relevance | 0.6B |
| **Ollama** (pilot) / **vLLM** (prod) | Local LLM for answering | Language model runtime |
| **Next.js + assistant-ui** | Responsive web UI | TypeScript/React |
| **PDF.js** | Client-side PDF viewer (bundled locally) | JavaScript |

---

## How It Works: The Two Pipelines

### Pipeline 1: Ingestion (Offline, Linear)

When you upload a PDF, this happens:

```
PDF Upload
    ↓
[1] PARSE with Docling
    ├─ Extract text, tables, layout structure
    ├─ Guard: reject empty/scanned pages (no OCR for now)
    └─ Store page sizes for bbox normalization
    ↓
[2] STRUCTURE CLASSIFICATION
    ├─ Heading → parent node (carries heading path)
    ├─ Table → atomic leaf (kept WHOLE, even if > 512 tokens)
    ├─ Recommendation/clause → atomic leaf (domain-specific heuristic)
    └─ Prose → leaf produced by token-aware splitter
    ↓
[3] METADATA & VERSIONING
    ├─ Normalize bounding boxes: 0..1 fractions (page-independent)
    ├─ Extract section addresses: (doc_id, chapter, §, point)
    ├─ Detect language per chunk (de/en/etc.)
    ├─ Assign parent_id (heading parents link to children)
    ├─ Set version_id + is_current=True
    ├─ Flag cross-references (regex on "§...", "Art.")
    └─ Store original PDF in local /originals/ directory
    ↓
[4] EMBEDDING
    ├─ Prepend contextual header (parent heading for prose)
    ├─ Embed with Qwen3 (dense vector, 1024 dims for 0.6B)
    ├─ Apply instruction prefix to queries only (not documents)
    └─ Generate BM25 sparse vectors
         ├─ German: lowercase → stopwords → stemming → DECOMPOUNDING
         └─ English: lowercase → stopwords → stemming
    ↓
[5] INDEX in Qdrant
    ├─ Dense vector + named sparse vectors per language
    │  (sparse_de, sparse_en, sparse_fr, ...)
    ├─ Chunk metadata (lang, parent_id, is_current, address, pages)
    ├─ Bounding boxes (normalized)
    └─ Source PDF path
    ↓
[6] ENRICH (tiered, DEFER on 16 GB pilot)
    ├─ Always: contextual header (cheap)
    ├─ High-value types (tables, recommendations):
    │  ├─ Description for oversize leaves (if > 400 tokens)
    │  └─ HyDE (hypothetical document expansions)
    └─ Semantic tags (soft hints, not authoritative)
```

**Key Design Choices:**

- **Structural preservation**: Tables are never split; prose is windowed by tokens (default 512). This ensures tables stay intact and readable.
- **Versioning**: If you re-ingest a document, the old chunks get `is_current=False`; the new ones are active. Old data stays queryable (for audit) but doesn't clutter results.
- **Language-specific sparse indices**: Each language has its own `sparse_X` field in Qdrant, populated at ingest time based on detected language. This allows per-language BM25 passes at query time.
- **No translation at index time**: Documents stay in their original language; translation happens query-side (once, cached).

---

### Pipeline 2: Query (Stateful, Looping via LangGraph)

When you ask a question, this state machine runs:

```
USER QUESTION
    ↓
[0] PREPARE_QUERY
    ├─ Detect query language (langdetect)
    ├─ Set answer_lang: explicit > detected > German default
    ├─ Read active_languages: de (always) + user-selected from UI
    ├─ Translate query ONCE into each active language
    │  └─ Cached in state (not recomputed on loops)
    ├─ Detect multi-part queries (cheap classifier)
    │  └─ If detected: decompose into sub_questions
    └─ State: {question, query_lang, answer_lang, translated_queries}
    ↓
[1] RETRIEVE (bidirectional hybrid fan-out)
    ├─ DENSE (cross-lingual backbone):
    │  └─ Query embedding → find top-50 from all docs
    ├─ BM25 PER ACTIVE LANGUAGE (from LanguageRegistry):
    │  ├─ German pass (always): search sparse_de field
    │  ├─ English pass (if en ∈ active_langs): search sparse_en field
    │  ├─ French pass (if fr ∈ active_langs): search sparse_fr field
    │  └─ Each pass uses the translated_query in that language
    ├─ Do NOT translate exact codes (§123, ABC-456 match as-is)
    ├─ Fuse all passes with Reciprocal Rank Fusion (RRF)
    └─ Return DEEP POOL (~50) for reranker
    ↓
[2] RERANK (Qwen3-Reranker)
    ├─ Score each candidate (0..1 confidence)
    ├─ Keep top-k (default 5) by score
    └─ Compute confidence gap: gap = score[0] - score[1]
    ↓
[3] SCORE_CONFIDENCE
    ├─ Check: score[0] >= CONFIDENCE_THRESHOLD (0.55)?
    ├─ Check: gap >= CONFIDENCE_GAP_MIN (0.05) [clear winner]?
    └─ Decision: proceed OR escalate?
    ↓
    ┌─────────────────────────────────────────────┐
    │  CONFIDENCE ROUTER (conditional edge)       │
    ├─────────────────────────────────────────────┤
    │ IF confidence >= threshold AND clear winner │
    │   → [4a] ANSWER                             │
    │ ELIF attempts < max_attempts (3)            │
    │   → [4b] ESCALATE                           │
    │ ELSE                                        │
    │   → [4c] ABSTAIN                            │
    └─────────────────────────────────────────────┘
         ↓
    ┌─────────────────────────────────────────────┐
    │ [4a] ANSWER (if confident enough)           │
    ├─────────────────────────────────────────────┤
    │ ├─ Expand context: add parent headings      │
    │ ├─ (Optional) add ±1 siblings (OFF by def)  │
    │ ├─ Call local LLM in answer_lang            │
    │ │  (instructions in prompts/answer_<lang>)  │
    │ ├─ Parse JSON: {answer, claims}             │
    │ ├─ VERIFY each claim's quote:               │
    │ │  ├─ Normalize whitespace, case            │
    │ │  ├─ Check quote ⊂ source chunk text       │
    │ │  ├─ For numbers: verify presence          │
    │ │  └─ Mark verified=True/False              │
    │ ├─ Build artifact_chunks:                   │
    │ │  ├─ chunk_id, text, boxes (normalized)    │
    │ │  ├─ address (§, chapter, etc.)            │
    │ │  └─ doc_id (for PDF.js fetch)             │
    │ └─ Return: {answer, claims, artifact_chunks}│
    └─────────────────────────────────────────────┘
         ↓
    ┌─────────────────────────────────────────────┐
    │ [4b] ESCALATE (if low confidence, retry)    │
    ├─────────────────────────────────────────────┤
    │ ├─ Increment attempts counter               │
    │ ├─ Try rungs (in order):                    │
    │ │  1. Query rewrite (generic, per-lang)     │
    │ │  2. Widen pool (k up)                     │
    │ │  3. Decompose (if multi-part)             │
    │ │  4. Fail gracefully after max_attempts    │
    │ ├─ Updated query → back to [1] RETRIEVE     │
    │ └─ Loop with fresh context (dense fresh)    │
    └─────────────────────────────────────────────┘
         ↓
    ┌─────────────────────────────────────────────┐
    │ [4c] ABSTAIN (low conf, max attempts hit)   │
    ├─────────────────────────────────────────────┤
    │ └─ "I can't ground this in the documents"   │
    │    (in answer_lang)                         │
    └─────────────────────────────────────────────┘
         ↓
      FINAL OUTPUT
      {answer, answer_lang, confidence, attempts,
       claims, artifact_chunks, supporting_points, caveats}
```

**Key Design Choices:**

- **Language-aware retrieval**: Each active language gets a dedicated BM25 pass; the query is translated once and cached so loops don't re-translate.
- **Confidence router**: Answers flow through the same logic whether retrieved in one shot or escalated. Low confidence or uncertainty → escalate → rewrite/retry.
- **Query rewrite escalation**: If the first pass returns weak results, the second rung rewrites the query (e.g., "is this safe?" → "is X compliant with Y?") using per-language few-shots and an optional domain dictionary.
- **Bounded loops**: max_attempts (default 3) prevents infinite spirals; escalation is controlled, not agentic.
- **Citation verification**: Claims must quote the source text verbatim (whitespace-normalized). Unverified claims are flagged, not silently deleted.

---

## Installation & Setup

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** (for Next.js frontend)
- **Git**
- **Ollama** (optional, for local LLM; skip if using vLLM on a GPU server)
- **macOS, Linux, or Windows with WSL2** (the project is tested on M1 macOS)

### Quick Start (One Command)

From the project root:

```bash
bash run.sh
```

This script will:
1. Create a Python virtual environment (`.venv`) if it doesn't exist
2. Install Python dependencies from `requirements.txt`
3. Install Node.js dependencies in `frontend/` from `package.json`
4. Start Ollama (if available locally)
5. Start the FastAPI backend on `http://127.0.0.1:8000`
6. Start the Next.js frontend on `http://localhost:3000`
7. Log all output to `.logs/`

Once running:
- Open your browser to **`http://localhost:3000`**
- Upload a PDF
- Ask questions about it

### Manual Setup (Step-by-Step)

If you prefer to set up manually:

#### 1. Backend Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: set Langfuse credentials (self-hosted only)
export LANGFUSE_ENABLED=true
export LANGFUSE_HOST=http://localhost:3001
export LANGFUSE_PUBLIC_KEY=your-key
export LANGFUSE_SECRET_KEY=your-secret
```

#### 2. Start Ollama (if using local LLM)

```bash
# If not already running, start Ollama in a separate terminal
ollama serve
```

In another terminal, pull a model:

```bash
ollama pull qwen3:8b
```

#### 3. Start the Backend

```bash
python -m src.api
```

The API will start on `http://127.0.0.1:8000`.

#### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will start on `http://localhost:3000`.

---

## Configuration

All configuration is centralized in **`config.py`** at the project root. This file controls:

### Embedding & Reranking

```python
EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"  # swap to 4B/8B for production
EMBED_DIM = 1024
EMBED_MAX_SEQ = 2048  # CPU-practical cap; full 8192 needs GPU
RERANKER_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
RERANKER_TOP_K = 8  # rerank this many → return top 5
```

### LLM for Answering

```python
OLLAMA_MODEL = "qwen3:8b"  # local Ollama model
OLLAMA_BASE_URL = "http://localhost:11434"  # never a cloud URL
OLLAMA_TEMPERATURE = 0  # deterministic answering
```

### Retrieval & Confidence

```python
RETRIEVE_K = 5  # return top-5 chunks to the answer node
RETRIEVE_DEEP_POOL = 50  # deep pool for reranker
CONFIDENCE_THRESHOLD = 0.55  # escalate if below this
CONFIDENCE_GAP_MIN = 0.05  # escalate if gap < this
MAX_ATTEMPTS = 3  # hard cap on escalation loops
```

### Features

```python
ENABLE_TRANSLATED_BM25 = True  # run BM25 per active language
ENABLE_SIBLING_EXPANSION = False  # add ±1 siblings (OFF until eval lift)
ENABLE_HYDE = False  # HyDE descriptions (deferred to GPU)
```

### Query Rewriting (Escalation)

```python
REWRITE = {
    "enabled": True,
    "trigger": "reactive",  # only on low-confidence escalation
    "use_llm": True,  # rewrite with local LLM
    "use_dictionary": False,  # opt-in per corpus
    "protected_patterns": [
        r"§\s*\d+",  # legal section numbers
        r"\b[A-Z]{1,3}-?\d+\b",  # part codes (ABC-456)
        r"\b\d+([.,]\d+)?\b",  # numbers
    ],
}
```

### Chunking

```python
CHUNK_MAX_TOKENS = 512  # prose windowing only
OVERSIZE_EMBED_THRESHOLD = 400  # leaves > 400 tokens get a description embedded
```

### Toggling Languages

Languages are registered in `AVAILABLE_LANGUAGES` (see below). The UI reads this list and allows the user to toggle which languages to search in:

```python
AVAILABLE_LANGUAGES = [
    ("de", "German", german_analyzer_config),
    ("en", "English", english_analyzer_config),
    ("fr", "French", french_analyzer_config),
]
```

For a language to be searchable at query time:
1. It **must** be in `AVAILABLE_LANGUAGES` at **ingestion time** (so its `sparse_X` field gets created)
2. At **query time**, the user can toggle it on/off via the UI dropdown

### Adding a New Language

1. Add an entry to `AVAILABLE_LANGUAGES` in `config.py` with its analyzer (tokenization, stemming, decompounding rules)
2. Ensure translation coverage (the MT model supports it)
3. Add prompt files for that language in `prompts/`:
   - `prompts/answer_<lang>.txt`
   - `prompts/abstain_<lang>.txt`
   - `prompts/rewrite_<lang>.txt`
4. Add few-shots if using rewriting:
   - `rewrite_data/rewrite_fewshots_<lang>.yaml`
5. Re-ingest the knowledge base (rebuilds indices with the new language)

---

## Directory Structure

```
/
├── CLAUDE.md                          # Full architecture spec (READ THIS FIRST)
├── README_DETAILED.md                 # This file
├── config.py                          # Central configuration (EDIT THIS)
├── requirements.txt                   # Python dependencies
├── run.sh                             # One-command launcher
│
├── src/                               # Backend code (Python)
│   ├── api.py                         # FastAPI HTTP endpoints
│   ├── __init__.py
│   │
│   ├── ingest/                        # Ingestion pipeline
│   │   ├── __init__.py
│   │   ├── pipeline.py                # Main ingest orchestrator
│   │   ├── parse.py                   # Docling wrapper
│   │   └── chunk.py                   # Structural chunking logic
│   │
│   ├── query/                         # Query pipeline (LangGraph)
│   │   ├── __init__.py
│   │   ├── reranker.py                # Qwen3-Reranker wrapper
│   │   │
│   │   └── graph/                     # LangGraph nodes & state
│   │       ├── __init__.py
│   │       ├── graph.py               # Build & run the state machine
│   │       ├── nodes.py               # Node implementations
│   │       └── state.py               # RAGState TypedDict
│   │
│   ├── rewrite/                       # Query rewriting (escalation)
│   │   ├── __init__.py
│   │   ├── rewriter.py                # Main rewrite logic
│   │   ├── fusion.py                  # LLM inference
│   │   ├── protected.py               # Protect exact codes
│   │   └── rules.py                   # Heuristic rules
│   │
│   ├── structure/                     # Structure classification & correction
│   │   ├── __init__.py
│   │   ├── classify.py                # LLM-based or heuristic classification
│   │   ├── post_chunk.py              # Post-chunking correction
│   │   └── rules.py                   # Per-corpus rules (PDF-specific)
│   │
│   └── common/                        # Shared utilities
│       ├── __init__.py
│       ├── citations.py               # Quote verification
│       ├── embed.py                   # Embedding & BM25 logic
│       ├── language.py                # LanguageRegistry & i18n
│       ├── sparse.py                  # BM25 tokenization
│       ├── store.py                   # Qdrant client wrapper
│       └── tracing.py                 # Langfuse integration
│
├── frontend/                          # Next.js frontend (TypeScript)
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx               # Chat UI
│   │   │   ├── layout.tsx
│   │   │   ├── globals.css
│   │   │   └── api/
│   │   │       ├── chat/route.ts      # Proxy to backend /api/chat
│   │   │       ├── ingest/route.ts    # Proxy to /api/ingest
│   │   │       ├── config/route.ts    # Proxy to /api/config
│   │   │       └── originals/[docId]/route.ts  # Proxy PDF serving
│   │   │
│   │   ├── components/
│   │   │   ├── PdfViewer.tsx          # Local PDF.js viewer
│   │   │   └── UploadPdf.tsx          # File upload UI
│   │   │
│   │   └── lib/
│   │       ├── backend.ts             # HTTP client for backend
│   │       ├── chatAdapter.ts         # Adapter for assistant-ui
│   │       └── types.ts               # Shared TypeScript types
│   │
│   └── public/
│       └── pdf.worker.min.mjs         # PDF.js worker (bundled locally)
│
├── prompts/                           # External prompt templates (language-keyed)
│   ├── answer_de.txt
│   ├── answer_en.txt
│   ├── abstain_de.txt
│   ├── abstain_en.txt
│   ├── rewrite_de.txt
│   ├── rewrite_en.txt
│   ├── hyde_de.txt
│   ├── hyde_en.txt
│   └── structure_classify_de.txt
│
├── rewrite_data/                      # Few-shots & optional dictionaries
│   ├── rewrite_fewshots_de.yaml       # German query rewrite examples
│   ├── rewrite_fewshots_en.yaml       # English query rewrite examples
│   └── rewrite_dictionary.default.yaml  # (optional) domain-specific terms
│
├── eval/                              # Evaluation harness & test set
│   ├── eval_set.json                  # Q&A pairs with expected chunk ids
│   ├── recall_harness.py              # Measures retrieval recall@k
│   └── rewrite_eval.py                # Measures rewrite effectiveness
│
├── docs/
│   ├── CLAUDE.md                      # Full spec (same as root)
│   └── superpowers/plans/             # Design docs
│
├── originals/                         # Storage for source PDFs
│   └── _staging/                      # Upload staging dir
│
├── samples/                           # Example PDFs for testing
│   └── README.md
│
├── scripts/
│   ├── show_chunks.py                 # Debug: inspect chunks for a PDF
│   └── start_langfuse.sh              # Boot local Langfuse instance
│
└── .venv/                             # Python virtual environment (created by run.sh)
```

---

## Security & Air-Gap Design

This system is designed to be **completely offline and auditable**. Here's how:

### 1. Offline Inference Path (HIGHEST PRIORITY)

Every model is **local and offline**:

```bash
# Set in config.py (hardcoded, not user-writable)
export HF_HUB_OFFLINE=1                 # No HF hub calls
export TRANSFORMERS_OFFLINE=1           # No model downloads
export HF_HUB_DISABLE_TELEMETRY=1       # No telemetry

EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"  # must already be cached
RERANKER_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"  # must already be cached
OLLAMA_BASE_URL = "http://localhost:11434"    # local only, never a cloud URL
```

**No cloud APIs are called**—not DeepL, not OpenAI, not Hugging Face inference endpoints.

### 2. No Observability Leaks

- **LangSmith**: Disabled (set `LANGCHAIN_TRACING_V2=false` in config.py)
- **Langfuse**: Self-hosted only (run `scripts/start_langfuse.sh`); it stores data locally
- **Crash reporting** (Sentry, etc.): Disabled
- **Logs**: Stay local; never shipped to external aggregators

### 3. No Client-Side Leaks

- **No CDNs**: All assets (fonts, libraries, PDF.js) bundled in the `frontend/public/` directory
- **No external fonts**: No Google Fonts or similar
- **No analytics**: No GA, Vercel, Sentry on the client
- **No NEXT_PUBLIC secrets**: No credentials hardcoded in the browser bundle
- **Content-Security-Policy**: Strict, same-origin only (enforced by the frontend)

### 4. Network Isolation (Auditable)

This is **the** verification layer:

- **Default-deny egress firewall**: Assume the network is air-gapped; nothing can call out without explicit routing
- **Internal DNS & NTP**: Don't rely on external time servers or name resolution
- **CI verification**: The build system runs the full ingest→query→answer pipeline WITH network access blocked; if it fails with the internet down, there's a leak
- **OS/app updates disabled**: No automatic checks that phone home

### 5. Credentials & Secrets

- Database credentials, API keys: stored in a secrets manager, never in code
- Environment variables: set per-deployment, not in `config.py`
- Git: `.gitignore` excludes `.env`, `.env.*`, `__pycache__`, etc.

### 6. Configuration Security

`config.py` and `prompts/` are:
- Version-controlled
- **Read-only at runtime** (the service doesn't modify them)
- Reviewed before deployment
- **Never user-writable** (the API doesn't have endpoints to modify config)

### How to Verify Air-Gap Compliance

1. **Monitor network traffic** (tcpdump, Wireshark):
   ```bash
   sudo tcpdump -i any 'tcp or udp' | grep -v "127.0.0.1"
   ```
   Should see only internal IPs or no external traffic if firewalled.

2. **Disable internet and test**:
   ```bash
   # Unplug network or set firewall to deny-all
   bash run.sh
   # Upload a PDF, ask a question
   # Should work fine offline
   ```

3. **Check model locations**:
   ```bash
   # Verify models are cached locally, not downloaded at runtime
   python -c "from transformers import AutoModel; AutoModel.from_pretrained('Qwen/Qwen3-Embedding-0.6B', local_files_only=True)"
   ```

---

## Using the System

### Web UI

1. Open `http://localhost:3000` in your browser
2. Click **"Upload PDF"** to add documents to the knowledge base
3. In the chat box, ask a question in German or English:
   - "Was ist die Kündigungsfrist?" (German)
   - "What is the notice period?" (English)
4. The system will:
   - Retrieve relevant passages
   - Rerank them
   - Generate an answer
   - Show source citations (click to view in the PDF)

### Language Selector

In the top-right corner, you can toggle which languages to search in:
- **German**: Always on (default)
- **English, French, etc.**: Click to enable additional language-specific BM25 searches

Enabling more languages makes searches more precise (lexical + semantic across languages).

### API Endpoints (for programmatic access)

#### Chat

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Was ist die Kündigungsfrist?",
    "active_lang_codes": ["de", "en"]
  }'
```

**Response:**

```json
{
  "answer": "Die Kündigungsfrist beträgt ein Monat zum Ende eines Kalendermonats.",
  "answer_lang": "de",
  "confidence": 0.72,
  "attempts": 1,
  "supporting_points": ["..."],
  "caveats": ["..."],
  "claims": [
    {
      "text": "Die Kündigungsfrist beträgt ein Monat zum Ende eines Kalendermonats.",
      "source": "contract.pdf § 5.2",
      "quote": "ein Monat zum Ende eines Kalendermonats",
      "verified": true
    }
  ],
  "artifact_chunks": [
    {
      "chunk_id": "abc123",
      "text": "Die Kündigungsfrist beträgt ein Monat zum Ende eines Kalendermonats.",
      "boxes": [{"page": 2, "rect": [0.1, 0.5, 0.9, 0.6]}],
      "address": {"doc_id": "contract.pdf", "section": "§ 5.2"},
      "source": "contract.pdf"
    }
  ]
}
```

#### Upload Document

```bash
curl -X POST http://localhost:8000/api/ingest \
  -F "file=@contract.pdf"
```

**Response:**

```json
{
  "job_id": "job-abc123",
  "status": "queued",
  "doc_id": "contract.pdf",
  "n_chunks": null
}
```

Poll the job status:

```bash
curl http://localhost:8000/api/ingest/job-abc123
```

#### Get Config

```bash
curl http://localhost:8000/api/config
```

**Response:**

```json
{
  "available_languages": ["de", "en", "fr"],
  "embed_model": "Qwen/Qwen3-Embedding-0.6B",
  "retrieve_k": 5,
  "reranker_top_k": 8
}
```

#### Serve Source PDF

```bash
# Fetch the original PDF by doc_id
curl http://localhost:8000/api/originals/contract.pdf > contract.pdf
```

---

## Advanced: How Each Component Works

### 1. Docling: Parsing Native PDFs

**What it does:** Reads a PDF, extracts text and tables, understands layout (headings, sections).

**Why this matters:** We parse native PDFs (with text layers), not scanned images. Docling's `TableFormer` model extracts table structure **deterministically** (no hallucination).

**How to use:**

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
doc = converter.convert("contract.pdf")  # DoclingDocument object

# Iterate the tree
for page in doc.pages:
    for block in page.blocks:
        if block.is_heading:
            print(f"Heading: {block.text}")
        elif block.is_table:
            print(f"Table with {len(block.table.rows)} rows")
        else:
            print(f"Prose: {block.text[:100]}...")
```

**Gotcha:** If a PDF has no extractable text layer (scanned/handwritten), we quarantine it now (no OCR yet). This is intentional—we flag it for the future OCR pipeline.

---

### 2. Structural Chunking: The Parent-Child Hierarchy

**What it does:** Converts the Docling tree into chunks that preserve semantics.

**Why this matters:**
- **Headings become parents**: carry the section context
- **Tables stay whole**: never split (tables > 512 tokens are embedded with a description, but the full table is still stored and returned)
- **Prose becomes leaves**: windowed by token count, not arbitrary split points

**Example:**

```
Document Tree:
  § 5. Termination
    | Parent (heading)
    |─ Table: Notice periods by role
    |  └─ Leaf (atomic, kept whole)
    |─ Paragraph: Procedure for termination
    |  └─ Leaf (prose, may be split)
    |─ Paragraph: Special cases
    |  └─ Leaf (prose, may be split)

Chunks (what gets stored):
  - chunk_0: heading "§ 5. Termination" (is_leaf=False, parent_id=None)
  - chunk_1: [Full table] (is_leaf=True, parent_id=chunk_0, chunk_type=table)
  - chunk_2: [Procedure para 1] (is_leaf=True, parent_id=chunk_0, chunk_type=prose)
  - chunk_3: [Procedure para 2] (is_leaf=True, parent_id=chunk_0, chunk_type=prose)
  - ... etc.
```

At retrieval time, if `chunk_2` scores high, we can **expand context** by prepending the parent heading ("§ 5. Termination") before embedding it into the LLM prompt. This gives the LLM full context without storing redundant copies.

---

### 3. Embedding: Dense + Sparse

**Dense (Qwen3-Embedding):**

```python
from src.common.embed import embed_query, embed_document

# At ingest time:
doc_vector = embed_document("Die Kündigungsfrist beträgt ein Monat.")
# Returns: numpy array shape (1024,) [for 0.6B/4B variant]

# At query time:
query_vector = embed_query("Kündigungsfrist?")
# Query instruction is prepended: "Instruct: Given a query, retrieve... Query: Kündigungsfrist?"
# Returns: same shape
```

**Sparse (BM25 with German Decompounding):**

For German queries, compound words are split:

```
"Kündigungsfrist"  →  ["Kündigung", "Frist"]
```

This is **crucial** for German documents: if a document says "Frist" but the user asks "Kündigungsfrist", a dumb tokenizer would miss it. Our tokenizer decomposes the compound.

```python
from src.common.sparse import tokenize_german, build_bm25

tokens = tokenize_german("Kündigungsfrist Monat")
# → ["kündig", "frist", "monat"]  (stemmed + decompounded)

# Build BM25 over the corpus (one per language)
# At index time: build_bm25(chunks, lang="de")
# At query time: bm25_de.retrieve(query_tokens, k=50)
```

---

### 4. Qdrant: Vector Database with Per-Language Sparse Indices

**Schema:**

```
Collection: rag_chunks

Point:
  - id: chunk_abc123
  - vector: [0.1, -0.05, ..., 0.3]  (dense, 1024 dims)
  - sparse_de: {100: 2.5, 102: 1.8, ...}  (BM25 term IDs + scores, German only)
  - sparse_en: {50: 1.2, 51: 0.9, ...}   (BM25 term IDs + scores, English only)
  - sparse_fr: {...}  (French, if language is available)
  - payload:
      - lang: "de"  or "en"
      - chunk_id: "abc123"
      - chunk_type: "prose" | "table" | "recommendation"
      - text: "Die Kündigungsfrist beträgt..."
      - parent_id: "heading_xyz"
      - boxes: [{page: 2, rect: [0.1, 0.5, 0.9, 0.6]}]
      - doc_id: "contract.pdf"
      - address: {section: "§ 5.2", chapter: "Termination"}
      - is_current: true
      - version_id: "v1"
```

**Retrieval (hybrid, multi-language):**

```python
from src.common.store import QdrantClient

# Dense search (cross-lingual)
dense_results = client.search_dense(
    query_vector=[...],
    limit=50
)

# BM25 German search
de_results = client.search_sparse(
    query="Kündigungsfrist Monat",
    sparse_field="sparse_de",
    limit=50
)

# BM25 English search (if language is active)
en_results = client.search_sparse(
    query="notice period month",
    sparse_field="sparse_en",
    limit=50
)

# Fuse with RRF
from src.query.graph.nodes import reciprocal_rank_fusion
fused = reciprocal_rank_fusion([dense_results, de_results, en_results])
# Returns top ~50 by combined RRF score
```

---

### 5. LangGraph: The Query State Machine

**State transitions:**

```python
# src/query/graph/state.py
class RAGState(TypedDict, total=False):
    # Input
    question: str
    active_lang_codes: list[str]
    
    # Computed
    query_lang: str  # detected
    answer_lang: str  # explicit > detected > default
    translated_queries: dict[str, str]  # cached
    
    # Retrieval results
    candidate_pool: list[dict]  # from retrieve node
    reranked: list[dict]  # from rerank node
    
    # Confidence
    confidence: float
    confidence_gap: float
    
    # Answer
    answer: str
    claims: list[dict]
    artifact_chunks: list[dict]  # for UI
    
    # Internals
    attempts: int
    escalation_reason: str
```

**Node implementations:**

- **prepare_query**: Detect language, set answer language, translate to active languages (cached)
- **retrieve**: Dense + BM25 per language, fuse with RRF, return deep pool
- **rerank**: Qwen3-Reranker scores each, top-k → state
- **score_confidence**: Compute confidence score + gap, decide action
- **escalate**: If low confidence, rewrite query and loop back to retrieve
- **answer**: Expand context, call LLM, verify quotes, build artifact_chunks
- **abstain**: Return "I can't ground this" message

---

### 6. Query Rewriting (Escalation Rung)

**When it triggers:** Low confidence + attempts < max_attempts → escalate → rewrite

**How it works:**

```python
from src.rewrite.rewriter import rewrite_query

# Original query
query = "Is this safe?"

# Rewriter has:
# - Per-language LLM few-shots (rewrite_fewshots_de.yaml)
# - Generic query rewrite prompt (prompts/rewrite_de.txt)
# - Optional domain dictionary (terms → formal equivalents)
# - Protected patterns (§, codes, numbers are never rewritten)

rewritten = rewrite_query(
    query,
    lang="de",
    use_dictionary=False,  # opt-in per corpus
    protected_patterns=[r"§\s*\d+", r"\b[A-Z]{1,3}-?\d+\b"]
)
# → "Erfüllt X die Anforderungen von § 5.2?"
```

The rewritten query feeds back into **retrieve** for another pass.

---

### 7. Citation Verification

**What it does:** Ensures every quoted claim is actually in the source document.

**How it works:**

```python
from src.common.citations import verify_quote

claim = {
    "text": "The notice period is one month.",
    "quote": "one month",
    "chunk_id": "abc123",
}

# Get the source chunk
source_text = "The notice period is one month to the end of the calendar month."

# Verify
verified = verify_quote(
    quote=claim["quote"],
    source=source_text,
    tolerance="whitespace_case"  # ignore case, normalize spaces
)
# Returns: True

# If the LLM hallucinated:
claim_2 = {
    "text": "The notice period is two weeks.",
    "quote": "two weeks",
    "chunk_id": "abc123",
}
verified_2 = verify_quote(claim_2["quote"], source_text)
# Returns: False → claim is flagged "verified=False" in the output
```

**Key point:** We don't delete unverified claims; we **flag** them as "unverified" so the user knows they're grounded in the LLM's reasoning, not the documents.

---

### 8. Multi-Language Handling (LanguageRegistry)

**How it's organized:**

```python
# config.py (conceptual; actual implementation in src/common/language.py)
AVAILABLE_LANGUAGES = [
    ("de", "German", german_analyzer),
    ("en", "English", english_analyzer),
    ("fr", "French", french_analyzer),
]

# At ingest time:
# - Create sparse_de, sparse_en, sparse_fr fields in Qdrant
# - For each chunk, detect language → populate only that language's sparse field

# At query time:
# - User selects active_languages: ["de", "en"]
# - prepare_query translates the question into DE and EN (cached)
# - retrieve runs:
#   - Dense (cross-lingual, no translation)
#   - BM25 German (search sparse_de using German tokens)
#   - BM25 English (search sparse_en using English tokens)
#   - Each BM25 pass uses the question *in that language*
```

**Key design:** Translation happens ONCE at query time, not at index time. This means:
1. Documents stay in their original language (no index-time mutation)
2. You can add languages without re-indexing (if the analyzer exists)
3. Queries translate to all active languages (with caching to avoid re-translation on escalation loops)

---

## Troubleshooting

### Models are downloading from HF Hub (not offline)

**Symptom:** You see network requests to `huggingface.co` in tcpdump.

**Cause:** Models aren't cached locally; `HF_HUB_OFFLINE=1` isn't working because models weren't pre-downloaded.

**Fix:**

1. Download models to cache:
   ```bash
   HF_HUB_OFFLINE=0 python -c "from transformers import AutoModel; AutoModel.from_pretrained('Qwen/Qwen3-Embedding-0.6B')"
   ```

2. Verify they're cached:
   ```bash
   ls ~/.cache/huggingface/hub/
   # Should see models-.../ directories
   ```

3. Restart with offline flags:
   ```bash
   export HF_HUB_OFFLINE=1
   bash run.sh
   ```

---

### "No such file or directory: Ollama"

**Symptom:** `run.sh` fails with "ollama: command not found" or hangs waiting for Ollama.

**Cause:** Ollama isn't installed or not in `PATH`.

**Fix:**

1. Install Ollama from `https://ollama.ai`
2. Verify it's available:
   ```bash
   which ollama
   ```

3. Pre-pull the model:
   ```bash
   ollama pull qwen3:8b
   ```

4. (Alternatively) Skip Ollama and use a remote vLLM server by setting `OLLAMA_BASE_URL` in `config.py` to point to your GPU server (not an external cloud; internal only).

---

### Low Confidence on Every Query

**Symptom:** Every answer gets `confidence < 0.55` and escalates multiple times.

**Causes:**

1. **Wrong language detected:** Check `query_lang` in the response. If it's wrong, add language hints to the query.
2. **Knowledge base is empty or doesn't match:** Upload more documents, or check the chat response for the actual documents retrieved.
3. **Thresholds are too strict:** Lower `CONFIDENCE_THRESHOLD` in `config.py` (default 0.55). On small corpora, try 0.45.
4. **Models are too weak:** Swap to a larger variant (e.g., Qwen3-Embedding-4B).

**Debug:**

1. Check what was retrieved:
   ```bash
   # Enable debug logging in the graph (if available)
   # Or inspect the ChatResponse.artifact_chunks to see what chunks were returned
   ```

2. Check the reranker score:
   - Open the browser's developer tools (F12)
   - Look at the network response for `/api/chat`
   - See `confidence` field

---

### "Qdrant connection refused"

**Symptom:** Backend crashes with `Connection refused` when starting.

**Cause:** Qdrant server isn't running.

**Fix:**

```bash
# Start Qdrant (it ships as a Docker container, but you can also run it locally)
docker run -p 6333:6333 qdrant/qdrant
# Or, if you installed it natively:
qdrant --storage-path ./qdrant_storage
```

Then restart the backend:

```bash
python -m src.api
```

---

### "Quote verification failed" on many claims

**Symptom:** Answers show `verified=False` for most claims.

**Causes:**

1. **LLM is paraphrasing:** The model rephrases the source instead of quoting verbatim. Reword the answer prompt in `prompts/answer_<lang>.txt`.
2. **Whitespace/case normalization too strict:** Check the `tolerance` parameter in `src/common/citations.py`.
3. **Source text differs from stored chunks:** Ensure chunks store the *exact* text (no post-processing).

**Debug:**

```bash
# Print a chunk's actual text
python -c "from src.common.store import QdrantClient; client = QdrantClient(); point = client.get('chunk_id'); print(point.payload['text'])"
```

Then manually check if the LLM's quote matches.

---

### "Rewrite query not working" during escalation

**Symptom:** Low confidence, escalation triggers, but the rewritten query doesn't improve results.

**Causes:**

1. **Rewrite is disabled:** Check `REWRITE["enabled"]` in `config.py`
2. **Few-shots are weak:** The examples in `rewrite_fewshots_<lang>.yaml` don't cover your domain. Add more examples.
3. **Protected patterns are too broad:** They prevent legitimate rewrites. Refine them in `config.py`.

**Debug:**

```bash
# Check what query is being rewritten to
# Enable debug logging in src/rewrite/rewriter.py or inspect the state
print(state.get("rewritten_query"))
```

---

### PDF Viewer Shows Blank or Wrong Page

**Symptom:** You click a source citation, the PDF loads, but the highlighted box is on the wrong page or invisible.

**Causes:**

1. **Bounding boxes weren't normalized:** Check the ingestion pipeline normalized boxes to 0..1 fractions (page-independent).
2. **PDF.js scale mismatch:** The viewer may render at a different DPI. Check `PdfViewer.tsx`.
3. **Pages were reordered in the PDF:** Docling's page numbers don't match human-visible page numbers (rare, but possible).

**Debug:**

```python
# Inspect a chunk's boxes
from src.common.store import QdrantClient
client = QdrantClient()
point = client.get("chunk_id")
print(point.payload["boxes"])
# Should be: [{"page": 1, "rect": [0.1, 0.2, 0.9, 0.8]}, ...]
# Fractions should be 0..1
```

---

## Next Steps

1. **Upload a sample PDF** (`samples/contract.pdf` if provided)
2. **Ask a question** in German or English
3. **Check the citation**: Click "Show source" to see the exact passage
4. **Inspect the logs** in `.logs/` if anything goes wrong
5. **Read CLAUDE.md** for the full architectural spec (this README summarizes; that spec is the source of truth)

---

## Architecture & Design References

- **Full Spec:** See [CLAUDE.md](CLAUDE.md) for the complete build order, security model, and feature roadmap
- **Query Rewrite:** See [Query_Rewrite Module_Implementation_Spec.md](Query_Rewrite%20Module_Implementation_Spec.md)
- **Structure Correction:** See [indexing_correction.md](indexing_correction.md)
- **Query Workflow:** See [query_wf.md](query_wf.md)
- **Retrieval Details:** See [retrival.md](retrival.md)

---

## Contributing / Extending

### Adding a New Language

1. Add to `AVAILABLE_LANGUAGES` in `config.py` with analyzer config
2. Add prompt files in `prompts/`:
   - `answer_<lang>.txt`
   - `abstain_<lang>.txt`
   - `rewrite_<lang>.txt`
3. (Optional) Add few-shots: `rewrite_data/rewrite_fewshots_<lang>.yaml`
4. Re-ingest documents (rebuilds sparse indices for new language)

### Swapping Models

All models are config values. To upgrade:

```python
# config.py
EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-4B"  # was 0.6B
# Pre-cache the model
# Re-ingest documents (rebuilds dense vectors)
```

### Custom Prompts

Edit `prompts/answer_<lang>.txt`, `prompts/rewrite_<lang>.txt`, etc. at runtime; changes apply immediately (no restart). Changes should respect the JSON contract (if the node expects JSON, keep it valid).

---

## License

[Your License Here]

---

**Questions?** Start with `CLAUDE.md`, then check the docs/ folder for detailed specs.
