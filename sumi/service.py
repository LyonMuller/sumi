"""Headless engine service for a native shell (the macOS SwiftUI app).

Protocol, one UTF-8 JSON object per line:

* stdin, commands: ``{"id": 7, "cmd": "set_effect", "value": "Portal"}``.
* stdout, events: ``hello``, ``reply`` (``id``, ``ok``, optional ``error``/``value``),
  ``state`` (full public ``ViewState`` when it changes), ``preview`` (slot ready),
  ``open_url`` and ``error``.

Preview frames go through a memory-mapped file instead of the pipe. Layout, little-endian:

* Header, 64 bytes: magic ``SUMIPRV1``, u32 version, u32 slots, u32 max width,
  u32 max height, zero padding.
* Each slot: 64-byte header (u64 sequence, u64 frame number, u32 width, u32 height,
  u32 bytes per row, padding) followed by ``max_width * max_height * 4`` bytes of BGRA.

The sequence is odd while a slot is being written and even when complete. A reader
copies the pixels only when the sequence is even and unchanged after the copy. The frame
number only grows while the file exists (also across camera restarts), so the slot with
the highest one is always the newest frame.
Stdin closing means the shell is gone: the service stops the camera and exits.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
from queue import Empty, Queue
import struct
import sys
from threading import Thread
from time import monotonic, sleep
from typing import BinaryIO, Callable

import cv2
import numpy as np

from . import __version__
from .controller import Controller
from .paths import resource_root

PROTOCOL = 1
MAGIC = b'SUMIPRV1'
HEADER = struct.Struct('<8sIIII')
SLOT_HEADER = struct.Struct('<QQIII')
HEADER_SIZE = 64
SLOT_HEADER_SIZE = 64
MAX_LINE = 64 * 1024
TICK = 1 / 30
COMMANDS_WITH_VALUE = {
    'set_camera': 'set_camera', 'set_effect': 'set_effect', 'set_resolution': 'set_resolution',
    'set_hold': 'set_hold', 'set_output': 'set_output', 'set_leave_delay': 'set_leave_delay',
}
ENGINE_COMMANDS = ('restore', 'calibrate', 'confirm', 'toggle', 'virtual')


class PreviewBuffer:
    """Double-buffered BGRA frames in a file the native shell maps read-only."""
    def __init__(self, path: Path, max_width: int = 1280, max_height: int = 720, slots: int = 2) -> None:
        self.path = path
        self.max_width, self.max_height, self.slots = max_width, max_height, slots
        self.slot_bytes = SLOT_HEADER_SIZE + max_width * max_height * 4
        size = HEADER_SIZE + slots * self.slot_bytes
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.ftruncate(descriptor, size)
            self.map = mmap.mmap(descriptor, size)
        finally:
            os.close(descriptor)
        self.map[:HEADER.size] = HEADER.pack(MAGIC, PROTOCOL, slots, max_width, max_height)
        self.sequences = [0] * slots
        self.next_slot = 0

    def describe(self) -> dict[str, object]:
        return {'path': str(self.path), 'slots': self.slots, 'max_width': self.max_width,
                'max_height': self.max_height, 'format': 'bgra', 'header_bytes': HEADER_SIZE,
                'slot_header_bytes': SLOT_HEADER_SIZE, 'slot_bytes': self.slot_bytes}

    def write(self, frame: np.ndarray, revision: int) -> tuple[int, int, int]:
        """Mirror like a selfie view, fit inside the maximum size and publish one slot."""
        height, width = frame.shape[:2]
        scale = min(1.0, self.max_width / width, self.max_height / height)
        if scale < 1.0:
            frame = cv2.resize(frame, (max(2, round(width * scale)), max(2, round(height * scale))),
                               interpolation=cv2.INTER_AREA)
        pixels = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2BGRA)
        height, width = pixels.shape[:2]
        slot = self.next_slot
        self.next_slot = (slot + 1) % self.slots
        start = HEADER_SIZE + slot * self.slot_bytes
        sequence = self.sequences[slot] + 1
        self.map[start:start + 8] = struct.pack('<Q', sequence)
        data = start + SLOT_HEADER_SIZE
        self.map[data:data + pixels.nbytes] = pixels.tobytes()
        sequence += 1
        self.sequences[slot] = sequence
        self.map[start:start + SLOT_HEADER.size] = SLOT_HEADER.pack(sequence, revision, width, height, width * 4)
        return slot, width, height

    def close(self) -> None:
        self.map.close()


@dataclass
class Outbox:
    stream: BinaryIO

    def send(self, message: dict[str, object]) -> None:
        line = json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n'
        self.stream.write(line.encode('utf-8'))
        self.stream.flush()


def read_commands(stream: BinaryIO, inbox: Queue[dict[str, object] | Exception | None]) -> None:
    try:
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                inbox.put(ValueError('Comando longo demais.'))
                continue
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError):
                inbox.put(ValueError('Comando inválido.'))
                continue
            inbox.put(message if isinstance(message, dict) else ValueError('Comando inválido.'))
    finally:
        inbox.put(None)


class Service:
    def __init__(self, controller: Controller, outbox: Outbox, preview: PreviewBuffer | None) -> None:
        self.controller = controller
        self.outbox = outbox
        self.preview = preview
        self.last_state: dict[str, object] | None = None
        self.preview_revision = -1
        self.frame_number = 0
        self.finished = False

    def hello(self) -> None:
        self.outbox.send({'event': 'hello', 'protocol': PROTOCOL, 'version': __version__,
                          'resources': str(resource_root()),
                          'preview': None if self.preview is None else self.preview.describe()})

    def handle(self, message: dict[str, object]) -> None:
        identifier = message.get('id')
        command = message.get('cmd')
        try:
            value = self.dispatch(command, message)
        except (ValueError, TypeError, KeyError) as error:
            self.outbox.send({'event': 'reply', 'id': identifier, 'ok': False, 'error': str(error)})
            return
        reply: dict[str, object] = {'event': 'reply', 'id': identifier, 'ok': True}
        if value is not None:
            reply['value'] = value
        self.outbox.send(reply)

    def dispatch(self, command: object, message: dict[str, object]) -> object:
        controller = self.controller
        if command in COMMANDS_WITH_VALUE:
            value = message.get('value')
            if not isinstance(value, str):
                raise ValueError('Valor ausente.')
            getattr(controller, COMMANDS_WITH_VALUE[command])(value)
        elif command == 'set_background':
            controller.set_background(bool(message.get('dynamic')))
        elif command == 'set_leave':
            controller.set_leave(bool(message.get('enabled')))
        elif command == 'refresh_cameras':
            controller.refresh_devices()
        elif command == 'start_camera':
            if controller.engine is not None and controller.engine.thread.is_alive():
                raise ValueError('A câmera já está ligada.')
            controller.start()
            if controller.engine is None or not controller.engine.thread.is_alive():
                raise ValueError(controller.status)
        elif command == 'stop_camera':
            controller.stop()
        elif command == 'primary':
            controller.primary_action()
        elif command == 'engine':
            name = message.get('name')
            if name not in ENGINE_COMMANDS:
                raise ValueError('Comando do motor desconhecido.')
            controller.command(str(name))
        elif command == 'prepare_meet':
            controller.prepare_meet()
        elif command == 'set_sounds':
            controller.set_sounds(bool(message.get('enabled')))
        elif command == 'set_call_sounds':
            controller.set_call_sounds(bool(message.get('enabled')))
        elif command == 'extension_path':
            folder = controller.extension_path()
            if folder is None:
                raise ValueError(controller.leave_note)
            return str(folder)
        elif command == 'shutdown':
            self.finished = True
        else:
            raise ValueError('Comando desconhecido.')
        return None

    def publish(self) -> None:
        state = self.controller.tick()
        public = state.public()
        if public != self.last_state:
            self.last_state = public
            self.outbox.send({'event': 'state', 'state': public})
        if (self.preview is not None and state.frame is not None
                and state.preview_revision != self.preview_revision):
            self.preview_revision = state.preview_revision
            self.frame_number += 1
            slot, width, height = self.preview.write(state.frame, self.frame_number)
            self.outbox.send({'event': 'preview', 'slot': slot, 'revision': state.preview_revision,
                              'width': width, 'height': height})

    def run(self, inbox: Queue[dict[str, object] | Exception | None],
            clock: Callable[[], float] = monotonic, pause: Callable[[float], None] = sleep,
            shutdown_timeout: float = 5.0, wait: Callable[[float], bool] | None = None) -> int:
        # Wake as soon as the engine has a frame; two independent 30 Hz clocks made
        # the preview repeat and skip frames. The timeout keeps commands responsive.
        wait = wait or self.controller.wait_for_frame
        self.hello()
        self.publish()
        while not self.finished:
            began = clock()
            while True:
                try:
                    item = inbox.get_nowait()
                except Empty:
                    break
                if item is None:
                    self.finished = True
                    break
                if isinstance(item, Exception):
                    self.outbox.send({'event': 'error', 'message': str(item)})
                else:
                    self.handle(item)
            self.publish()
            if not self.finished:
                if not wait(max(0.0, TICK - (clock() - began))):
                    # No frame: sleep only what is left (nothing after a full timeout).
                    pause(max(0.0, TICK - (clock() - began)))
        self.controller.close()
        deadline = clock() + shutdown_timeout
        while not self.controller.stopped() and clock() < deadline:
            pause(0.05)
        try:
            self.outbox.send({'event': 'bye', 'stopped': self.controller.stopped()})
        except (OSError, ValueError):
            pass
        return 0 if self.controller.stopped() else 1


def protocol_stdout() -> BinaryIO:
    """Reserve the real stdout for protocol lines; stray prints and native logs go to stderr."""
    descriptor = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(descriptor, 'wb', buffering=0)


def main(preview_path: Path | None, meet: bool = True) -> int:
    output = protocol_stdout()
    inbox: Queue[dict[str, object] | Exception | None] = Queue()
    outbox = Outbox(output)
    preview = PreviewBuffer(preview_path) if preview_path is not None else None
    controller_options: dict[str, object] = {'open_url': lambda url: outbox.send({'event': 'open_url', 'url': url})}
    if not meet:
        controller_options['bridge_factory'] = None
    controller = Controller(**controller_options)  # type: ignore[arg-type]
    controller.refresh_devices()
    Thread(target=read_commands, args=(sys.stdin.buffer, inbox), daemon=True, name='service-input').start()
    try:
        return Service(controller, outbox, preview).run(inbox)
    except BrokenPipeError:
        # The shell went away while we were writing; still release the camera.
        controller.close()
        return 1
    finally:
        if preview is not None:
            preview.close()
