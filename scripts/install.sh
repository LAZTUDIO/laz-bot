#!/bin/bash
# LAZ-Bot 一键部署脚本 (在树莓派上执行)
# Usage: bash scripts/install.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== LAZ-Bot 安装脚本 ==="
echo "Project: $PROJECT_DIR"
echo ""

# 1. System dependencies
echo "[1/6] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-venv \
    alsa-utils \
    ffmpeg \
    libsndfile1 \
    2>&1 | tail -3

# 2. Python venv
echo "[2/6] Creating Python virtual environment..."
cd "$PROJECT_DIR"
python3 -m venv venv
source venv/bin/activate

# 3. Upgrade pip
echo "[3/6] Upgrading pip..."
pip install --quiet --upgrade pip

# 4. Install Python packages
echo "[4/6] Installing Python packages..."
pip install --quiet -r requirements.txt

# 5. Initialize database
echo "[5/6] Initializing database..."
if [ ! -f "$PROJECT_DIR/config.yaml" ]; then
    cp "$PROJECT_DIR/config.yaml.example" "$PROJECT_DIR/config.yaml"
    echo "  Created config.yaml from example — edit it with your API keys"
else
    echo "  config.yaml already exists, skipping copy"
fi
python3 "$PROJECT_DIR/scripts/init_db.py"

# 6. Verify
echo "[6/6] Verifying installations..."
python3 -c "
import fastapi; print(f'  FastAPI: {fastapi.__version__}')
import openwakeword; print(f'  openWakeWord: OK')
import numpy; print(f'  NumPy: OK')
import httpx; print(f'  httpx: OK')
import yaml; print(f'  yaml: OK')
import psutil; print(f'  psutil: {psutil.__version__}')
import sqlite_vec; print(f'  sqlite-vec: OK')
print('  All dependencies OK!')
"

echo ""
echo "=== 安装完成! ==="
echo ""
echo "启动方式:"
echo "  bash scripts/start.sh"
echo "  或: cd $PROJECT_DIR && source venv/bin/activate"
echo "      python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8765"
echo ""
echo "管理界面: http://<你的IP>:8765/admin"
