from io import BytesIO
import json
import mmap
from pathlib import Path
from queue import Queue
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from sumi.controller import Controller
from sumi.service import (HEADER, HEADER_SIZE, MAGIC, SLOT_HEADER, SLOT_HEADER_SIZE, Outbox,
                                  PreviewBuffer, Service, read_commands)
from tests.test_controller import CAMERAS, FakeEngine

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def pause(self, seconds: float) -> None:
        self.now += max(seconds, 0.001)


def events(stream: BytesIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().decode('utf-8').splitlines()]


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.engines: list[FakeEngine] = []

        def factory(settings):
            engine = FakeEngine(settings)
            self.engines.append(engine)
            return engine
        self.opened = Mock()
        self.controller = Controller(preferences_path=self.folder / 'user_settings.json', engine_factory=factory,
                                     camera_lister=lambda: list(CAMERAS), bridge_factory=None,
                                     open_url=self.opened)
        self.controller.device_events.put((list(CAMERAS), ''))
        self.controller.accept_devices()

    def run_service(self, commands: list[dict | str], preview: PreviewBuffer | None = None) -> list[dict]:
        lines = b''.join((c if isinstance(c, str) else json.dumps(c)).encode() + b'\n' for c in commands)
        inbox: Queue = Queue()
        read_commands(BytesIO(lines), inbox)
        output = BytesIO()
        clock = Clock()
        code = Service(self.controller, Outbox(output), preview).run(inbox, clock, clock.pause, shutdown_timeout=0)
        result = events(output)
        result.append({'event': 'exit', 'code': code})
        return result

    def test_commands_reply_and_state_follows(self):
        result = self.run_service([
            {'id': 1, 'cmd': 'set_effect', 'value': 'Portal'},
            {'id': 2, 'cmd': 'set_effect', 'value': 'Nada'},
            {'id': 3, 'cmd': 'nao_existe'},
            'isto não é json',
            {'id': 4, 'cmd': 'shutdown'},
        ])
        self.assertEqual(result[0]['event'], 'hello')
        replies = {event['id']: event for event in result if event['event'] == 'reply'}
        self.assertTrue(replies[1]['ok'])
        self.assertFalse(replies[2]['ok'])
        self.assertEqual(replies[3]['error'], 'Comando desconhecido.')
        self.assertTrue(any(event['event'] == 'error' for event in result))
        self.assertEqual(result[-2]['event'], 'bye')

    def test_stdin_closing_stops_the_camera(self):
        result = self.run_service([{'id': 1, 'cmd': 'start_camera'}])
        self.assertTrue(self.engines[0].stop.is_set())
        self.assertEqual(result[-2], {'event': 'bye', 'stopped': False})
        self.assertEqual(result[-1]['code'], 1)

    def test_start_twice_is_rejected_instead_of_stopping(self):
        result = self.run_service([{'id': 1, 'cmd': 'start_camera'}, {'id': 2, 'cmd': 'start_camera'}])
        replies = {event['id']: event for event in result if event['event'] == 'reply'}
        self.assertTrue(replies[1]['ok'])
        self.assertFalse(replies[2]['ok'])
        self.assertEqual(len(self.engines), 1)

    def test_obs_download_is_delegated_to_the_shell(self):
        self.controller.devices = [CAMERAS[0]]
        result = self.run_service([{'id': 1, 'cmd': 'prepare_meet'}])
        self.opened.assert_called_once_with('https://obsproject.com/download')

    def test_preview_frames_are_mirrored_bgra_with_complete_sequence(self):
        preview = PreviewBuffer(self.folder / 'preview.bin', max_width=8, max_height=4)
        frame = np.zeros((4, 6, 3), np.uint8)
        frame[:, 0] = (10, 20, 30)
        slot, width, height = preview.write(frame, revision=5)
        self.assertEqual((slot, width, height), (0, 6, 4))
        with open(self.folder / 'preview.bin', 'rb') as stream:
            data = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
            magic, version, slots, max_width, max_height = HEADER.unpack_from(data, 0)
            self.assertEqual((magic, slots, max_width, max_height), (MAGIC, 2, 8, 4))
            sequence, revision, w, h, stride = SLOT_HEADER.unpack_from(data, HEADER_SIZE)
            self.assertEqual((sequence % 2, revision, w, h, stride), (0, 5, 6, 4, 24))
            pixels = np.frombuffer(data, np.uint8, h * stride, HEADER_SIZE + SLOT_HEADER_SIZE).reshape(h, w, 4)
            self.assertEqual(tuple(pixels[0, -1]), (10, 20, 30, 255))
            del pixels
            data.close()
        self.assertEqual(preview.write(frame, revision=6)[0], 1)
        preview.close()

    def test_running_camera_publishes_preview_events(self):
        preview = PreviewBuffer(self.folder / 'preview.bin', max_width=8, max_height=4)
        result = self.run_service([{'id': 1, 'cmd': 'start_camera'}, {'id': 2, 'cmd': 'shutdown'}], preview)
        preview.close()
        frames = [event for event in result if event['event'] == 'preview']
        self.assertEqual(frames[0]['revision'], 3)
        with open(self.folder / 'preview.bin', 'rb') as stream:
            data = stream.read()
        numbers = [SLOT_HEADER.unpack_from(data, HEADER_SIZE + slot * preview.slot_bytes)[1] for slot in range(2)]
        self.assertEqual(max(numbers), len(frames), 'slots carry a frame number that keeps growing')
        states = [event['state'] for event in result if event['event'] == 'state']
        self.assertTrue(states[-1]['running'])


    def test_loop_wakes_on_frames_instead_of_sleeping(self):
        waits: list[float] = []

        def wait(timeout: float) -> bool:
            waits.append(timeout)
            return True
        inbox: Queue = Queue()
        read_commands(BytesIO(b'{"id": 1, "cmd": "shutdown"}\n'), inbox)
        clock = Clock()
        pause = Mock(side_effect=clock.pause)
        Service(self.controller, Outbox(BytesIO()), None).run(inbox, clock, pause, shutdown_timeout=0, wait=wait)
        self.assertEqual(waits, [], 'shutdown first: loop ends without waiting')
        inbox = Queue()
        inbox.put({'id': 1, 'cmd': 'refresh_cameras'})
        def stop_after_wait(timeout: float) -> bool:
            waits.append(timeout)
            inbox.put(None)
            return True
        Service(self.controller, Outbox(BytesIO()), None).run(inbox, clock, pause, shutdown_timeout=0,
                                                             wait=stop_after_wait)
        self.assertEqual(len(waits), 1)
        self.assertLessEqual(waits[0], 1 / 30)
        pause.assert_not_called()


class ServiceProcessTests(unittest.TestCase):
    def test_real_process_says_hello_and_exits_when_stdin_closes(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                [sys.executable, '-B', str(ROOT / 'main.py'), '--service', '--no-meet',
                 '--preview', str(Path(folder) / 'preview.bin')],
                input=b'{"id":1,"cmd":"shutdown"}\n', capture_output=True, timeout=60, cwd=folder)
        lines = [json.loads(line) for line in process.stdout.decode().splitlines()]
        self.assertEqual(process.returncode, 0, process.stderr.decode()[-2000:])
        self.assertEqual(lines[0]['event'], 'hello')
        self.assertEqual(lines[0]['preview']['format'], 'bgra')
        self.assertEqual(lines[-1], {'event': 'bye', 'stopped': True})


if __name__ == '__main__':
    unittest.main()
