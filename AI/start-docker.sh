#!/usr/bin/env bash
set -euo pipefail

# ── Re-run as root if needed ──────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
  echo "==> Re-running as root..."
  exec sudo bash "$0" "$@"
fi

REAL_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd ""$(dirname "$0")" && pwd)"
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
if ! systemctl is-active --quiet docker; then
  echo "==> Starting Docker daemon..."
  systemctl start docker
else
  echo "==> Docker daemon already running."
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
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    echo "ERROR: $ENV_EXAMPLE not found. Cannot create .env."
    exit 1
  fi
  echo "==> .env not found. Creating from .env.example..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# Prompt for any placeholder values
changed=0
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  if [[ "$value" == *"your_"* || "$value" == *"_here"* || -z "$value" ]]; then
    echo ""
    echo "==> Value needed for: $key"
    read -rp "    Enter $key: " new_value </dev/tty
    escaped_value="$(printf '%s\n' "$new_value" | sed 's/[\/&]/\\&/g')"
    sed -i "s|^$key=.*|$key=$escaped_value|" "$ENV_FILE"
    changed=1
  fi
done < "$ENV_FILE"

if [[ "$changed" -eq 1 ]]; then
  echo "==> .env configured."
else
  echo "==> .env already configured."
fi

# ── Launch stack as the real user ─────────────────────────────────────────────
echo "==> Docker is ready. Launching stack..."
exec su - "$REAL_USER" -c "bash '$SCRIPT_DIR/run.sh' start"