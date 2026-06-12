# Firm Knowledge Assistant — Local RAG

**A commercial-grade, air-gapped local RAG system** for enterprise knowledge bases. Ingest native PDFs, ask questions, get answers with verified source citations—all without any data leaving your network.

## Quick Start (One Command)

```bash
bash run.sh
```

This starts:
- FastAPI backend on `http://127.0.0.1:8000`
- Next.js frontend on `http://localhost:3000`
- Qdrant vector database (local)
- Ollama LLM (if available)

Then open your browser to **`http://localhost:3000`**, upload a PDF, and ask questions.

## What This System Does

- **Parses PDFs locally** → Extract text, tables, and structure with Docling
- **Indexes documents** → Embed with Qwen3 + BM25 sparse search (German decompounding)
- **Retrieves multilingual** → Dense + per-language BM25, fused with RRF
- **Answers with citations** → Local LLM with quote verification
- **Shows sources** → Click to jump to the exact passage in the PDF
- **Works offline** → No cloud APIs, completely air-gapped

## Documentation

- **[README_DETAILED.md](README_DETAILED.md)** ← **START HERE** for a full walkthrough of how the system works, with examples
- [CLAUDE.md](CLAUDE.md) — Full architectural spec and build order (for developers)
- [Query_Rewrite Module_Implementation_Spec.md](Query_Rewrite%20Module_Implementation_Spec.md) — Query rewriting details
- [indexing_correction.md](indexing_correction.md) — Document structure correction
- [query_wf.md](query_wf.md) — Query pipeline workflow
- [retrival.md](retrival.md) — Retrieval mechanics

## Key Technologies

| Component | Purpose |
|-----------|---------|
| **Docling** | Native PDF parsing (text + tables) |
| **Qwen3-Embedding** | Dense semantic search (0.6B/4B/8B) |
| **Qdrant** | Vector database (self-hosted, local) |
| **LangGraph** | Query orchestration (state machine) |
| **Qwen3-Reranker** | Ranking candidates (0.6B) |
| **Ollama / vLLM** | Local LLM for answering |
| **Next.js + assistant-ui** | Web UI (responsive, PWA-ready) |

## Installation

### Requirements
- Python 3.10+
- Node.js 18+
- Ollama (optional, for local LLM)
- ~16 GB RAM (M1 Pro for pilot; GPU server for production)

### Setup
```bash
# One-command setup
bash run.sh

# Or manually
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install
```

## Configuration

All settings are in **`config.py`** at the project root:

```python
# Models (swap here for different versions)
EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"  # change to 4B/8B
RERANKER_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
OLLAMA_MODEL = "qwen3:8b"

# Retrieval
RETRIEVE_K = 5  # top-5 chunks to answer node
RETRIEVE_DEEP_POOL = 50  # deep pool for reranker
CONFIDENCE_THRESHOLD = 0.55  # escalate if below
MAX_ATTEMPTS = 3  # hard cap on retries

# Features
ENABLE_TRANSLATED_BM25 = True  # search per language
ENABLE_SIBLING_EXPANSION = False  # add adjacent chunks
ENABLE_HYDE = False  # hypothetical docs (deferred)
```

## Usage

### Web Interface

1. Open `http://localhost:3000`
2. Upload a PDF
3. Ask a question (German or English):
   - "Was ist die Kündigungsfrist?" (German)
   - "What is the notice period?" (English)
4. View the answer and click citations to see source

### API

```bash
# Ask a question
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Was ist die Kündigungsfrist?", "active_lang_codes": ["de", "en"]}'

# Upload a document
curl -X POST http://localhost:8000/api/ingest \
  -F "file=@contract.pdf"

# Get configuration
curl http://localhost:8000/api/config
```

## Security & Air-Gap

This system is **completely offline**:

- ✅ No cloud APIs (no OpenAI, DeepL, HuggingFace endpoints)
- ✅ All models cached locally, offline mode enforced
- ✅ No telemetry or observability leaks (LangSmith off, Langfuse self-hosted)
- ✅ No external assets (fonts, CDNs, analytics)
- ✅ Credentials in env vars, never in code
- ✅ Firewall-verifiable (default-deny egress)

See [README_DETAILED.md § Security](README_DETAILED.md#security--air-gap-design) for full details.

## Architecture Diagram

```
Browser (http://localhost:3000)
    ↓
FastAPI Backend (api.py)
    ├─ /api/chat → LangGraph query engine
    ├─ /api/ingest → Ingest pipeline
    └─ /api/originals → Serve source PDFs
    
Behind the scenes:
  Docling (parse) → Chunking → Embedding
  Dense + BM25 → Qdrant → Retrieve + Rerank
  → Confidence scoring → Escalation loop (if needed)
  → LLM answer + quote verification
```

## Troubleshooting

**Models downloading from HuggingFace?**
- Models must be cached locally first
- Run: `python -c "from transformers import AutoModel; AutoModel.from_pretrained('Qwen/Qwen3-Embedding-0.6B')"`
- Then set `HF_HUB_OFFLINE=1` and restart

**Ollama not found?**
- Install from https://ollama.ai
- Pull model: `ollama pull qwen3:8b`
- Or use a remote vLLM server (point `OLLAMA_BASE_URL` to internal GPU server)

**Low confidence on every query?**
- Check retrieved documents (see `artifact_chunks` in response)
- Lower `CONFIDENCE_THRESHOLD` in config.py
- Upload more relevant documents

**Qdrant connection refused?**
- Start Qdrant: `docker run -p 6333:6333 qdrant/qdrant`
- Or: `qdrant --storage-path ./qdrant_storage`

See [README_DETAILED.md § Troubleshooting](README_DETAILED.md#troubleshooting) for more.

## Directory Structure

```
/
├── README.md (this file)
├── README_DETAILED.md ← Full walkthrough (READ THIS)
├── CLAUDE.md ← Full spec for developers
├── config.py ← Configuration (EDIT THIS)
├── requirements.txt ← Python dependencies
├── run.sh ← One-command launcher
│
├── src/ ← Backend (Python)
├── frontend/ ← Frontend (Next.js/TypeScript)
├── prompts/ ← Language-specific prompt templates
├── eval/ ← Evaluation harness
├── docs/ ← Design docs
└── originals/ ← PDF storage
```

## Next Steps

1. **Read [README_DETAILED.md](README_DETAILED.md)** for a complete explanation of how the agent works
2. Upload a sample PDF
3. Ask a question
4. Check [CLAUDE.md](CLAUDE.md) for the full architectural spec and build order

## License

[Your License]

---

**Questions?** Start with [README_DETAILED.md](README_DETAILED.md) — it has examples, troubleshooting, and detailed explanations of every component.
