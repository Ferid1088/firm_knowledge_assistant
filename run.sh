#!/usr/bin/env bash

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/.logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
OLLAMA_LOG="$LOG_DIR/ollama.log"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="3000"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

STARTED_PIDS=()
STARTED_NAMES=()
STARTED_LOGS=()
CLEANED_UP=0

blue="\033[1;34m"
yellow="\033[1;33m"
red="\033[1;31m"
green="\033[1;32m"
reset="\033[0m"

info() {
  printf "%b==>%b %s\n" "$blue" "$reset" "$*"
}

success() {
  printf "%b✔%b %s\n" "$green" "$reset" "$*"
}

warn() {
  printf "%b!%b %s\n" "$yellow" "$reset" "$*"
}

error() {
  printf "%b✖%b %s\n" "$red" "$reset" "$*" >&2
}

die() {
  error "$*"
  exit 1
}

cleanup() {
  if [ "$CLEANED_UP" -eq 1 ]; then
    return
  fi
  CLEANED_UP=1

  if [ "${#STARTED_PIDS[@]}" -eq 0 ]; then
    return
  fi

  info "Stopping services started by this script..."

  local idx pid name
  for ((idx=${#STARTED_PIDS[@]}-1; idx>=0; idx--)); do
    pid="${STARTED_PIDS[$idx]}"
    name="${STARTED_NAMES[$idx]}"

    if kill -0 "$pid" 2>/dev/null; then
      warn "Stopping ${name} (pid ${pid})"
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
  done
}

trap cleanup EXIT INT TERM

require_cmd() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "Missing command '$cmd'. ${hint}"
  fi
}

load_optional_env_files() {
  local env_file
  local env_files=(
    "$ROOT_DIR/.env"
    "$ROOT_DIR/.env.local"
    "$ROOT_DIR/.env.langfuse"
    "$ROOT_DIR/.env.langfuse.local"
  )

  for env_file in "${env_files[@]}"; do
    if [ -f "$env_file" ]; then
      info "Loading environment from $(basename "$env_file") ..."
      set -a
      # shellcheck disable=SC1090
      source "$env_file"
      set +a
    fi
  done

  if [ "${LANGFUSE_ENABLED:-false}" = "true" ]; then
    if [ -z "${LANGFUSE_PUBLIC_KEY:-}" ] || [ -z "${LANGFUSE_SECRET_KEY:-}" ]; then
      warn "LANGFUSE_ENABLED=true but Langfuse keys are missing. Backend will start without tracing callbacks."
    else
      success "Langfuse tracing env detected for ${LANGFUSE_HOST:-http://localhost:3001}"
    fi
  else
    warn "Langfuse tracing is disabled. Export LANGFUSE_ENABLED=true (and keys) before starting, or place them in .env.langfuse."
  fi
}

http_ready() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local timeout="${3:-60}"
  local elapsed=0

  while [ "$elapsed" -lt "$timeout" ]; do
    if http_ready "$url"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  return 1
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

register_process() {
  local name="$1"
  local pid="$2"
  local log_path="$3"
  STARTED_PIDS+=("$pid")
  STARTED_NAMES+=("$name")
  STARTED_LOGS+=("$log_path")
}

start_background() {
  local name="$1"
  local log_path="$2"
  local command_str="$3"

  info "Starting ${name}..."
  bash -lc "$command_str" >>"$log_path" 2>&1 &
  local pid=$!
  register_process "$name" "$pid" "$log_path"
  success "${name} started (pid ${pid})"
}

ensure_python_env() {
  if [ ! -d "$ROOT_DIR/.venv" ]; then
    info "Creating Python virtual environment in .venv ..."
    python3 -m venv "$ROOT_DIR/.venv" || die "Failed to create .venv"
  fi

  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"

  if ! python - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import langgraph
import qdrant_client
import ollama
PY
  then
    info "Installing backend dependencies from requirements.txt ..."
    python -m pip install -r "$ROOT_DIR/requirements.txt" || die "Backend dependency installation failed"
  fi
}

ensure_frontend_deps() {
  if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
    info "Installing frontend dependencies with npm ..."
    (
      cd "$ROOT_DIR/frontend"
      npm install --no-fund --no-audit
    ) || die "Frontend dependency installation failed"
  fi
}

load_config() {
  local cfg
  cfg="$((cd "$ROOT_DIR" && python3 - <<'PY'
from config import OLLAMA_MODEL, OLLAMA_BASE_URL, EMBED_MODEL_ID, RERANKER_MODEL_ID
print(OLLAMA_MODEL)
print(OLLAMA_BASE_URL)
print(EMBED_MODEL_ID)
print(RERANKER_MODEL_ID)
PY
))" || true
}

read_config_values() {
  local cfg
  cfg="$(cd "$ROOT_DIR" && python3 - <<'PY'
from config import OLLAMA_MODEL, OLLAMA_BASE_URL, EMBED_MODEL_ID, RERANKER_MODEL_ID
print(OLLAMA_MODEL)
print(OLLAMA_BASE_URL)
print(EMBED_MODEL_ID)
print(RERANKER_MODEL_ID)
PY
)" || die "Unable to read local model settings from config.py"

  OLLAMA_MODEL="$(printf '%s\n' "$cfg" | sed -n '1p')"
  OLLAMA_BASE_URL="$(printf '%s\n' "$cfg" | sed -n '2p')"
  EMBED_MODEL_ID="$(printf '%s\n' "$cfg" | sed -n '3p')"
  RERANKER_MODEL_ID="$(printf '%s\n' "$cfg" | sed -n '4p')"
  OLLAMA_TAGS_URL="${OLLAMA_BASE_URL%/}/api/tags"
}

ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama is not installed. The UI and API can start, but answering will fail until Ollama is available."
    return 0
  fi

  if http_ready "$OLLAMA_TAGS_URL"; then
    success "Ollama is already running at ${OLLAMA_BASE_URL}"
  else
    if port_in_use 11434; then
      warn "Port 11434 is in use, but Ollama did not answer at ${OLLAMA_TAGS_URL}."
    else
      start_background "ollama" "$OLLAMA_LOG" "exec ollama serve"
      if wait_for_http "Ollama" "$OLLAMA_TAGS_URL" 20; then
        success "Ollama is ready at ${OLLAMA_BASE_URL}"
      else
        warn "Ollama did not become ready within 20s. Check ${OLLAMA_LOG}."
      fi
    fi
  fi

  if command -v ollama >/dev/null 2>&1; then
    if ! ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
      warn "Configured Ollama model '${OLLAMA_MODEL}' is not available locally. Run: ollama pull ${OLLAMA_MODEL}"
    else
      success "Configured Ollama model found: ${OLLAMA_MODEL}"
    fi
  fi
}

start_backend() {
  local health_url="${BACKEND_URL}/api/config"

  if http_ready "$health_url"; then
    success "Backend already running at ${BACKEND_URL}"
    return 0
  fi

  if port_in_use "$BACKEND_PORT"; then
    die "Port ${BACKEND_PORT} is already in use, but the backend health check failed. Free the port or stop the conflicting service."
  fi

  start_background \
    "backend" \
    "$BACKEND_LOG" \
    "cd \"$ROOT_DIR\" && source \"$ROOT_DIR/.venv/bin/activate\" && exec python -m uvicorn src.api:app --host $BACKEND_HOST --port $BACKEND_PORT"

  if wait_for_http "backend" "$health_url" 30; then
    success "Backend is ready at ${BACKEND_URL}"
  else
    die "Backend failed to start. Check ${BACKEND_LOG}"
  fi
}

start_frontend() {
  local health_url="http://${FRONTEND_HOST}:${FRONTEND_PORT}"

  if http_ready "$health_url"; then
    success "Frontend already running at ${FRONTEND_URL}"
    return 0
  fi

  if port_in_use "$FRONTEND_PORT"; then
    die "Port ${FRONTEND_PORT} is already in use, but the frontend health check failed. Free the port or stop the conflicting service."
  fi

  start_background \
    "frontend" \
    "$FRONTEND_LOG" \
    "cd \"$ROOT_DIR/frontend\" && exec npm run dev -- --hostname $FRONTEND_HOST --port $FRONTEND_PORT"

  if wait_for_http "frontend" "$health_url" 60; then
    success "Frontend is ready at ${FRONTEND_URL}"
  else
    die "Frontend failed to start. Check ${FRONTEND_LOG}"
  fi
}

monitor_started_processes() {
  if [ "${#STARTED_PIDS[@]}" -eq 0 ]; then
    return 0
  fi

  info "Press Ctrl+C to stop the services started by this script."

  while true; do
    sleep 2

    local idx pid name log_path
    for idx in "${!STARTED_PIDS[@]}"; do
      pid="${STARTED_PIDS[$idx]}"
      name="${STARTED_NAMES[$idx]}"
      log_path="${STARTED_LOGS[$idx]}"

      if ! kill -0 "$pid" 2>/dev/null; then
        die "${name} exited unexpectedly. Check ${log_path}"
      fi
    done
  done
}

main() {
  mkdir -p "$LOG_DIR"

  require_cmd python3 "Install Python 3 first."
  require_cmd npm "Install Node.js + npm first."
  require_cmd curl "Install curl first."

  load_optional_env_files
  read_config_values

  info "Preparing local environment ..."
  ensure_python_env
  ensure_frontend_deps

  warn "config.py enables offline Hugging Face mode. Make sure these models are already cached locally:"
  printf "    - %s\n" "$EMBED_MODEL_ID"
  printf "    - %s\n" "$RERANKER_MODEL_ID"

  ensure_ollama
  start_backend
  start_frontend

  printf "\n"
  success "Local RAG is running"
  printf "    Frontend: %s\n" "$FRONTEND_URL"
  printf "    Backend:  %s\n" "$BACKEND_URL"
  printf "    Ollama:   %s\n" "$OLLAMA_BASE_URL"
  printf "    Logs:     %s\n" "$LOG_DIR"
  printf "\n"
  warn "If answering fails, first check Ollama and the locally cached embedding/reranker models."

  monitor_started_processes
}

main "$@"