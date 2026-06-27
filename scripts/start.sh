#!/bin/bash
# LAZ-Bot 快速启动脚本
# Usage: bash scripts/start.sh

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

source venv/bin/activate

echo "=== LAZ-Bot 启动 ==="
echo "Project: $PROJECT_DIR"
echo ""

exec python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8765
