#!/bin/bash
# Prepares macos/.cache (git-ignored) for release builds:
#   .cache/python   standalone CPython 3.14 (deployment target macOS 11, so the bundle is not
#                   limited to the macOS version of the build machine, unlike Homebrew's Python)
#   .cache/venv     packaging environment; the repository's own .venv is never touched
#   .cache/wheels   OpenCV built without FFmpeg (see build-opencv.sh)
#
# Needs: uv (brew install uv), cmake and the Xcode command line tools.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cache="$here/.cache"
python_version="3.14.3"

command -v uv >/dev/null || { echo "Instale o uv: brew install uv" >&2; exit 1; }
command -v cmake >/dev/null || { echo "Instale o cmake: brew install cmake" >&2; exit 1; }

export UV_PYTHON_INSTALL_DIR="$cache/python"
mkdir -p "$cache"
uv python install "$python_version" --no-bin
python="$(UV_PYTHON_PREFERENCE=only-managed uv python find "$python_version")"

if [[ ! -x "$cache/venv/bin/python" ]]; then
    "$python" -m venv "$cache/venv"
fi
pip="$cache/venv/bin/python -m pip"
$pip install --quiet --upgrade pip

"$here/packaging/build-opencv.sh"
wheel="$(ls "$cache"/wheels/opencv_python_headless-*.whl | head -n 1)"

grep -v '^mediapipe==' "$here/packaging/requirements-mac.txt" > "$cache/requirements-resolved.txt"
$pip install --quiet -r "$cache/requirements-resolved.txt"
# Always the locally built wheel, even when PyPI's same-version package is already installed.
$pip install --quiet --force-reinstall --no-deps "$wheel"
$pip install --quiet --no-deps "mediapipe==1.1.1"
echo "Ambiente de empacotamento pronto em $cache/venv"
