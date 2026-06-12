"""GET /api/config — expose UI-relevant configuration."""
from fastapi import APIRouter

from backend.config import AVAILABLE_LANGUAGES, OLLAMA_MODEL, RETRIEVE_K, RERANKER_TOP_K

router = APIRouter()


@router.get("/config")
def get_config():
    return {
        "available_languages": [code for code, *_ in AVAILABLE_LANGUAGES],
        "default_active_languages": [code for code, *_ in AVAILABLE_LANGUAGES],
        "ollama_model": OLLAMA_MODEL,
        "top_k": max(RETRIEVE_K, RERANKER_TOP_K),
    }
