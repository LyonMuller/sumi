#!/bin/bash
# Freezes the Python engine with PyInstaller (arm64, one folder) into macos/.cache/engine/SumiEngine.
# The separate GPL video-output program (camera_output/, PyVirtualCam) is frozen on its own and
# placed in SumiEngine/_internal/video_output, where virtual_output.py looks for it when frozen.
#
#   macos/packaging/build-engine.sh              # engine + video output
#   macos/packaging/build-engine.sh --no-output  # engine only (preview-only builds)
#
# Needs macos/.cache/venv (packaging/bootstrap.sh).
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
root="$(dirname "$here")"
cache="$here/.cache"
python="$cache/venv/bin/python"
out="$cache/engine"
work="$cache/pyinstaller"
with_output=1
[[ "${1:-}" == "--no-output" ]] && with_output=0

[[ -x "$python" ]] || { echo "Rode macos/packaging/bootstrap.sh primeiro." >&2; exit 1; }

# 1. Licence gate: the OpenCV in this environment must be the FFmpeg-free build.
"$python" -I - <<'PY'
import re
import cv2
info = cv2.getBuildInformation()
def value(key):
    match = re.search(r'^\s*' + key + r':\s+(\S+)', info, re.MULTILINE)
    return match.group(1) if match else 'absent'
ffmpeg, avfoundation = value('FFMPEG'), value('AVFoundation')
print(f'OpenCV {cv2.__version__}: FFMPEG={ffmpeg} AVFoundation={avfoundation}')
if ffmpeg not in ('NO', 'absent') or avfoundation != 'YES':
    raise SystemExit('OpenCV com FFmpeg (ou sem AVFoundation): rode packaging/build-opencv.sh --force e bootstrap.sh.')
PY

# 2. Models are git-ignored; fetch them (hash-verified) when missing.
if [[ ! -f "$root/models/hand_landmarker.task" || ! -f "$root/models/face_detector.tflite" \
      || ! -f "$root/models/selfie_segmenter_landscape.tflite" ]]; then
    (cd "$root" && "$python" setup_models.py)
fi

rm -rf "$out" "$work"
mkdir -p "$out" "$work"
cd "$cache"
"$python" -m PyInstaller --noconfirm --clean --distpath "$out" --workpath "$work/engine" \
    "$here/packaging/sumi-engine.spec"

if [[ "$with_output" == "1" ]]; then
    "$python" -m PyInstaller --noconfirm --clean --distpath "$work/output-dist" --workpath "$work/output" \
        "$root/camera_output/worker.spec"
    mkdir -p "$out/SumiEngine/_internal/video_output"
    ditto "$work/output-dist/SumiVideoOutput" "$out/SumiEngine/_internal/video_output"
fi

# 3. Hard stop if anything GPL from the OpenCV/FFmpeg world slipped in (the output program is its own GPL process).
if find "$out" \( -iname 'libx264*' -o -iname 'libx265*' -o -iname 'libavcodec*' -o -iname 'libavformat*' \
        -o -iname 'libavutil*' -o -iname 'libswscale*' -o -iname 'libpostproc*' -o -iname '*videoio_ffmpeg*' \) | grep -q .; then
    echo "Biblioteca GPL/FFmpeg encontrada no motor." >&2
    exit 1
fi
du -sh "$out/SumiEngine"
echo "Pronto: $out/SumiEngine"
