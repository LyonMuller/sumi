#!/bin/bash
# Prepara o ambiente de desenvolvimento no macOS (Apple Silicon, Python 3.14 com Tk).
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3.14}"
if ! "$PYTHON" -c "import sys, platform, tkinter; sys.exit(0 if sys.version_info[:2] == (3, 14) and platform.machine() == 'arm64' else 1)" 2>/dev/null; then
    echo "Requer Python 3.14 arm64 com Tk. No Homebrew: brew install python@3.14 python-tk@3.14"
    exit 1
fi
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python setup_models.py
echo "Pronto. Execute iniciar.command."
