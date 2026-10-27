"""macOS (Apple Silicon): the Sumi engine as a one-folder PyInstaller bundle.

Run through build-engine.sh. The folder is later embedded in Sumi.app/Contents/Resources/engine.
What is left out on purpose: Tk/CustomTkinter and Pillow (the SwiftUI app draws the
window), PyVirtualCam (a separate GPL program, see build-engine.sh), sounddevice and
matplotlib. MediaPipe imports matplotlib.pyplot at import time only for its plotting
helpers; a stub (rthook_stub_matplotlib.py) satisfies that import instead of shipping
matplotlib, Pillow, fontTools and friends. Set SUMI_KEEP_MATPLOTLIB=1 to bundle the real one.
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

here = Path(SPECPATH).resolve()
root = here.parents[1]
keep_matplotlib = os.environ.get('SUMI_KEEP_MATPLOTLIB') == '1'
# verify-engine.sh swaps the entry point to run checks inside the frozen environment.
entry = os.environ.get('SUMI_ENTRY', str(root / 'main.py'))
product = os.environ.get('SUMI_NAME', 'SumiEngine')

datas = [(str(root / 'meet_extension'), 'meet_extension'),
         (str(root / 'LICENSE'), '.')]
for name in ('hand_landmarker.task', 'face_detector.tflite', 'selfie_segmenter_landscape.tflite'):
    datas.append((str(root / 'models' / name), 'models'))
for path in sorted((root / 'assets' / 'gestures').glob('*.png')):
    datas.append((str(path), 'assets/gestures'))
for path in sorted((root / 'assets' / 'effects').glob('*.png')):
    datas.append((str(path), 'assets/effects'))
for path in sorted((root / 'assets' / 'sounds').glob('*.wav')):
    datas.append((str(path), 'assets/sounds'))
# Brand art for the engine: the app icon only (README cover and the icon source art stay out).
for name in ('app-icon.png', 'app-icon-macos.png'):
    datas.append((str(root / 'assets' / 'brand' / name), 'assets/brand'))
datas += collect_data_files('mediapipe')
binaries = collect_dynamic_libs('mediapipe')

excludes = ['IPython', 'jupyter', 'pytest', 'sounddevice', 'pyvirtualcam', 'camera_output',
            'tkinter', '_tkinter', 'customtkinter', 'darkdetect', 'cffi', 'pip', 'setuptools',
            'pkg_resources', 'distutils', 'sumi.app', 'sumi.theme',
            'sumi.branding', 'sumi.hotkey', 'pydoc', 'doctest']
runtime_hooks = []
if not keep_matplotlib:
    excludes += ['matplotlib', 'PIL', 'fontTools', 'kiwisolver', 'contourpy', 'cycler',
                 'dateutil']
    runtime_hooks.append(str(here / 'rthook_stub_matplotlib.py'))

a = Analysis(
    [entry], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=['mediapipe.tasks.c', 'sumi.service'],
    excludes=excludes, runtime_hooks=runtime_hooks, noarchive=False,
)
# Safety net for the licence: no FFmpeg, x264 or x265 library may reach the bundle.
for name, source, kind in a.binaries:
    lowered = Path(name).name.lower()
    if lowered.startswith(('libavcodec', 'libavformat', 'libavutil', 'libswscale', 'libswresample',
                           'libx264', 'libx265', 'libpostproc', 'libavdevice', 'libavfilter')) \
            or 'opencv_videoio_ffmpeg' in lowered:
        raise ValueError('GPL/FFmpeg library in the engine bundle: ' + name)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=product, console=True,
          debug=False, strip=False, upx=False, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=product)
