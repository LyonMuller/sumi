# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2026 Lyon Müller
# Copyright (c) 2026 Fora de Cena contributors
"""Standalone BGR24 raw-video stdin -> virtual camera. No app-specific imports."""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import sys
from typing import BinaryIO, Callable
import zlib

MAX_FRAME_BYTES = 3840 * 2160 * 3


def read_frame(source: BinaryIO, buffer: bytearray) -> bool:
    view = memoryview(buffer)
    offset = 0
    while offset < len(view):
        count = source.readinto(view[offset:])
        if not count:
            if offset:
                raise EOFError('Incomplete raw-video frame')
            return False
        offset += count
    return True


def emit(message: dict[str, object]) -> None:
    sys.stdout.buffer.write((json.dumps(message, ensure_ascii=True) + '\n').encode('ascii'))
    sys.stdout.buffer.flush()


def stream(source: BinaryIO, width: int, height: int, send: Callable[[memoryview], None],
           reply: Callable[[dict[str, object]], None], dry_run: bool = False) -> None:
    buffer = bytearray(width * height * 3)
    index = 0
    while read_frame(source, buffer):
        send(memoryview(buffer))
        index += 1
        message: dict[str, object] = {'event': 'frame', 'index': index}
        if dry_run:
            message['crc32'] = zlib.crc32(buffer)
        # Acknowledgment happens only after Camera.send returns successfully.
        reply(message)


def self_test() -> dict[str, object]:
    import numpy as np
    import pyvirtualcam
    forbidden = sorted(name for name in ('cv2', 'mediapipe', 'customtkinter', 'sumi', 'ssl', '_ssl', '_hashlib') if name in sys.modules)
    if forbidden:
        raise RuntimeError('Unexpected output-process imports: ' + ', '.join(forbidden))
    return {'ok': True, 'program': 'SumiVideoOutput', 'license': 'GPL-2.0-only',
            'pyvirtualcam': pyvirtualcam.__version__, 'numpy': np.__version__,
            'camera_opened': False, 'forbidden_imports': forbidden}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--backend', choices=('obs', 'unitycapture'), default='obs')
    parser.add_argument('--dry-run', action='store_true', help='Validate the stream without opening a camera')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--license', action='store_true')
    args = parser.parse_args()
    if args.license:
        print((Path(__file__).resolve().parent / 'LICENSE').read_text(encoding='utf-8'))
        return 0
    try:
        if args.self_test:
            emit(self_test())
            return 0
        if not (2 <= args.width <= 3840 and 2 <= args.height <= 2160 and
                args.width % 2 == 0 and args.height % 2 == 0 and 1 <= args.fps <= 120):
            raise ValueError('Expected even dimensions up to 3840x2160 and fps in 1..120')
        import numpy as np
        import pyvirtualcam
        context = nullcontext(None) if args.dry_run else pyvirtualcam.Camera(
            args.width, args.height, args.fps, fmt=pyvirtualcam.PixelFormat.BGR, backend=args.backend)
        with context as camera:
            emit({'event': 'ready', 'device': 'Diagnostic stream (no camera)' if camera is None else camera.device,
                  'format': 'bgr24', 'width': args.width, 'height': args.height})
            def send(data: memoryview) -> None:
                if camera is not None:
                    camera.send(np.frombuffer(data, dtype=np.uint8).reshape(args.height, args.width, 3))
            stream(sys.stdin.buffer, args.width, args.height, send, emit, args.dry_run)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        try:
            emit({'event': 'error', 'message': f'{type(error).__name__}: {error}'[:600]})
        except (OSError, BrokenPipeError):
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
