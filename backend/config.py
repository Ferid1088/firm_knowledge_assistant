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
ENABLE_EMBED_ENRICHMENT = True   # LLM descriptions for oversize tables + figures at ingest

# ── Vector store (Qdrant, local) ───────────────────────────────────────────
QDRANT_DIR = "database/qdrant"
QDRANT_COLLECTION = "rag_chunks"

# ── Originals store ────────────────────────────────────────────────────────
ORIGINALS_DIR = "raw_knowlegebase"   # source PDFs stored here by doc_id

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

# ── Multi-user persistence (SQLite, local) ───────────────────────────────────
DATABASE_PATH = "database/app.db"

# ── Local key material (Vault / RSA-PKI substitutes — see security.py) ──────
# Both files are generated on first run and stored 0600; never committed
# (covered by the /database/ gitignore entry).
MASTER_KEY_PATH = "database/keys/master.key"           # AES-256-GCM key-wrapping key
SIGNING_KEY_PATH = "database/keys/signing_ed25519.pem"  # message-integrity signing key

# ── IAM: tenant / departments / users ───────────────────────────────────────
# Single-tenant pilot — kept as a field for forward compatibility with the
# multi-tenant spec, never exposed in the UI.
DEFAULT_TENANT_ID = "default"

# Seed data inserted (idempotently) on startup. Real user/department management
# would replace this list with an admin API/UI; for the pilot this is the only
# place "who exists" is configured (config-driven, per CLAUDE.md).
SEED_DEPARTMENTS = [
    # (id, name, code)
    ("dept-hr",   "HR",         "HR"),
    ("dept-mgmt", "Management", "MGMT"),
    ("dept-mkt",  "Marketing",  "MKT"),
    ("dept-tech", "Technical",  "TECH"),
]

SEED_USERS = []  # Users created via scripts/setup.py, not seeded

# Document types seeded idempotently on startup (id, name, description).
# Admins can add more via the Admin → Doc Types tab; these are the defaults.
SEED_DOC_TYPES = [
    ("dt-norm",     "Norm / Regulation",   "DIN, ISO, legal regulations, standards"),
    ("dt-contract", "Contract",            "Legal contracts, agreements, clauses"),
    ("dt-manual",   "Technical Manual",    "Operating manuals, datasheets, drawings"),
    ("dt-hr",       "HR Document",         "Policies, guidelines, employment docs"),
    ("dt-report",   "Report / Protocol",   "Meeting minutes, audit reports, analyses"),
    ("dt-email",    "Email / Correspondence", "Emails, mailbox exports, letters"),
    ("dt-other",    "Other",               "General documents not covered above"),
]

# ── Sessions (Redis substitute: SQLite-backed, TTL-checked on access) ───────
SESSION_TTL_SECONDS = 3600  # 1 hour, per spec

# ── Rate limiting (Redis substitute: SQLite counters) ───────────────────────
RATE_LIMIT_MSGS_PER_HOUR = 50
RATE_LIMIT_CONVERSATIONS_PER_DAY = 10
# Retrievals-per-message cap (spec: 5) maps onto the existing escalation loop:
# each escalate->retrieve hop is one retrieval, bounded by MAX_ATTEMPTS above.

# ── Conversation context window ──────────────────────────────────────────────
MAX_CONTEXT_TOKENS = 4096  # history token budget for ConversationContext

# ── Observability (Langfuse, self-hosted only — CLAUDE.md: never cloud) ─────
# Values read from .env.langfuse at startup; defaults keep tracing OFF if the
# file is absent (safe for air-gapped deployments without Langfuse running).
def _env_bool(key: str, default: bool = False) -> bool:
    """Read an environment variable as a boolean ('1', 'true', or 'yes' → True)."""
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")

LANGFUSE_ENABLED  = _env_bool("LANGFUSE_ENABLED", False)
LANGFUSE_HOST     = os.environ.get("LANGFUSE_HOST",       "http://localhost:3001")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

# ── Response cache (SQLite-backed, local only) ────────────────────────────
# Identical queries (same question + conversation + user + lang filters) are
# served from cache without running the full RAG pipeline.
CACHE_ENABLED        = True
CACHE_TTL_SECONDS    = 3600   # seconds until a cached entry expires; 0 = no expiry
CACHE_MAX_ENTRIES    = 500    # LRU eviction kicks in above this count
CACHE_MIN_CONFIDENCE = 0.55   # only cache answers at or above this confidence score
