"""Generic raw-video process adapter. GPL code is never imported into this process."""
from __future__ import annotations
import json
import os
from queue import Empty, Full, Queue
import subprocess
import sys
from threading import Event, Thread
from typing import BinaryIO
import numpy as np
from .paths import resource_root
from .system import hidden_process_flags, output_executable
from .scene import Frame


def output_command() -> list[str]:
    if getattr(sys, 'frozen', False):
        return [str(output_executable(resource_root() / 'video_output'))]
    return [sys.executable, '-I', str(resource_root() / 'camera_output' / 'main.py')]


def output_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
    # A frozen child is its own program, not a fork using the parent's bundle.
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return environment


def read_message(stream: BinaryIO) -> dict[str, object]:
    line = stream.readline(2049)
    if not line or len(line) > 2048 or not line.endswith(b'\n'):
        raise RuntimeError('O processo de saída encerrou ou retornou uma resposta inválida.')
    try:
        message = json.loads(line)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('Resposta inválida da saída de vídeo.') from error
    if not isinstance(message, dict):
        raise RuntimeError('Resposta inválida da saída de vídeo.')
    if message.get('event') == 'error':
        raise RuntimeError(str(message.get('message', 'Falha da câmera virtual.'))[:600])
    return message


def write_all(stream: BinaryIO, data: memoryview) -> None:
    offset = 0
    while offset < len(data):
        count = stream.write(data[offset:])
        if not count:
            raise BrokenPipeError('O processo de saída não recebeu o quadro.')
        offset += count


class VirtualOutput:
    """At most one frame in flight, bounded waits and confirmation after delivery."""
    def __init__(self, width: int, height: int, fps: int, backend: str,
                 *, dry_run: bool = False, timeout: float = 2.0, startup_timeout: float = 12.0) -> None:
        if backend not in ('obs', 'unitycapture') or not (2 <= width <= 3840 and 2 <= height <= 2160
                and width % 2 == 0 and height % 2 == 0 and 1 <= fps <= 120):
            raise ValueError('Formato de saída virtual inválido.')
        self.width, self.height = width, height
        self.timeout = timeout
        self.closed = Event()
        self.frames: Queue[Frame | None] = Queue(maxsize=1)
        self.responses: Queue[dict[str, object] | Exception] = Queue(maxsize=1)
        self.index = 0
        self.last_crc32: int | None = None
        command = output_command() + ['--width', str(width), '--height', str(height), '--fps', str(fps), '--backend', backend]
        if dry_run:
            command.append('--dry-run')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, env=output_environment(),
            creationflags=hidden_process_flags())
        self.thread = Thread(target=self._exchange, daemon=True, name='virtual-output-pipe')
        self.thread.start()
        try:
            message = self._wait(startup_timeout)
            if (message.get('event') != 'ready' or message.get('width') != width or message.get('height') != height
                    or message.get('format') != 'bgr24' or not isinstance(message.get('device'), str)):
                raise RuntimeError('A saída virtual não confirmou o formato solicitado.')
            self.device = str(message['device'])
        except Exception:
            self.close()
            raise

    def _exchange(self) -> None:
        try:
            if self.process.stdin is None or self.process.stdout is None:
                raise RuntimeError('Não foi possível criar o canal de vídeo.')
            self.responses.put_nowait(read_message(self.process.stdout))
            while True:
                frame = self.frames.get()
                if frame is None or self.closed.is_set():
                    self.process.stdin.close()
                    return
                write_all(self.process.stdin, memoryview(frame).cast('B'))
                self.responses.put_nowait(read_message(self.process.stdout))
        except Exception as error:
            try:
                self.responses.put_nowait(error)
            except Full:
                pass

    def _wait(self, timeout: float) -> dict[str, object]:
        try:
            result = self.responses.get(timeout=timeout)
        except Empty as error:
            raise RuntimeError('A saída virtual não respondeu a tempo. Use Reconectar saída.') from error
        if isinstance(result, Exception):
            raise RuntimeError(str(result)) from result
        return result

    def send(self, frame: Frame) -> None:
        if self.closed.is_set():
            raise RuntimeError('Saída de vídeo encerrada.')
        if frame.dtype != np.uint8 or frame.shape != (self.height, self.width, 3):
            raise ValueError('Quadro incompatível com a saída virtual.')
        try:
            self.frames.put_nowait(np.ascontiguousarray(frame))
            message = self._wait(self.timeout)
            self.index += 1
            if message.get('event') != 'frame' or message.get('index') != self.index:
                raise RuntimeError('A saída virtual não confirmou o quadro enviado.')
            checksum = message.get('crc32')
            self.last_crc32 = checksum if isinstance(checksum, int) else None
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            self.frames.put_nowait(None)
        except Full:
            pass
        try:
            self.process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        finally:
            self.thread.join(timeout=1)
            if self.process.stdin is not None:
                self.process.stdin.close()
            if self.process.stdout is not None:
                self.process.stdout.close()
