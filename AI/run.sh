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

# Prompt for any missing or placeholder values
if [[ -f "$ENV_EXAMPLE" ]]; then
  exec 3< "$ENV_EXAMPLE"
  while IFS= read -r line <&3; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      echo "$key=" >> "$ENV_FILE"
    fi
    current_value=$(grep -m1 "^${key}=" "$ENV_FILE" | cut -d= -f2-)
    if [[ "$current_value" == *"your_"* || "$current_value" == *"_here"* ]]; then
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
  echo "  See: https://docs.docker.com/compose/install/"
  exit 1
fi

_docker_err=$(docker info 2>&1 || true)
if ! docker info &>/dev/null 2>&1; then
  if echo "$_docker_err" | grep -qi "permission denied"; then
    if [[ -z "${_DOCKER_GROUP_RELAUNCHED:-}" ]] && grep -qE "^docker:" /etc/group 2>/dev/null; then
      echo "==> Activating docker group for this session..."
      QUOTED="$(printf '%q ' "$0" "$@")"
      exec sg docker -c "_DOCKER_GROUP_RELAUNCHED=1 bash $QUOTED"
    fi
    echo "ERROR: Permission denied on Docker socket."
    echo "  Run: newgrp docker"
    exit 1
  else
    echo "ERROR: Docker daemon is not running."
    echo "  Run: sudo systemctl start docker"
    exit 1
  fi
fi

# Parse arguments: first non-flag arg is the command; --profile flags build PROFILES
CMD="interactive"
PROFILES=()
LOGS_SVC=""
i=0
ARGS=("$@")
while [[ $i -lt ${#ARGS[@]} ]]; do
  arg="${ARGS[$i]}"
  case "$arg" in
    --profile)
      i=$((i+1))
      PROFILES+=("--profile" "${ARGS[$i]}")
      ;;
    --profile=*)
      PROFILES+=("--profile" "${arg#--profile=}")
      ;;
    logs)
      CMD="logs"
      i=$((i+1))
      [[ $i -lt ${#ARGS[@]} ]] && LOGS_SVC="${ARGS[$i]}" || LOGS_SVC=""
      i=$((i+1))
      continue
      ;;
    *)
      [[ "$CMD" == "interactive" ]] && CMD="$arg"
      ;;
  esac
  i=$((i+1))
done

COMPOSE=(docker compose -f "$DIR/docker-compose.yml" --env-file "$DIR/.env" "${PROFILES[@]}")

_has_profile() {
  local p="$1"
  local elem
  for elem in "${PROFILES[@]}"; do
    [[ "$elem" == "$p" ]] && return 0
  done
  return 1
}

print_urls() {
  local host
  host=$(ip route get 1.1.1.1 2>/dev/null | awk '/src/{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1);exit}}') || true
  [[ -z "${host:-}" ]] && host=$(hostname -I 2>/dev/null | awk '{print $1}') || true
  [[ -z "${host:-}" ]] && host="localhost"
  echo ""
  echo "  Services:"
  echo "    OpenWebUI    ->  http://${host}:3000"
  echo "    Ollama       ->  http://${host}:11434"
  echo "    ComfyUI      ->  http://${host}:8188"
  echo "    Kokoro TTS   ->  http://${host}:8880/docs"
  echo "    Speaches STT ->  http://${host}:9000/docs"
  echo "    SearXNG      ->  http://${host}:8080"
  if _has_profile "voicebox"; then
    echo "    Voicebox     ->  http://${host}:17493"
  fi
  if _has_profile "odysseus"; then
    echo "    Odysseus     ->  http://${host}:7000"
    echo "    ChromaDB     ->  http://${host}:8100"
    echo "    ntfy         ->  http://${host}:8091"
  fi
  echo ""
}

print_status() {
  echo ""
  echo "  Container status:"
  "${COMPOSE[@]}" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true
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
        xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null || true
      fi
      return
    fi
    sleep 2
  done
  echo "==> Timed out waiting for OpenWebUI. Check logs with: ./run.sh logs"
  print_urls
}

do_start() {
  echo "==> Building custom images (if needed)..."
  "${COMPOSE[@]}" build
  echo "==> Starting containers..."
  "${COMPOSE[@]}" up -d --remove-orphans
  open_browser
}

do_restart() {
  echo "==> Building custom images (if needed)..."
  "${COMPOSE[@]}" build
  echo "==> Restarting all containers..."
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans
  open_browser
}

do_stop() {
  echo "==> Stopping containers..."
  "${COMPOSE[@]}" down
  echo "==> Done."
}

interactive() {
  print_status
  local active_profiles="${PROFILES[*]:-none}"
  echo "Active profiles: $active_profiles"
  echo ""
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

case "$CMD" in
  interactive) interactive ;;
  start)       do_start ;;
  restart)     do_restart ;;
  stop)        do_stop ;;
  logs)        "${COMPOSE[@]}" logs -f ${LOGS_SVC:+"$LOGS_SVC"} ;;
  free-vram)
    echo "==> Freeing ComfyUI VRAM..."
    curl -s -X POST http://localhost:8188/api/free \
      -H "Content-Type: application/json" \
      -d '{"unload_models": true, "free_memory": true}' >/dev/null
    FREE=$(docker exec ollama nvidia-smi --query-gpu=memory.free --format=csv,noheader 2>/dev/null || echo "unknown")
    echo "==> Done. VRAM free: $FREE"
    ;;
  dashboard)
    PORT="${DASHBOARD_PORT:-8888}"
    echo "==> Starting dashboard on http://localhost:${PORT}"
    echo "    (Ctrl-C to stop)"
    exec python3 "$DIR/dashboard.py" "${DASHBOARD_PORT:+--port=$DASHBOARD_PORT}"
    ;;
  *)
    echo "Unknown command: $CMD"
    echo "Usage: $0 [start|restart|stop|logs [svc]|free-vram|dashboard] [--profile voicebox] [--profile odysseus]"
    exit 1
    ;;
esac
