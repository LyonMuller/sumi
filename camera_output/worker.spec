# SPDX-License-Identifier: GPL-2.0-only
"""Build this standalone program without importing the Sumi application."""
from pathlib import Path

root = Path(SPECPATH)
a = Analysis([str(root / 'main.py')], pathex=[str(root)],
    datas=[(str(root / 'LICENSE'), '.'), (str(root / 'README.md'), '.')],
    excludes=['cv2', 'mediapipe', 'customtkinter', 'matplotlib', 'scipy', 'tkinter', 'PIL',
              'IPython', 'pytest', 'sounddevice', 'ssl', '_ssl', 'hashlib', '_hashlib', 'certifi',
              'urllib', 'http', 'sumi'], noarchive=False)
for name, source, kind in a.binaries:
    if Path(name).name.lower().startswith(('libssl', 'libcrypto', 'opencv_', 'libmediapipe')):
        raise ValueError('Unexpected dependency in output program: ' + name)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SumiVideoOutput',
          console=True, upx=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, name='SumiVideoOutput', upx=False, strip=False)
