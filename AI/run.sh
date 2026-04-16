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

# Repair .env if it has the same literal \n corruption
if grep -q '\\n' "$ENV_FILE" 2>/dev/null; then
  sed -i 's/\\n/\n/g' "$ENV_FILE"
fi

# Rebuild .env from .env.example structure to remove duplicate keys
if [[ -f "$ENV_EXAMPLE" ]]; then
  _tmp=$(mktemp)
  exec 3< "$ENV_EXAMPLE"
  while IFS= read -r _line <&3; do
    if [[ "$_line" =~ ^[[:space:]]*# || -z "$_line" ]]; then
      printf '%s\n' "$_line"
    elif [[ "$_line" == *=* ]]; then
      _key="${_line%%=*}"
      _cur=$(grep "^${_key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)
      if [[ -n "$_cur" ]]; then
        printf '%s=%s\n' "$_key" "$_cur"
      else
        printf '%s\n' "$_line"
      fi
    else
      printf '%s\n' "$_line"
    fi
  done > "$_tmp"
  exec 3<&-
  mv "$_tmp" "$ENV_FILE"
fi

# Prompt for any missing or placeholder values
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

_docker_err=$(docker info 2>&1 || true)
if ! docker info &>/dev/null 2>&1; then
  if echo "$_docker_err" | grep -qi "permission denied"; then
    # Group not active in this session — re-exec under sg docker once
    if [[ -z "${_DOCKER_GROUP_RELAUNCHED:-}" ]] && grep -qE "^docker:" /etc/group 2>/dev/null; then
      echo "==> Activating docker group for this session..."
      export _DOCKER_GROUP_RELAUNCHED=1
      exec sg docker -- bash "$0" "$@"
    fi
    echo "ERROR: Permission denied on Docker socket."
    echo "  Run: newgrp docker   (activates the group without logging out)"
    exit 1
  else
    # Daemon not running — start-docker.sh handles this
    echo "ERROR: Docker daemon is not running."
    echo "  Run: bash '$DIR/start-docker.sh'  (starts the daemon and launches the stack)"
    echo "  Or manually: sudo systemctl start docker"
    exit 1
  fi
fi

COMPOSE=(docker compose -f "$DIR/docker-compose.ai-stack.yml" --env-file "$DIR/.env")

print_urls() {
  local host
  host=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
  [[ -z "$host" ]] && host=$(hostname -I 2>/dev/null | awk '{print $1}')
  [[ -z "$host" ]] && host="localhost"
  echo ""
  echo "  Services:"
  echo "    OpenWebUI    ->  http://${host}:3000"
  echo "    Ollama       ->  http://${host}:11434"
  echo "    ComfyUI      ->  http://${host}:8188"
  echo "    Kokoro TTS   ->  http://${host}:8880/docs"
  echo "    Speaches STT ->  http://${host}:9000/docs"
  echo "    SearXNG      ->  http://${host}:8080"
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
      if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
        if command -v xdg-open &>/dev/null; then
          xdg-open "$url" 2>/dev/null || true
        elif command -v open &>/dev/null; then
          open "$url" 2>/dev/null || true
        fi
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
  "${COMPOSE[@]}" up -d --remove-orphans
  open_browser
}

do_restart() {
  echo "==> Restarting all containers..."
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans
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
