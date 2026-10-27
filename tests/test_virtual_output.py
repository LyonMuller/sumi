from io import BytesIO
from pathlib import Path
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import zlib
import numpy as np

from camera_output.main import read_frame, stream
from sumi.virtual_output import VirtualOutput, output_command, output_environment, read_message


class RawVideoTests(unittest.TestCase):
    def test_partial_pipe_reads_are_assembled_and_eof_is_clean(self):
        class Partial(BytesIO):
            def readinto(self, buffer):
                return super().readinto(buffer[:3])
        source = Partial(b'abcdefghi')
        frame = bytearray(9)
        self.assertTrue(read_frame(source, frame))
        self.assertEqual(frame, b'abcdefghi')
        self.assertFalse(read_frame(source, frame))

    def test_incomplete_frame_is_never_sent(self):
        sent, replies = [], []
        with self.assertRaises(EOFError):
            stream(BytesIO(b'too short'), 4, 4, lambda data: sent.append(bytes(data)), replies.append)
        self.assertEqual(sent, [])
        self.assertEqual(replies, [])

    def test_ack_is_emitted_only_after_the_sink_accepts_the_frame(self):
        events = []
        stream(BytesIO(bytes(12)), 2, 2, lambda data: events.append('sent'), lambda message: events.append(message['event']))
        self.assertEqual(events, ['sent', 'frame'])
        replies = []
        def failed_send(data):
            raise RuntimeError('output failed')
        with self.assertRaises(RuntimeError):
            stream(BytesIO(bytes(12)), 2, 2, failed_send, replies.append)
        self.assertEqual(replies, [])

    def test_protocol_rejects_large_invalid_and_error_replies(self):
        for message in (b'x' * 2049, b'not json\n', b'[]\n', b'', b'{"event":"error","message":"failed"}\n'):
            with self.subTest(message=message[:30]):
                with self.assertRaises(RuntimeError):
                    read_message(BytesIO(message))

    def test_frozen_child_uses_its_own_bundle_environment(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', 'C:/package', create=True), \
             patch.object(sys, 'platform', 'win32'):
            self.assertEqual(Path(output_command()[0]), Path('C:/package/video_output/SumiVideoOutput.exe'))
        self.assertEqual(output_environment()['PYINSTALLER_RESET_ENVIRONMENT'], '1')


class OutputProcessTests(unittest.TestCase):
    def test_real_process_stream_preserves_pixels_and_closes_without_orphans(self):
        output = VirtualOutput(640, 480, 30, 'obs', dry_run=True)
        try:
            frame = np.arange(480 * 640 * 3, dtype=np.uint8).reshape(480, 640, 3)
            for image in (frame, frame[:, ::-1]):
                output.send(image)
                self.assertEqual(output.last_crc32, zlib.crc32(np.ascontiguousarray(image)))
            self.assertEqual(output.index, 2)
            self.assertIn('no camera', output.device)
        finally:
            output.close()
            output.close()
        self.assertIsNotNone(output.process.poll())
        self.assertFalse(output.thread.is_alive())

    def test_dead_output_is_reported_and_a_new_output_can_connect(self):
        output = VirtualOutput(16, 16, 30, 'obs', dry_run=True)
        output.process.kill()
        output.process.wait(timeout=2)
        with self.assertRaises(RuntimeError):
            output.send(np.zeros((16, 16, 3), np.uint8))
        output.close()
        replacement = VirtualOutput(16, 16, 30, 'obs', dry_run=True)
        try:
            replacement.send(np.zeros((16, 16, 3), np.uint8))
        finally:
            replacement.close()

    def test_unresponsive_startup_has_a_deadline(self):
        command = [sys.executable, '-I', '-c', 'import time; time.sleep(20)']
        began = time.monotonic()
        with patch('sumi.virtual_output.output_command', return_value=command):
            with self.assertRaises(RuntimeError):
                VirtualOutput(16, 16, 30, 'obs', startup_timeout=.1)
        self.assertLess(time.monotonic() - began, 4)

    def test_stream_that_stops_reading_cannot_hang_the_video_thread(self):
        ready = json.dumps({'event': 'ready', 'device': 'test', 'format': 'bgr24', 'width': 1280, 'height': 720})
        code = f'import time; print({ready!r}, flush=True); time.sleep(20)'
        command = [sys.executable, '-I', '-c', code]
        with patch('sumi.virtual_output.output_command', return_value=command):
            output = VirtualOutput(1280, 720, 30, 'obs', timeout=.1)
        began = time.monotonic()
        with self.assertRaises(RuntimeError):
            output.send(np.zeros((720, 1280, 3), np.uint8))
        self.assertLess(time.monotonic() - began, 4)
        self.assertIsNotNone(output.process.poll())
        self.assertFalse(output.thread.is_alive())

    def test_worker_imports_no_application_or_apache_video_dependencies(self):
        completed = subprocess.run(output_command() + ['--self-test'], capture_output=True, check=True, timeout=15)
        result = json.loads(completed.stdout)
        self.assertTrue(result['ok'])
        self.assertEqual(result['forbidden_imports'], [])
        self.assertFalse(result['camera_opened'])
