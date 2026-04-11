#!/usr/bin/env bash
set -euo pipefail

echo "==> Pulling Ollama..."
docker pull ollama/ollama:latest

echo "==> Pulling WhisperX..."
docker pull onerahmet/openai-whisper-asr-webservice:latest-gpu

echo "==> Pulling Kokoro FastAPI (GPU)..."
docker pull ghcr.io/remsky/kokoro-fastapi-gpu:latest

echo "==> Pulling ComfyUI + Flux..."
docker pull frefrik/comfyui-flux:latest

echo "==> Pulling OpenWebUI (CUDA)..."
docker pull ghcr.io/open-webui/open-webui:cuda

echo "==> All images pulled."
