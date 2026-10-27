# SumiVideoOutput 1.0

Independent raw-video command-line program, licensed GPL-2.0-only. It accepts any
source of BGR24 frames on stdin and forwards them to an installed virtual camera.
It does not import Sumi, MediaPipe, OpenCV or its gesture/effect modules.
There is no webcam capture, audio capture, network interface or recording here.

## Protocol

Arguments: `--width 1280 --height 720 --fps 30 --backend obs` (or `unitycapture`).
Dimensions must be even, 2..3840 by 2..2160; fps 1..120. Format is contiguous BGR24,
top-to-bottom, exactly width * height * 3 bytes per frame, with no frame headers.
Frames are synchronous; the producer should pace them at the requested rate.

Stdout is UTF-8 JSON, one line per message:

- Startup: `{"event":"ready","device":"...","format":"bgr24","width":1280,"height":720}`
- After the virtual camera accepts each frame: `{"event":"frame","index":1}` (1-based).
- Failure: `{"event":"error","message":"..."}`, followed by a nonzero exit code.

Closing stdin on a frame boundary closes the output normally. A partial last frame
is rejected. Stdout must be drained by the producer. This interface can be used
without the Sumi app, for example with a separate producer of raw video.
`--dry-run` validates the stream and returns frame CRC32 without opening a camera;
`--self-test` verifies imports; `--license` prints the complete license.

## Build the program

Windows x64 with Python 3.14 and an installed OBS virtual camera for real output.
Run these commands from the `camera_output/` directory:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.venv\Scripts\python.exe -m PyInstaller --noconfirm worker.spec
```

No C++ compiler is needed when using the upstream Python wheel. To rebuild
PyVirtualCam's native extensions, the accompanying source archive includes the
official v0.15.0 tree, its pinned libyuv submodule and upstream build scripts.
See its README and `.github/scripts/build-windows.ps1`; a suitable Visual Studio
C++ compiler, Windows SDK, setuptools and pybind11 are needed on the build machine.
The upstream CI did not pin every build-tool version; bit-identical wheel rebuilds
are not claimed. Unmodified installed native files are inventoried by SHA-256.

## Distribution

Include this GPL license, the program's source and the corresponding PyVirtualCam
sources with libyuv, build instructions and dependency notices. Recipients retain
all rights provided by the GPL, including modification and redistribution. No
permission to push to the maintainer's repository is granted by those rights.

The graphical Sumi app is a separate program using this generic raw-video
interface. Its own source retains its own license. Distribution analysis must
consider the actual interface and packaging, not only process names.
