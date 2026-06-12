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

# ── Tracing (self-hosted Langfuse only — never cloud LangSmith) ───────────
# Off by default. To enable: run scripts/start_langfuse.sh, then export
# LANGFUSE_ENABLED=true, LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
# (keys are local-instance credentials — kept in env, never in this file).
LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3001")

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

# ── Query rewrite (reactive escalation rung) ───────────────────────────────
# Closes the vocabulary gap between colloquial/spoken-register queries and the
# formal/written register of the document corpus. Document-agnostic mechanism
# in src/rewrite/rewriter.py — generic by default (works on any corpus):
#   - LLM rewrite uses generic per-language few-shots
#     (rewrite_data/rewrite_fewshots_<lang>.yaml) and prompts
#     (prompts/rewrite_<lang>.txt).
#   - The synonym DICTIONARY rung is opt-in per corpus: set use_dictionary=True
#     and point dictionary_path at a corpus-specific YAML
#     (term -> domain-term expansions) to add deterministic boosts on top.
# See "Query_Rewrite Module_Implementation_Spec.md".
REWRITE = {
    "enabled": True,
    "trigger": "reactive",          # only on low-confidence escalation
    "use_dictionary": False,        # opt-in per corpus (see dictionary_path)
    "use_llm": True,
    "use_hyde": False,              # enable per eval
    "use_multiquery": False,        # later rung, per eval
    "temperature": 0.1,
    "protected_patterns": [         # per corpus; generic engine
        r"§\s*\d+", r"\bAbs\.?\s*\d+", r"\b[A-Z]{1,3}-?\d+\b", r"\b\d+([.,]\d+)?\b",
    ],
    "dictionary_path": "rewrite_data/rewrite_dictionary.default.yaml",  # set per corpus when use_dictionary=True
    "domain_hint": "",              # optional one line per corpus
}

# ── Structure correction (pre/post-chunk, deterministic-first) ────────────
# Corrects Docling layout-derived structure before/after chunking. Mechanism is
# generic; all patterns/thresholds below are per-corpus (TV_L.pdf for the pilot).
# See "indexing_correction.md".
STRUCTURE = {
    "header": {
        "max_label_chars": 250,
        "max_label_words": 20,
        "label_suffixes": [":"],            # heading ending with these -> demote to prose
        "demote_single_stopword": True,
        "label_stopwords": ["nein", "ja"],  # single-word headings demoted if (punctuation-stripped) in this list
        "require_larger_font_than_body": True,  # not enforced yet — no per-item font info from Docling
        "flag_ambiguous_short_headers": True,  # step 6: flag short non-demoted headers for the LLM classifier
    },
    # Note: a bare "\d+(\.\d+)+" section-number pattern is intentionally NOT
    # included here — on TV_L.pdf it false-matches footnote dates (e.g.
    # "26.06.2001"). Add a more specific pattern (anchored to §/Art./Abs.
    # context) per corpus if/when a document uses numeric section numbering.
    "reference_patterns": [r"§\s*\d+(?:\s*Abs\.?\s*\d+)?", r"\bAbs\.?\s*\d+", r"\bArt\.\s*\d+"],
    "list_markers": [r"^[a-z]\)", r"^\d+\.", r"^[-–]\s*"],
    "min_prose_chars": 3,                # below this -> drop (prose only, tables exempt)
    "lang_inherit_max_chars": 15,        # below this -> inherit lang from previous leaf (langdetect unreliable)
    "tables_exempt_from_empty_filter": True,
    "use_llm_classifier": True,          # step 6: LLM classifier for ambiguous headers
    "xref_patterns": [r"siehe\s+§\s*\d+", r"vgl\.\s+§\s*\d+"],
}

# ── Vector store (Qdrant, local) ───────────────────────────────────────────
QDRANT_DIR = "database/qdrant"
QDRANT_COLLECTION = "rag_chunks"

# ── Originals store ────────────────────────────────────────────────────────
ORIGINALS_DIR = "documents"   # source PDFs stored here by doc_id

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
