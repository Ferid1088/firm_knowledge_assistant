# ── Local RAG — Developer Entry Points ────────────────────────────────────────
# Usage:
#   make dev        start backend + frontend (foreground logs, Ctrl-C stops both)
#   make backend    start backend only
#   make frontend   start frontend only
#   make stop       kill both services
#   make logs       tail combined logs
#   make status     show whether backend / frontend are running
#   make install    install Python deps + Node deps
#   make test       run the pytest test suite

SHELL        := /bin/bash
PROJECT_ROOT := $(shell pwd)
VENV         := $(PROJECT_ROOT)/.venv
PYTHON       := $(VENV)/bin/python
UVICORN      := $(VENV)/bin/uvicorn
LOGS_DIR     := $(PROJECT_ROOT)/.logs

BACKEND_HOST  := 127.0.0.1
BACKEND_PORT  := 8000
FRONTEND_DIR  := $(PROJECT_ROOT)/frontend
BACKEND_PID   := $(LOGS_DIR)/backend.pid
FRONTEND_PID  := $(LOGS_DIR)/frontend.pid
BACKEND_LOG   := $(LOGS_DIR)/backend.log
FRONTEND_LOG  := $(LOGS_DIR)/frontend.log

.PHONY: dev backend frontend stop logs status install test

# ── dev: start both, stream combined logs to terminal ─────────────────────────
dev: _ensure-logs _start-backend _start-frontend
	@echo ""
	@echo "  Backend  → http://$(BACKEND_HOST):$(BACKEND_PORT)"
	@echo "  Frontend → http://localhost:3000"
	@echo "  Logs     → $(LOGS_DIR)/"
	@echo ""
	@echo "  Press Ctrl-C to stop both services."
	@echo ""
	@trap 'make stop' INT TERM; tail -f $(BACKEND_LOG) $(FRONTEND_LOG)

# ── individual services ────────────────────────────────────────────────────────
backend: _ensure-logs _start-backend
	@echo "Backend running on http://$(BACKEND_HOST):$(BACKEND_PORT) — logs: $(BACKEND_LOG)"

frontend: _ensure-logs _start-frontend
	@echo "Frontend running on http://localhost:3000 — logs: $(FRONTEND_LOG)"

# ── stop both ─────────────────────────────────────────────────────────────────
stop:
	@if [ -f $(BACKEND_PID) ]; then \
	  PID=$$(cat $(BACKEND_PID)); \
	  kill $$PID 2>/dev/null && echo "Backend stopped (pid $$PID)" || echo "Backend already stopped"; \
	  rm -f $(BACKEND_PID); \
	fi
	@if [ -f $(FRONTEND_PID) ]; then \
	  PID=$$(cat $(FRONTEND_PID)); \
	  kill $$PID 2>/dev/null && echo "Frontend stopped (pid $$PID)" || echo "Frontend already stopped"; \
	  rm -f $(FRONTEND_PID); \
	fi

# ── logs ──────────────────────────────────────────────────────────────────────
logs: _ensure-logs
	@tail -f $(BACKEND_LOG) $(FRONTEND_LOG)

# ── status ────────────────────────────────────────────────────────────────────
status:
	@echo "Backend:"
	@if [ -f $(BACKEND_PID) ] && kill -0 $$(cat $(BACKEND_PID)) 2>/dev/null; then \
	  echo "  running  (pid $$(cat $(BACKEND_PID)))  http://$(BACKEND_HOST):$(BACKEND_PORT)"; \
	else \
	  echo "  stopped"; \
	fi
	@echo "Frontend:"
	@if [ -f $(FRONTEND_PID) ] && kill -0 $$(cat $(FRONTEND_PID)) 2>/dev/null; then \
	  echo "  running  (pid $$(cat $(FRONTEND_PID)))  http://localhost:3000"; \
	else \
	  echo "  stopped"; \
	fi

# ── install ───────────────────────────────────────────────────────────────────
install:
	@echo "Installing Python dependencies..."
	uv pip install -r requirements.txt -q
	@echo "Installing Node dependencies..."
	cd $(FRONTEND_DIR) && npm install
	@echo "Done."

# ── test ──────────────────────────────────────────────────────────────────────
test:
	$(PYTHON) -m pytest tests/ -v

# ── internal helpers ──────────────────────────────────────────────────────────
_ensure-logs:
	@mkdir -p $(LOGS_DIR)

_start-backend:
	@if [ -f $(BACKEND_PID) ] && kill -0 $$(cat $(BACKEND_PID)) 2>/dev/null; then \
	  echo "Backend already running (pid $$(cat $(BACKEND_PID)))"; \
	else \
	  cd $(PROJECT_ROOT) && \
	  $(UVICORN) backend.api.main:app \
	    --host $(BACKEND_HOST) \
	    --port $(BACKEND_PORT) \
	    --reload \
	    > $(BACKEND_LOG) 2>&1 & \
	  echo $$! > $(BACKEND_PID); \
	  echo "Backend started (pid $$(cat $(BACKEND_PID)))"; \
	fi

_start-frontend:
	@if [ -f $(FRONTEND_PID) ] && kill -0 $$(cat $(FRONTEND_PID)) 2>/dev/null; then \
	  echo "Frontend already running (pid $$(cat $(FRONTEND_PID)))"; \
	else \
	  cd $(FRONTEND_DIR) && \
	  npm run dev \
	    > $(FRONTEND_LOG) 2>&1 & \
	  echo $$! > $(FRONTEND_PID); \
	  echo "Frontend started (pid $$(cat $(FRONTEND_PID)))"; \
	fi
