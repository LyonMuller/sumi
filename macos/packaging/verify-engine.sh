#!/bin/bash
# Freezes frozen_selftest.py with the engine's recipe and runs it: resources, model hashes, MediaPipe
# inference, every effect and the video-output program, all inside a frozen bundle and without a camera.
#
#   macos/packaging/verify-engine.sh
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cache="$here/.cache"
python="$cache/venv/bin/python"
probe="$cache/engine-probe"
engine="$cache/engine/SumiEngine"
[[ -x "$python" && -d "$engine/_internal/video_output" ]] || { echo "Rode bootstrap.sh e build-engine.sh primeiro." >&2; exit 1; }

rm -rf "$probe" "$cache/pyinstaller/probe"
cd "$cache"
SUMI_ENTRY="$here/packaging/frozen_selftest.py" SUMI_NAME=SumiEngineProbe \
    "$python" -m PyInstaller --noconfirm --clean --log-level WARN --distpath "$probe" \
    --workpath "$cache/pyinstaller/probe" "$here/packaging/sumi-engine.spec"
# Use the real engine's folder (including video_output) so the check covers what ships.
cp "$probe/SumiEngineProbe/SumiEngineProbe" "$engine/SumiEngineProbe"
trap 'rm -f "$engine/SumiEngineProbe"' EXIT
HOME="$(mktemp -d)" "$engine/SumiEngineProbe"
