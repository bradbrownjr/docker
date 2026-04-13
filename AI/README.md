# AI Stack

A self-hosted, GPU-accelerated AI stack powered by Docker Compose. Includes a chat UI, local LLM inference, image generation, text-to-speech, speech-to-text, and private web search — all wired together and running locally.

## Services

| Service | Port | Description |
|---|---|---|
| [Open WebUI](https://github.com/open-webui/open-webui) | `3000` | Chat interface for all services |
| [Ollama](https://ollama.com) | `11434` | Local LLM inference |
| [ComfyUI + Flux](https://github.com/comfyanonymous/ComfyUI) | `8188` | Image generation |
| [Kokoro TTS](https://github.com/remsky/kokoro-fastapi) | `8880` | Text-to-speech |
| [WhisperX](https://github.com/onerahmet/openai-whisper-asr-webservice) | `9000` | Speech-to-text |
| [SearXNG](https://searxng.org) | `8080` | Private web search |

## Prerequisites

- **OS:** Linux (tested on CachyOS/Arch; Ubuntu/Debian support coming)
- **GPU:** NVIDIA GPU with CUDA support
- **Docker:** Docker Engine + Docker Compose v2
- **NVIDIA Container Toolkit:** Installed and configured (handled automatically by `start-docker.sh` on Arch-based systems)
- **Hugging Face Token:** Required for ComfyUI/Flux model downloads — get one at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/bradbrownjr/docker.git
cd docker/AI
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
HF_TOKEN=your_huggingface_token_here
LOW_VRAM=false        # Set to true if you have less than 12GB VRAM
FLUX_MODELS=schnell   # Options: schnell (fast) or dev (quality)
```

### 3. Pull Docker images

```bash
bash pull.sh
```

This pulls all required images: Ollama, WhisperX, Kokoro, ComfyUI, SearXNG, and Open WebUI.

### 4. Start the stack

**Recommended (handles Docker daemon + NVIDIA setup automatically):**

```bash
bash start-docker.sh
```

This script will:
- Install and configure the NVIDIA Container Toolkit if missing (Arch/CachyOS only)
- Start the Docker daemon if it isn't running
- Add your user to the `docker` group if needed
- Launch the full stack

**Or start directly with `run.sh`:**

```bash
bash run.sh
```

Once Open WebUI is ready, it will open automatically in your browser at **http://localhost:3000**.

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

### Available service names for `logs`

`ollama` · `whisperx` · `kokoro` · `comfyui` · `openwebui` · `searxng`

## Service URLs

| Service | URL |
|---|---|
| Open WebUI | http://localhost:3000 |
| Ollama API | http://localhost:11434 |
| ComfyUI | http://localhost:8188 |
| Kokoro TTS (docs) | http://localhost:8880/docs |
| WhisperX (docs) | http://localhost:9000/docs |
| SearXNG | http://localhost:8080 |

## Tips

- **Low VRAM?** Set `LOW_VRAM=true` in your `.env` file before starting.
- **Image generation failing?** ComfyUI and Ollama can contend for GPU memory. Run `bash run.sh free-vram` to release ComfyUI's VRAM before generating images.
- **First startup is slow** — ComfyUI will download Flux model weights on first run. Subsequent starts are much faster.
- **Pulling models in Ollama:** After the stack is up, open Open WebUI and download a model from the admin settings, or run:
  ```bash
docker exec -it ollama ollama pull llama3.2
```