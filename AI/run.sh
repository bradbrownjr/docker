#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/.env"
ENV_EXAMPLE="$DIR/.env.example"

# Repair .env.example if corrupted with literal \n sequences (single-line file)
if [[ -f "$ENV_EXAMPLE" ]] && [[ $(wc -l < "$ENV_EXAMPLE") -le 1 ]] && grep -q '\\n' "$ENV_EXAMPLE"; then
  sed -i 's/\\n/\n/g' "$ENV_EXAMPLE"
fi

# Create .env if missing
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "ERROR: No .env or .env.example found in $DIR."
    exit 1
  fi
  echo "==> .env not found. Creating from .env.example..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# Prompt for any missing or placeholder values
# Read the file via fd 3 so stdin stays connected to the terminal for prompts
if [[ -f "$ENV_EXAMPLE" ]]; then
  exec 3< "$ENV_EXAMPLE"
  while IFS= read -r line <&3; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    example_value="${line#*=}"
    if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      echo "$key=$example_value" >> "$ENV_FILE"
    fi
    current_value=$(grep -m1 "^${key}=" "$ENV_FILE" | cut -d= -f2-)
    if [[ "$current_value" == *"your_"* || "$current_value" == *"_here"* || -z "$current_value" ]]; then
      echo ""
      echo "==> Value needed for: $key"
      read -rp "    Enter $key: " new_value
      escaped_value="$(printf '%s\n' "$new_value" | sed 's/[\/&]/\\&/g')"
      sed -i "s|^$key=.*|$key=$escaped_value|" "$ENV_FILE"
    fi
  done
  exec 3<&-
fi

if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose V2 plugin not found."
  echo "  Run: bash '$DIR/start-docker.sh'  (it will install it automatically)"
  echo "  Or manually: https://docs.docker.com/compose/install/"
  exit 1
fi

if ! docker info &>/dev/null; then
  echo "ERROR: Cannot connect to the Docker daemon."
  echo "  • Docker not running? Try: sudo systemctl start docker"
  echo "  • Just added to docker group? Run: newgrp docker  (then retry)"
  exit 1
fi

COMPOSE=(docker compose -f "$DIR/docker-compose.ai-stack.yml" --env-file "$DIR/.env")

print_urls() {
  echo ""
  echo "  Services:"
  echo "    OpenWebUI  ->  http://localhost:3000"
  echo "    Ollama     ->  http://localhost:11434"
  echo "    ComfyUI    ->  http://localhost:8188"
  echo "    Kokoro TTS ->  http://localhost:8880/docs"
  echo "    WhisperX   ->  http://localhost:9000/docs"
  echo "    SearXNG    ->  http://localhost:8080"
  echo ""
}

print_status() {
  echo ""
  echo "  Container status:"
  docker compose -f "$DIR/docker-compose.ai-stack.yml" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true
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
  "${COMPOSE[@]}" up -d
  open_browser
}

do_restart() {
  echo "==> Restarting all containers..."
  "${COMPOSE[@]}" restart
  open_browser
}

do_stop() {
  echo "==> Stopping all containers..."
  "${COMPOSE[@]}" down
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
    "${COMPOSE[@]}" logs -f "${2:-}"
    ;;
  *)
    echo "Unknown command: $1"
    echo "Usage: $0 [start|restart|stop|pull|free-vram|logs [service]]"
    exit 1
    ;;
esac
