# Local RAG Pilot

Local RAG over native PDFs with text + tables. See CLAUDE.md for the full spec
and build order.

Quick start: put a test PDF in `samples/`, create a venv, install
requirements.txt, then follow CLAUDE.md's build order starting at step 0.

## One-command local startup

From the project root, run:

```bash
bash run.sh
```

The launcher will:
- check Python / npm / curl
- create `.venv` if missing
- install backend dependencies if needed
- install frontend dependencies if needed
- try to start Ollama if available locally
- start the FastAPI backend on `127.0.0.1:8000`
- start the Next.js frontend on `http://localhost:3000`

Logs are written to `.logs/`.
