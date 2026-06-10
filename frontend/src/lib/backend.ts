// FastAPI backend (src/api.py). Internal-only, same machine on the pilot.
// Server-side only — never exposed to the browser bundle (no NEXT_PUBLIC_ prefix).
export const BACKEND_ORIGIN = process.env.RAG_API_ORIGIN ?? "http://127.0.0.1:8000";
