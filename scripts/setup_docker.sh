#!/bin/bash
# 安装 Docker + Open WebUI (可选组件)
# Usage: bash scripts/setup_docker.sh

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/setup_docker.log"

log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "============================================"
log "Docker + Open WebUI 安装"
log "============================================"

# Install Docker
log "[1/4] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh 2>&1 | tail -5 >> "$LOG_FILE"
    sudo usermod -aG docker "$USER"
    log "  Docker installed — you may need to re-login for group changes"
else
    log "  Docker already installed"
fi

# Start Docker
log "[2/4] Starting Docker..."
sudo systemctl enable docker 2>/dev/null || true
sudo systemctl start docker 2>/dev/null || true
sleep 3
docker --version 2>&1 | tee -a "$LOG_FILE"

# Pull and run Open WebUI
log "[3/4] Pulling Open WebUI image..."
docker pull ghcr.io/open-webui/open-webui:main 2>&1 | tail -5 >> "$LOG_FILE"

log "[4/4] Starting Open WebUI container..."
docker rm -f open-webui 2>/dev/null || true

docker run -d \
    --name open-webui \
    --restart always \
    -p 3000:8080 \
    -v open-webui-data:/app/backend/data \
    ghcr.io/open-webui/open-webui:main 2>&1 | tee -a "$LOG_FILE"

log "  Waiting for Open WebUI to start..."
sleep 10

if docker ps --filter name=open-webui --format "{{.Status}}" | grep -q "Up"; then
    log "  ✅ Open WebUI is running!"
else
    log "  ⚠️  May still be starting..."
    docker logs open-webui --tail 5 2>&1 | tee -a "$LOG_FILE"
fi

log "============================================"
log "DONE"
log "  Browse: http://$(hostname -I | awk '{print $1}'):3000"
log "  API:    http://localhost:3000/api"
log "============================================"
