#!/usr/bin/env bash
# Usage:
#   ./run.sh              — interactive: shows status and prompts for action
#   ./run.sh start        — start only stopped/missing containers
#   ./run.sh restart      — restart all containers
#   ./run.sh stop         — stop all containers
#   ./run.sh pull         — pull latest images, then start
#   ./run.sh logs         — tail logs for all services
#   ./run.sh logs <svc>   — tail logs for one service (ollama|whisperx|kokoro|comfyui|openwebui)
#   ./run.sh free-vram    — release GPU memory held by ComfyUI (run this before generating images if Ollama times out)
set -euo pipefail

DIR="$(cd ""$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f $DIR/docker-compose.ai-stack.yml --env-file $DIR/.env"

if [[ ! -f "$DIR/.env" ]]; then
  echo "ERROR: .env not found. Copy .env.example and fill in your HF_TOKEN:"
  echo "  cp $DIR/.env.example $DIR/.env"
  exit 1
fi

print_urls() {
  echo ""
  echo "  Services:"
  echo "    OpenWebUI  →  http://localhost:3000"
  echo "    Ollama     →  http://localhost:11434"
  echo "    ComfyUI    →  http://localhost:8188"
  echo "    Kokoro TTS →  http://localhost:8880/docs"
  echo "    WhisperX   →  http://localhost:9000/docs"
  echo "    SearXNG    →  http://localhost:8080"
  echo ""
}

print_status() {
  echo ""
  echo "  Container status:"
  docker compose -f "$DIR/docker-compose.ai-stack.yml" ps --format "table {{.Name}}	{{.Status}}" 2>/dev/null || true
  echo ""
}

open_browser() {
  local url="http://localhost:3000"
  echo "==> Waiting for OpenWebUI to be ready..."
  for i in $(seq 1 60); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "==> OpenWebUI is up."
      print_urls
      if command -v xdg-open &>/dev/null; then
        xdg-open "$url"
      elif command -v open &>/dev/null; then
        open "$url"
      fi
      return
    fi
    sleep 2
  done
  echo "==> Timed out waiting for OpenWebUI. Check logs with: ./run.sh logs"
  print_urls
}

do_start() {
  echo "==> Starting any stopped/missing containers..."
  $COMPOSE up -d
  open_browser
}

do_restart() {
  echo "==> Restarting all containers..."
  $COMPOSE restart
  open_browser
}

do_stop() {
  echo "==> Stopping all containers..."
  $COMPOSE down
  echo "==> All containers stopped."
}

interactive() {
  print_status

  echo "What would you like to do?"
  echo "  1) Start non-running containers"
  echo "  2) Restart all containers"
  echo "  3) Stop all containers"
  echo "  4) Exit"
  echo ""
  read -rp "Choice [1-4]: " choice

  case "$choice" in
    1) do_start ;;
    2) do_restart ;;
    3) do_stop ;;
    4) exit 0 ;;
    *) echo "Invalid choice."; exit 1 ;;
  esac
}

case "${1:-interactive}" in
  interactive) interactive ;;
  start)       do_start ;;
  restart)     do_restart ;;
  stop)        do_stop ;;
  pull)
    bash "$DIR/pull.sh"
    do_start
    ;;
  free-vram)
    echo "==> Freeing ComfyUI VRAM..."
    curl -s -X POST http://localhost:8188/api/free \
      -H "Content-Type: application/json" \
      -d '{"unload_models": true, "free_memory": true}' >/dev/null
    FREE=$(docker exec ollama nvidia-smi --query-gpu=memory.free --format=csv,noheader 2>/dev/null || echo "unknown")
    echo "==> Done. VRAM free: $FREE"
    ;;
  logs)
    $COMPOSE logs -f "${2:-}"
    ;;
  *)
    echo "Unknown command: $1"
    echo "Usage: $0 [start|restart|stop|pull|free-vram|logs [service]]"
    exit 1
    ;;
esac
