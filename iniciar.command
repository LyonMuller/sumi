#!/bin/bash
# Abre o Sumi pelos fontes no macOS.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Execute instalar.command primeiro."
    exit 1
fi
exec .venv/bin/python main.py
