#!/bin/bash
# Builds OpenCV from source as a wheel WITHOUT FFmpeg (and therefore without x264/x265).
#
# The opencv-python wheels for macOS bundle FFmpeg with GPL codecs. Sumi only needs
# imgproc, imgcodecs and camera capture through AVFoundation, so this builds the same
# OpenCV version as requirements-mac.txt with only those modules, headless, and with
# the FFmpeg and GStreamer backends off. The wheel is cached in macos/.cache/wheels/.
#
#   macos/packaging/build-opencv.sh            # no-op when the wheel is already cached
#   macos/packaging/build-opencv.sh --force    # rebuild
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cache="$here/.cache"
python="$cache/venv/bin/python"

# Same version as requirements-mac.txt; the sdist hash pins the source tree.
version="4.14.0.94"
sdist_sha256="4afa2ea1214453648be88259f035712454faa9039b686de7753569ba8eec1577"
sdist_url="https://files.pythonhosted.org/packages/source/o/opencv-python-headless/opencv_python_headless-$version.tar.gz"
deployment_target="13.0"

wheels="$cache/wheels"
mkdir -p "$wheels" "$cache/src"
existing="$(ls "$wheels"/opencv_python_headless-"$version"-*.whl 2>/dev/null | head -n 1 || true)"
if [[ -n "$existing" && "${1:-}" != "--force" ]]; then
    echo "Wheel do OpenCV já existe: $existing"
    exit 0
fi
[[ -x "$python" ]] || { echo "Rode macos/packaging/bootstrap.sh primeiro (cria $cache/venv)." >&2; exit 1; }

# Build tools (scikit-build, an older numpy for the headers) live in their own venv so the
# packaging venv keeps exactly the pinned versions of requirements-mac.txt.
builder="$cache/venv-opencv/bin/python"
[[ -x "$builder" ]] || "$python" -m venv "$cache/venv-opencv"

tarball="$cache/src/opencv_python_headless-$version.tar.gz"
if [[ ! -f "$tarball" ]]; then
    curl -fL --retry 3 -o "$tarball" "$sdist_url"
fi
echo "$sdist_sha256  $tarball" | shasum -a 256 -c -

work="$cache/src/opencv-build"
rm -rf "$work"
mkdir -p "$work"
tar xzf "$tarball" -C "$work"
source_dir="$work/opencv_python_headless-$version"

# The optional type-stub files (py.typed, cv2/typing) cannot be generated for a module subset
# (the stub generator expects features2d). They are only editor hints and nothing imports them,
# so drop them from the wheel manifest of this throwaway copy of the sdist.
"$builder" - "$source_dir/setup.py" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
old_typed = '        [ r"python/cv2/py.typed" ] if sys.version_info >= (3, 6) else []\n'
old_typing = '        rearrange_cmake_output_data["cv2.typing"] = ["python/cv2" + r"/typing/.*\\.py"]\n'
assert old_typed in text and old_typing in text, 'setup.py layout changed; review the patch'
text = text.replace(old_typed, '        []\n').replace(old_typing, '        pass\n')
path.write_text(text)
PY

"$builder" -m pip install --quiet "numpy==2.3.2" "scikit-build>=0.14.0" "setuptools<70" wheel packaging cmake

# BUILD_LIST keeps only what the engine calls (see `grep -rho 'cv2\.[A-Za-z_]*' sumi`).
# WITH_FFMPEG=OFF is the licence-critical flag; AVFoundation stays on for the camera.
export MACOSX_DEPLOYMENT_TARGET="$deployment_target"
export ENABLE_HEADLESS=1
export CMAKE_ARGS="-DPYTHON3_LIMITED_API=ON -DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DWITH_AVFOUNDATION=ON \
-DWITH_AVIF=OFF -DWITH_OPENCL=OFF -DWITH_OPENEXR=OFF -DBUILD_OPENEXR=OFF -DBUILD_LIST=core,imgproc,imgcodecs,videoio,python3 \
-DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target \
-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew;/usr/local"
export CMAKE_BUILD_PARALLEL_LEVEL="$(sysctl -n hw.ncpu)"
export OPENCV_PYTHON_SKIP_GIT_COMMANDS=1

cd "$source_dir"
"$builder" -m pip wheel . --no-deps --no-build-isolation --wheel-dir "$wheels" -v

# The wheel must not depend on anything outside macOS itself (a Homebrew libavif was picked up once).
wheel="$(ls "$wheels"/opencv_python_headless-"$version"-*.whl)"
check="$(mktemp -d)"
unzip -q "$wheel" -d "$check"
bad="$(find "$check" \( -name '*.so' -o -name '*.dylib' \) -exec otool -L {} + \
    | awk '$1 ~ /^\// && $1 !~ /:$/ && $1 !~ /^\/(usr\/lib|System)\// {print $1}' | sort -u)"
rm -rf "$check"
if [[ -n "$bad" ]]; then
    echo "O wheel depende de bibliotecas fora do macOS:" >&2
    echo "$bad" >&2
    exit 1
fi
echo "Pronto: $wheel"
