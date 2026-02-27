#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# launcher.sh — One-command startup for the Intelligent Assistant Platform
#
# Starts:
#   1. FastAPI backend   (uvicorn, port 8000)
#   2. Vite dev server   (npm run dev, port 5173)
#   3. Opens the browser automatically
#
# Usage:
#   ./launcher.sh            # start everything
#   ./launcher.sh --no-open  # start without opening browser
#
# Requirements:
#   • Python 3.12+ with uvicorn, fastapi, etc. installed
#   • Node.js / npm in PATH
#   • .env file in project root with API keys
#
# All processes are killed on Ctrl+C via trap.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

OPEN_BROWSER=true
[[ "${1:-}" == "--no-open" ]] && OPEN_BROWSER=false

# Resolve project root regardless of where the script is called from
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$PROJECT_DIR/copilot-ui"

API_PORT=8000
UI_PORT=5173
API_URL="http://localhost:$API_PORT/health"
UI_URL="http://localhost:$UI_PORT"

# Colour helpers
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

pids=()

cleanup() {
  echo -e "\n${YELLOW}Shutting down…${RESET}"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo -e "${GREEN}All services stopped.${RESET}"
}
trap cleanup EXIT INT TERM

# ── Pre-flight checks ─────────────────────────────────────────────────────────

echo -e "${BOLD}${CYAN}Intelligent Assistant Platform — Launcher${RESET}"
echo -e "${CYAN}──────────────────────────────────────────${RESET}"

# Check .env
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo -e "${RED}✗ .env not found at $PROJECT_DIR/.env${RESET}"
  echo "  Create it with OPENAI_API_KEY and DATABASE_URL (see .env.example)"
  exit 1
fi
echo -e "${GREEN}✓ .env found${RESET}"

# Check uvicorn
if ! command -v uvicorn &>/dev/null; then
  echo -e "${RED}✗ uvicorn not found in PATH${RESET}"
  echo "  Install: pip install uvicorn"
  exit 1
fi
echo -e "${GREEN}✓ uvicorn $(uvicorn --version 2>&1 | head -1)${RESET}"

# Check Node
if ! command -v npm &>/dev/null; then
  echo -e "${RED}✗ npm not found in PATH${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ node $(node --version)  npm $(npm --version)${RESET}"

# Check copilot-ui node_modules
if [[ ! -d "$UI_DIR/node_modules" ]]; then
  echo -e "${YELLOW}⟳ Installing UI dependencies (first run)…${RESET}"
  npm --prefix "$UI_DIR" install --silent
fi
echo -e "${GREEN}✓ UI dependencies OK${RESET}"

echo ""

# ── Start services ────────────────────────────────────────────────────────────

# 1. FastAPI backend
echo -e "${CYAN}▶ Starting FastAPI backend on port $API_PORT…${RESET}"
cd "$PROJECT_DIR"
uvicorn api.main:app --port "$API_PORT" --reload \
  > "$PROJECT_DIR/.api.log" 2>&1 &
pids+=($!)
echo -e "  PID ${pids[-1]}  →  logs: .api.log"

# 2. Vite dev server
echo -e "${CYAN}▶ Starting Vite dev server on port $UI_PORT…${RESET}"
npm --prefix "$UI_DIR" run dev \
  > "$PROJECT_DIR/.vite.log" 2>&1 &
pids+=($!)
echo -e "  PID ${pids[-1]}  →  logs: .vite.log"

# ── Wait for readiness ────────────────────────────────────────────────────────

echo ""
echo -e "${YELLOW}Waiting for services to be ready…${RESET}"

# Helpers
wait_http() {
  local url="$1" label="$2" max=30
  for i in $(seq 1 $max); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo -e "  ${GREEN}✓ $label ready${RESET}"
      return 0
    fi
    sleep 1
  done
  echo -e "  ${RED}✗ $label did not start within ${max}s — check .api.log or .vite.log${RESET}"
  return 1
}

wait_http "$API_URL"             "FastAPI  ($API_URL)"
wait_http "$UI_URL"              "Vite     ($UI_URL)"

# ── Open browser ──────────────────────────────────────────────────────────────

if $OPEN_BROWSER; then
  echo ""
  echo -e "${CYAN}▶ Opening browser at $UI_URL${RESET}"
  if command -v open &>/dev/null; then
    open "$UI_URL"           # macOS
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$UI_URL"       # Linux
  elif command -v start &>/dev/null; then
    start "$UI_URL"          # Windows (Git Bash)
  fi
fi

# ── Ready ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}✓ Copilot is running!${RESET}"
echo -e "  ${CYAN}UI:  ${BOLD}$UI_URL${RESET}"
echo -e "  ${CYAN}API: ${BOLD}http://localhost:$API_PORT${RESET}"
echo -e "  ${CYAN}Docs:${BOLD}http://localhost:$API_PORT/docs${RESET}"
echo ""
echo -e "${YELLOW}Next: load the ALS Listener (.amxd) device in Ableton Live${RESET}"
echo -e "  Drag ${BOLD}ableton_bridge/als_listener/ALSListener.amxd${RESET} onto any track."
echo ""
echo -e "Press ${BOLD}Ctrl+C${RESET} to stop all services."
echo ""

# ── Keep alive ────────────────────────────────────────────────────────────────
wait
