#!/usr/bin/env bash
# setup.sh — bootstrap a new machine for the AI stack
# Run once after cloning:  bash setup.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${CYAN}──▶${NC} $*"; }
ok()    { echo -e "    ${GREEN}✓${NC}  $*"; }

# ── Sudo ──────────────────────────────────────────────────────────────────────

if ! sudo -v 2>/dev/null; then
    error "sudo access is required. Exiting."
    exit 1
fi
# Keep the sudo ticket alive for the duration of the script
( while true; do sudo -n true; sleep 50; done ) &
_SUDO_KEEP=$!
trap 'kill $_SUDO_KEEP 2>/dev/null || true' EXIT

CURRENT_USER=$(id -un)

# ── OS detection ──────────────────────────────────────────────────────────────

step "Detecting OS..."
if   [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_ID_LIKE="${ID_LIKE:-}"
else
    OS_ID="unknown"
    OS_ID_LIKE=""
fi

case "$OS_ID" in
    fedora)           PKG="dnf";  ok "Fedora detected" ;;
    rhel|centos|almalinux|rocky) PKG="dnf"; ok "RHEL-family detected" ;;
    ubuntu|debian)    PKG="apt";  ok "Debian/Ubuntu detected" ;;
    *)
        # Fall back to ID_LIKE
        if [[ "$OS_ID_LIKE" == *fedora* || "$OS_ID_LIKE" == *rhel* ]]; then
            PKG="dnf"; ok "RHEL-family detected via ID_LIKE"
        elif [[ "$OS_ID_LIKE" == *debian* || "$OS_ID_LIKE" == *ubuntu* ]]; then
            PKG="apt"; ok "Debian-family detected via ID_LIKE"
        else
            error "Unsupported OS: $OS_ID. Only Fedora/RHEL and Debian/Ubuntu are supported."
            exit 1
        fi
        ;;
esac

# ── Docker ────────────────────────────────────────────────────────────────────

step "Checking Docker..."
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    ok "Docker already installed: $(docker --version | head -1)"
else
    info "Installing Docker CE..."
    if [[ "$PKG" == "dnf" ]]; then
        sudo dnf config-manager addrepo \
            --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo 2>/dev/null \
            || sudo dnf config-manager --add-repo \
               https://download.docker.com/linux/fedora/docker-ce.repo
        sudo dnf install -y docker-ce docker-ce-cli containerd.io \
            docker-buildx-plugin docker-compose-plugin
    elif [[ "$PKG" == "apt" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y ca-certificates curl gnupg lsb-release
        sudo install -m0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/${OS_ID}/gpg \
            | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${OS_ID} $(lsb_release -cs) stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
        sudo apt-get update -qq
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
            docker-buildx-plugin docker-compose-plugin
    fi
    sudo systemctl enable --now docker
    ok "Docker installed: $(docker --version | head -1)"
fi

# ── Docker group ──────────────────────────────────────────────────────────────

if getent group docker | grep -qw "$CURRENT_USER"; then
    ok "User '$CURRENT_USER' is in the docker group"
else
    step "Adding '$CURRENT_USER' to the docker group..."
    sudo usermod -aG docker "$CURRENT_USER"
    warn "Group change takes effect after logout/login, or run: newgrp docker"
fi

# ── GPU detection ─────────────────────────────────────────────────────────────

step "Detecting GPU..."
GPU_TYPE="none"
if lspci 2>/dev/null | grep -qi "nvidia"; then
    GPU_TYPE="nvidia"
    ok "NVIDIA GPU detected"
elif lspci 2>/dev/null | grep -qi "amd\|radeon"; then
    GPU_TYPE="amd"
    ok "AMD GPU detected"
else
    warn "No discrete GPU detected — services will run CPU-only"
fi

# ── NVIDIA Container Toolkit ──────────────────────────────────────────────────

if [[ "$GPU_TYPE" == "nvidia" ]]; then
    step "Checking NVIDIA Container Toolkit..."
    if command -v nvidia-ctk &>/dev/null && rpm -q nvidia-container-toolkit &>/dev/null 2>/dev/null \
       || dpkg -l nvidia-container-toolkit &>/dev/null 2>/dev/null; then
        ok "nvidia-container-toolkit already installed"
    else
        info "Installing NVIDIA Container Toolkit..."
        if [[ "$PKG" == "dnf" ]]; then
            curl -fsSL \
                https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
                | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null
            sudo dnf install -y nvidia-container-toolkit
        elif [[ "$PKG" == "apt" ]]; then
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
                | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
                | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
                | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
            sudo apt-get update -qq
            sudo apt-get install -y nvidia-container-toolkit
        fi
        ok "nvidia-container-toolkit installed"
    fi

    step "Configuring Docker NVIDIA runtime..."
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    ok "Docker NVIDIA runtime configured"

    step "Verifying GPU passthrough..."
    if sudo docker run --rm --gpus all ubuntu:22.04 ls /dev/nvidia0 &>/dev/null; then
        ok "GPU passthrough confirmed"
    else
        warn "Could not confirm GPU passthrough — verify with:"
        warn "  sudo docker run --rm --gpus all ubuntu:22.04 ls /dev/nvidia*"
    fi
fi

# ── AMD ROCm note ─────────────────────────────────────────────────────────────

if [[ "$GPU_TYPE" == "amd" ]]; then
    step "AMD GPU setup note..."
    warn "AMD ROCm requires manual driver installation."
    warn "See: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/"
    warn "Once ROCm is installed, ensure your user is in the 'video' and 'render' groups:"
    warn "  sudo usermod -aG video,render $CURRENT_USER"
    warn "The stack's NVIDIA GPU config works for most services. For full AMD GPU"
    warn "acceleration, you may need to adjust the deploy.resources section in docker-compose.yml."
fi

# ── Voicebox source ───────────────────────────────────────────────────────────

step "Checking Voicebox source..."
VBDIR="$DIR/voicebox"
if [[ -d "$VBDIR/.git" || -f "$VBDIR/Dockerfile" ]]; then
    ok "Voicebox already present at $VBDIR"
    if [[ -d "$VBDIR/.git" ]]; then
        info "Updating Voicebox..."
        git -C "$VBDIR" pull --ff-only 2>/dev/null && ok "Voicebox updated" || warn "Could not auto-update Voicebox (local changes?)"
    fi
else
    info "Cloning Voicebox..."
    git clone --depth=1 https://github.com/jamiepine/voicebox "$VBDIR"
    ok "Voicebox cloned"
fi

# ── Hermes Agent source ───────────────────────────────────────────────────────

step "Checking Hermes Agent source..."
HERMES_DIR="$DIR/hermes"
if [[ -d "$HERMES_DIR/.git" || -f "$HERMES_DIR/Dockerfile" ]]; then
    ok "Hermes Agent already present at $HERMES_DIR"
    if [[ -d "$HERMES_DIR/.git" ]]; then
        info "Updating Hermes Agent..."
        git -C "$HERMES_DIR" pull --ff-only 2>/dev/null && ok "Hermes updated" || warn "Could not auto-update Hermes (local changes?)"
    fi
else
    info "Cloning Hermes Agent..."
    git clone --depth=1 https://github.com/nousresearch/hermes-agent "$HERMES_DIR"
    ok "Hermes Agent cloned"
fi

# ── .env setup ────────────────────────────────────────────────────────────────

step "Setting up .env..."
ENV_FILE="$DIR/.env"
ENV_EXAMPLE="$DIR/.env.example"

if [[ -f "$ENV_FILE" ]]; then
    ok ".env already exists"
else
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok ".env created from .env.example"

    echo ""
    info "A few values need to be filled in. Press Enter to skip optional ones."
    echo ""

    _prompt() {
        local key="$1" prompt="$2" required="${3:-false}"
        local cur
        cur=$(grep -m1 "^${key}=" "$ENV_FILE" | cut -d= -f2- || true)
        if [[ -z "$cur" ]]; then
            read -rp "    $prompt: " val
            if [[ -n "$val" ]]; then
                escaped="$(printf '%s\n' "$val" | sed 's/[\/&]/\\&/g')"
                sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
            elif [[ "$required" == "true" ]]; then
                warn "$key is required — edit .env before starting the stack"
            fi
        fi
    }

    _prompt "HF_TOKEN"               "Hugging Face token (for ComfyUI model downloads)" false
    _prompt "ODYSSEUS_ADMIN_PASSWORD" "Odysseus admin password (leave blank to auto-generate)" false
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "    Start the core stack:"
echo "      ./run.sh start"
echo ""
echo "    Start with optional services:"
echo "      ./run.sh start --profile voicebox"
echo "      ./run.sh start --profile odysseus"
echo "      ./run.sh start --profile hermes"
echo ""
echo "    Open the dashboard (http://localhost:8888):"
echo "      ./run.sh dashboard"
echo ""

if ! getent group docker | grep -qw "$CURRENT_USER"; then
    echo -e "  ${YELLOW}⚠  Run 'newgrp docker' or log out/in before starting the stack.${NC}"
    echo ""
fi

if [[ "$GPU_TYPE" == "none" ]]; then
    echo -e "  ${YELLOW}⚠  No GPU detected. Edit docker-compose.yml to remove the${NC}"
    echo -e "  ${YELLOW}   'deploy.resources.reservations' blocks before starting.${NC}"
    echo ""
fi
