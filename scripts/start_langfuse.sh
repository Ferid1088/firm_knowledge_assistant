#!/usr/bin/env bash
# ── Self-hosted Langfuse (local-only tracing for the LangGraph pipeline) ───
# Spins up Langfuse v2 + Postgres via Docker Compose. Everything stays on
# localhost — no external network calls. Safe for the air-gapped pilot.
#
# Usage:
#   ./scripts/start_langfuse.sh up      # start (default)
#   ./scripts/start_langfuse.sh down    # stop
#   ./scripts/start_langfuse.sh logs    # tail logs
#
# After it's up, open http://localhost:3001, create a local account/project,
# and copy the generated Public/Secret keys into your shell env:
#   export LANGFUSE_ENABLED=true
#   export LANGFUSE_HOST=http://localhost:3001
#   export LANGFUSE_PUBLIC_KEY=pk-lf-...
#   export LANGFUSE_SECRET_KEY=sk-lf-...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR/.langfuse"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
ACTION="${1:-up}"

mkdir -p "$COMPOSE_DIR"

cat > "$COMPOSE_FILE" <<'EOF'
services:
  langfuse-db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - langfuse_db_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5433:5432"

  langfuse:
    image: langfuse/langfuse:2
    restart: unless-stopped
    depends_on:
      - langfuse-db
    ports:
      - "127.0.0.1:3001:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: local-dev-secret-change-me
      NEXTAUTH_URL: http://localhost:3001
      SALT: local-dev-salt-change-me
      TELEMETRY_ENABLED: "false"
      NEXT_PUBLIC_SIGN_UP_DISABLED: "false"

volumes:
  langfuse_db_data:
EOF

case "$ACTION" in
  up)
    docker compose -f "$COMPOSE_FILE" up -d
    echo ""
    echo "Langfuse starting at http://localhost:3001"
    echo "Create a local account + project there, then export:"
    echo "  export LANGFUSE_ENABLED=true"
    echo "  export LANGFUSE_HOST=http://localhost:3001"
    echo "  export LANGFUSE_PUBLIC_KEY=pk-lf-..."
    echo "  export LANGFUSE_SECRET_KEY=sk-lf-..."
    ;;
  down)
    docker compose -f "$COMPOSE_FILE" down
    ;;
  logs)
    docker compose -f "$COMPOSE_FILE" logs -f
    ;;
  *)
    echo "Usage: $0 {up|down|logs}" >&2
    exit 1
    ;;
esac
