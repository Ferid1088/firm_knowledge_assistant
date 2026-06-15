# ── Local RAG — Central Configuration ─────────────────────────────────────
# ONE place controls all behavior. Code reads this; nothing is hardcoded elsewhere.
# Keep this file under version control; never make it writable by the running service.

import os

# ── Offline / security flags ───────────────────────────────────────────────
# Set BEFORE any HuggingFace import. Models must already be cached locally.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

# ── Embedding model ────────────────────────────────────────────────────────
# Pilot: 0.6B fits on 16 GB M1. Production: swap to 4B/8B here only.
EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EMBED_DIM = 1024          # output dimension for 0.6B and 4B
EMBED_MAX_SEQ = 2048      # CPU-practical cap for the pilot (full 8192 needs GPU)
# Instruction prefix applied to QUERIES ONLY (not documents at index time)
EMBED_QUERY_INSTRUCTION = "Instruct: Given a query, retrieve the most relevant document passage.\nQuery: "

# ── Reranker ───────────────────────────────────────────────────────────────
RERANKER_MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
RERANKER_TOP_K = 8        # re-rank this many candidates -> return top RETRIEVE_K

# ── Chunking ───────────────────────────────────────────────────────────────
CHUNK_MAX_TOKENS = 512    # prose windowing only; atomic leaves (table/rec) kept whole
OVERSIZE_EMBED_THRESHOLD = 400  # tokens; leaves above this get a contextual description embedded

# ── Answering LLM (Ollama) ─────────────────────────────────────────────────
# Pilot: Ollama. Production: swap to vLLM base_url here only.
OLLAMA_MODEL = "qwen3:8b"
OLLAMA_BASE_URL = "http://localhost:11434"  # never a cloud URL
OLLAMA_TEMPERATURE = 0

# ── Retrieval ──────────────────────────────────────────────────────────────
RETRIEVE_K = 5            # final top-k returned to the answer node
RETRIEVE_DEEP_POOL = 50   # deep pool sent to reranker
MAX_ATTEMPTS = 3          # escalation loop hard cap
CONFIDENCE_THRESHOLD = 0.55   # top-1 score below this -> escalate
CONFIDENCE_GAP_MIN = 0.05     # gap(top1 - top2) below this adds uncertainty

# ── Feature flags ──────────────────────────────────────────────────────────
ENABLE_TRANSLATED_BM25 = True   # run BM25 pass per active language (not just DE)
ENABLE_SIBLING_EXPANSION = False # ±1 sibling context (OFF until eval shows lift)
ENABLE_HYDE = False              # deferred to GPU server

# ── Vector store (Qdrant, local) ───────────────────────────────────────────
QDRANT_DIR = ".qdrant"
QDRANT_COLLECTION = "rag_chunks"

# ── Originals store ────────────────────────────────────────────────────────
ORIGINALS_DIR = "originals"   # source PDFs stored here by doc_id

# ── Language registry ──────────────────────────────────────────────────────
# AVAILABLE_LANGUAGES: languages whose analyzer + sparse field exist at ingestion time.
# German is always ON. Others are opt-in at query time (must exist at ingestion).
# Each entry: (code, decompound, sparse_field, prompt_key)
AVAILABLE_LANGUAGES = [
    # code    decompound  sparse_field   prompt_key
    ("de",    True,       "sparse_de",   "de"),   # German — always active
    ("en",    False,      "sparse_en",   "en"),   # English
]

# Default language for answers when none can be detected
DEFAULT_ANSWER_LANG = "de"
