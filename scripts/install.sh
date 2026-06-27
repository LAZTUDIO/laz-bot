#!/bin/bash
# LAZ-Bot 一键部署脚本 (在树莓派上执行)
# Usage: bash scripts/install.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== LAZ-Bot 安装脚本 ==="
echo "Project: $PROJECT_DIR"
echo ""

# 1. System dependencies
echo "[1/5] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-venv \
    alsa-utils \
    ffmpeg \
    libsndfile1 \
    2>&1 | tail -3

# 2. Python venv
echo "[2/5] Creating Python virtual environment..."
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate

# 3. Install Python packages
echo "[3/5] Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt 2>&1 | tail -3

# 4. Verify installations
echo "[4/5] Verifying installations..."
python3 -c "
import fastapi; print(f'  FastAPI: {fastapi.__version__}')
import silero_vad; print(f'  SileroVAD: OK')
import openwakeword; print(f'  openWakeWord: OK')
import numpy; print(f'  NumPy: OK')
import httpx; print(f'  httpx: OK')
import yaml; print(f'  yaml: OK')
print('  All dependencies OK!')
"

# 5. Create data directory and config
mkdir -p "$PROJECT_DIR/data"
if [ ! -f "$PROJECT_DIR/config.yaml" ]; then
    cp "$PROJECT_DIR/config.yaml.example" "$PROJECT_DIR/config.yaml"
    echo "[5/5] Created config.yaml from example — edit it with your API keys"
else
    echo "[5/5] config.yaml already exists, skipping"
fi

echo ""
echo "=== 安装完成! ==="
echo ""
echo "启动方式:"
echo "  cd $PROJECT_DIR && source venv/bin/activate"
echo "  python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8765"
echo ""
echo "管理界面: http://<你的IP>:8765/admin"
