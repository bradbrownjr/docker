# AI Stack

A self-hosted, GPU-accelerated AI stack powered by Docker Compose. Includes a chat UI, local LLM inference, image generation, text-to-speech, speech-to-text, and private web search — all wired together and running locally.

## Services

| Service | Port | Description |
|---|---|---|
| [Open WebUI](https://github.com/open-webui/open-webui) | `3000` | Chat interface for all services |
| [Ollama](https://ollama.com) | `11434` | Local LLM inference |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) + FLUX.2-Klein 4B | `8188` | Image generation (GGUF quantized) |
| [Kokoro TTS](https://github.com/remsky/kokoro-fastapi) | `8880` | Text-to-speech |
| [Speaches](https://github.com/speaches-ai/speaches) (Whisper) | `9000` | Speech-to-text |
| [SearXNG](https://searxng.org) | `8080` | Private web search |

## Prerequisites

- **OS:** Linux — tested on CachyOS/Arch, Bazzite (Fedora Atomic), Debian/Ubuntu
- **GPU:** NVIDIA GPU with CUDA support (8 GB+ VRAM recommended)
- **Docker:** Docker Engine + Docker Compose v2 (installed automatically by `start-docker.sh` if missing)
- **NVIDIA Container Toolkit:** Installed and configured automatically by `start-docker.sh` on Arch-based systems

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/bradbrownjr/docker.git
cd docker/AI
```

### 2. Start the stack

```bash
bash start-docker.sh
```

That's it. The script handles everything:
- Installs NVIDIA Container Toolkit if missing (Arch/CachyOS only)
- Enables and starts the Docker daemon
- Installs Docker Compose V2 if missing
- Adds your user to the `docker` group
- Creates `.env` from `.env.example` and prompts for any required values
- Builds the custom ComfyUI image and launches the full stack

### First startup

The first run will be slow — ComfyUI automatically downloads FLUX.2-Klein model weights on first start (~5 GB total, 10–30 minutes depending on connection):
- `flux-2-klein-4b-Q5_K_S.gguf` (~2.9 GB) — UNet from [unsloth](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF)
- `qwen_3_4b_fp4_flux2.safetensors` (~3.7 GB) — Text encoder from [Comfy-Org](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b)
- `flux2-vae.safetensors` (~300 MB) — VAE from [Comfy-Org](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b)

It also installs the [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) custom node. All subsequent starts are fast.

All model files are Apache 2.0 licensed and do not require a HuggingFace token or license acceptance.

**You still need to pull an LLM model for chat.** After the stack is up, either:
- Open WebUI → Admin → Models → pull a model
- Or from the terminal:
  ```bash
  docker exec -it ollama ollama pull llama3.2
  ```

All integrations (image generation, TTS, STT, web search) are pre-wired and ready without any additional configuration. OpenWebUI is pre-configured with the FLUX.2-Klein ComfyUI workflow.

## Managing the Stack

`run.sh` is the main management script. You can run it interactively or pass a command directly:

```bash
bash run.sh              # Interactive mode — shows status and prompts for action
bash run.sh start        # Start any stopped/missing containers
bash run.sh restart      # Restart all containers
bash run.sh stop         # Stop and remove all containers
bash run.sh pull         # Pull latest images, then start
bash run.sh logs         # Tail logs for all services
bash run.sh logs ollama  # Tail logs for a specific service
bash run.sh free-vram    # Free GPU memory held by ComfyUI
```

`run.sh` also checks for missing or placeholder `.env` values on startup and prompts you to fill them in.

### Available service names for `logs`

`ollama` · `speaches` · `kokoro` · `comfyui` · `openwebui` · `searxng`

## Service URLs

| Service | URL |
|---|---|
| Open WebUI | http://localhost:3000 |
| Ollama API | http://localhost:11434 |
| ComfyUI | http://localhost:8188 |
| Kokoro TTS (docs) | http://localhost:8880/docs |
| Speaches STT (docs) | http://localhost:9000/docs |
| SearXNG | http://localhost:8080 |

## Tips

- **Low VRAM?** Set `LOW_VRAM=true` in your `.env` file before starting.
- **Image generation failing?** ComfyUI and Ollama can contend for GPU memory. Run `bash run.sh free-vram` to release ComfyUI's VRAM before generating images.
- **First startup is slow** — ComfyUI downloads FLUX.2-Klein model weights on first run (~5 GB). Subsequent starts are much faster.
- **Ollama has no models by default** — pull one after the stack is up (see Getting Started above).
- **Docker group not active?** If `run.sh` can't reach the Docker socket, it will attempt to activate the group automatically. If that fails, run `newgrp docker` in your shell and retry.
- **ComfyUI image is built locally** — `start-docker.sh` and `run.sh` handle `docker compose build` automatically. If you change `comfyui-gguf-start.sh` or `flux2-klein-workflow.json`, rebuild with `docker compose -f docker-compose.ai-stack.yml build comfyui`.
- **Service URLs show LAN IP** — `run.sh` auto-detects the host's LAN IP so URLs work from other machines on the network.