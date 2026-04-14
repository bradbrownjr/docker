#!/usr/bin/env bash
set -euo pipefail

# ── Re-run as root if needed ──────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
  echo "==> Re-running as root..."
  exec sudo bash "$0" "$@"
fi

REAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

# ── NVIDIA Container Toolkit ─────────────────────────────────────────────────
if ! command -v nvidia-ctk &>/dev/null; then
  echo "==> NVIDIA Container Toolkit not found. Installing..."
  if command -v pacman &>/dev/null; then
    pacman -Sy --noconfirm nvidia-container-toolkit
  else
    echo "ERROR: Unsupported package manager. Install nvidia-container-toolkit manually:"
    echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    exit 1
  fi
  echo "==> Configuring Docker runtime for NVIDIA..."
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
  echo "==> NVIDIA Container Toolkit installed and configured."
else
  echo "==> NVIDIA Container Toolkit already installed."
fi

# ── Docker daemon ─────────────────────────────────────────────────────────────
if ! systemctl is-enabled --quiet docker 2>/dev/null; then
  echo "==> Enabling Docker to start on boot..."
  systemctl enable docker
fi
if ! systemctl is-active --quiet docker; then
  echo "==> Starting Docker daemon..."
  systemctl start docker
else
  echo "==> Docker daemon already running."
fi

# ── Docker Compose V2 ───────────────────────────────────────────────────────
if ! docker compose version &>/dev/null; then
  echo "==> Docker Compose V2 plugin not found. Installing..."
  COMPOSE_PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"
  mkdir -p "$COMPOSE_PLUGIN_DIR"
  ARCH=$(uname -m)
  COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}"
  curl -fsSL "$COMPOSE_URL" -o "$COMPOSE_PLUGIN_DIR/docker-compose"
  chmod +x "$COMPOSE_PLUGIN_DIR/docker-compose"
  echo "==> Docker Compose V2 installed: $(docker compose version)"
else
  echo "==> Docker Compose V2 already installed."
fi

# ── Docker group ──────────────────────────────────────────────────────────────
if ! groups "$REAL_USER" | grep -q '\bdocker\b'; then
  echo "==> Adding $REAL_USER to the docker group..."
  usermod -aG docker "$REAL_USER"
  echo "==> Done. Group membership will apply in new shells."
else
  echo "==> $REAL_USER is already in the docker group."
fi

# ── .env setup ────────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "ERROR: $ENV_EXAMPLE not found. Cannot auto-configure .env."
  exit 1
fi

# Repair .env.example if it was corrupted with literal \n sequences (single-line file)
if [[ $(wc -l < "$ENV_EXAMPLE") -le 1 ]] && grep -q '\\n' "$ENV_EXAMPLE"; then
  echo "==> Repairing .env.example (literal \\n sequences detected)..."
  sed -i 's/\\n/\n/g' "$ENV_EXAMPLE"
  chown "$REAL_USER" "$ENV_EXAMPLE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> .env not found. Creating from .env.example..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# Repair .env if it has the same literal \n corruption
if grep -q '\\n' "$ENV_FILE" 2>/dev/null; then
  echo "==> Repairing .env (literal \\n sequences detected)..."
  sed -i 's/\\n/\n/g' "$ENV_FILE"
fi

# Rebuild .env from .env.example structure to remove duplicate keys
# For each key in .env.example, use the last value found in .env (falling back to example value)
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

# Prompt for any keys that are still missing, blank, or placeholder
# Read via fd 3 so stdin stays connected to the terminal for prompts
changed=0
exec 3< "$ENV_EXAMPLE"
while IFS= read -r line <&3; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  example_value="${line#*=}"

  # Add key to .env if it's missing entirely
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
    changed=1
  fi
done
exec 3<&-

if [[ "$changed" -eq 1 ]]; then
  echo "==> .env configured."
else
  echo "==> .env already configured."
fi

# Ensure .env is owned by the real user, not root
chown "$REAL_USER" "$ENV_FILE"

# ── Launch stack as the real user ─────────────────────────────────────────────
echo "==> Docker is ready. Launching stack..."
# Since we are already root, sudo -u/-g sets user and explicitly activates the
# docker group without needing a new PAM login session (su - doesn't work on
# Fedora Atomic/Bazzite for freshly-added groups)
exec sudo -u "$REAL_USER" -g docker -- bash "$SCRIPT_DIR/run.sh" start