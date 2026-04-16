#!/usr/bin/env bash
set -euo pipefail

COMFYUI_DIR="/app"
MODELS_DIR="$COMFYUI_DIR/models"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
PYTHON="$(command -v python3 || command -v python)"

# ── Copy workflow into volume (build-time COPY is hidden by the volume) ──────
WORKFLOW_DIR="$COMFYUI_DIR/user/default/workflows"
mkdir -p "$WORKFLOW_DIR"
cp -f /scripts/flux2-klein-workflow.json "$WORKFLOW_DIR/flux2-klein.json"
echo "==> Flux2-Klein workflow installed."

# ── Install ComfyUI-GGUF custom node ─────────────────────────────────────────
if [[ ! -d "$CUSTOM_NODES_DIR/ComfyUI-GGUF" ]]; then
  echo "==> Installing ComfyUI-GGUF custom node..."
  git clone --depth=1 https://github.com/city96/ComfyUI-GGUF \
    "$CUSTOM_NODES_DIR/ComfyUI-GGUF"
  if ! "$PYTHON" -m pip --version &>/dev/null; then
    echo "==> Bootstrapping pip..."
    "$PYTHON" -m ensurepip 2>/dev/null \
      || curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
  fi
  "$PYTHON" -m pip install -q \
    -r "$CUSTOM_NODES_DIR/ComfyUI-GGUF/requirements.txt"
  echo "==> ComfyUI-GGUF installed."
else
  echo "==> ComfyUI-GGUF already installed."
fi

# ── Download model files ──────────────────────────────────────────────────────
_download() {
  local dest="$1" url="$2"
  if [[ -f "$dest" ]]; then
    echo "==> Already present: $(basename "$dest")"
    return 0
  fi
  echo "==> Downloading $(basename "$dest")..."
  mkdir -p "$(dirname "$dest")"
  if command -v curl &>/dev/null; then
    local curl_args=("-fL" "-o" "${dest}.tmp")
    [[ -n "${HF_TOKEN:-}" ]] && curl_args+=("-H" "Authorization: Bearer ${HF_TOKEN}")
    curl "${curl_args[@]}" "$url"
  elif command -v wget &>/dev/null; then
    local wget_args=("-q" "-O" "${dest}.tmp")
    [[ -n "${HF_TOKEN:-}" ]] && wget_args+=("--header=Authorization: Bearer ${HF_TOKEN}")
    wget "${wget_args[@]}" "$url"
  else
    "$PYTHON" -c "
import urllib.request, os, sys
url, dest = sys.argv[1], sys.argv[2]
req = urllib.request.Request(url)
token = os.environ.get('HF_TOKEN', '')
if token:
    req.add_header('Authorization', f'Bearer {token}')
urllib.request.urlretrieve(url, dest, reporthook=lambda b,bs,ts: print(f'\r  {b*bs/(1024**2):.0f} MB', end='', flush=True) if ts>0 else None)
print()
" "$url" "${dest}.tmp"
  fi
  if [[ -f "${dest}.tmp" ]]; then
    mv "${dest}.tmp" "$dest"
    echo "==> Done: $(basename "$dest")"
  else
    echo "ERROR: Failed to download $(basename "$dest")"
    exit 1
  fi
}

# UNet — FLUX.2-Klein 4B Q5_K_S GGUF (Apache 2.0, unsloth)
_download \
  "$MODELS_DIR/unet/flux-2-klein-4b-Q5_K_S.gguf" \
  "https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF/resolve/main/flux-2-klein-4b-Q5_K_S.gguf"

# Text encoder — fp4 quantized Qwen3-4B (Comfy-Org)
_download \
  "$MODELS_DIR/text_encoders/qwen_3_4b_fp4_flux2.safetensors" \
  "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/resolve/main/split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors"

# VAE (Comfy-Org)
_download \
  "$MODELS_DIR/vae/flux2-vae.safetensors" \
  "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/resolve/main/split_files/vae/flux2-vae.safetensors"

# ── Start ComfyUI ─────────────────────────────────────────────────────────────
COMFYUI_ARGS=(--listen 0.0.0.0 --port 8188 --gpu-only)
[[ "${LOW_VRAM:-false}" == "true" ]] && COMFYUI_ARGS+=(--lowvram)

echo "==> Starting ComfyUI..."
exec "$PYTHON" "$COMFYUI_DIR/main.py" "${COMFYUI_ARGS[@]}"
