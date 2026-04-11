#!/usr/bin/env bash
set -euo pipefail

# ── NVIDIA Container Toolkit ─────────────────────────────────────────────────
if ! command -v nvidia-ctk &>/dev/null; then
  echo "==> NVIDIA Container Toolkit not found. Installing..."
  # CachyOS / Arch Linux
  if command -v pacman &>/dev/null; then
    sudo pacman -Sy --noconfirm nvidia-container-toolkit
  else
    echo "ERROR: Unsupported package manager. Install nvidia-container-toolkit manually:"
    echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    exit 1
  fi
  echo "==> Configuring Docker runtime for NVIDIA..."
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  echo "==> NVIDIA Container Toolkit installed and configured."
else
  echo "==> NVIDIA Container Toolkit already installed."
fi

# ── Docker daemon ─────────────────────────────────────────────────────────────
if ! systemctl is-active --quiet docker; then
  echo "==> Starting Docker daemon..."
  sudo systemctl start docker
else
  echo "==> Docker daemon already running."
fi

# ── Docker group ──────────────────────────────────────────────────────────────
if ! groups "$USER" | grep -q '\bdocker\b'; then
  echo "==> Adding $USER to the docker group..."
  sudo usermod -aG docker "$USER"
  echo "==> Group membership updated. Applying with newgrp..."
  exec newgrp docker -- bash "$0" "$@"
fi

echo "==> Docker is ready. Launching stack..."
exec "$(dirname "$0")/run.sh"
