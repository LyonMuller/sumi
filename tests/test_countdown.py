import unittest
from threading import Event
from time import monotonic
from unittest.mock import Mock, patch

import numpy as np

from sumi.countdown import CAPTURE_FLASH, render_capture_flash, render_countdown
from sumi.effects import Silhouette
from sumi.engine import Engine, Settings
from sumi.scene import Scene


class CountdownOverlayTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((360, 640, 3), 90, np.uint8)

    def test_draws_big_number_without_touching_the_input(self):
        original = self.frame.copy()
        output = render_countdown(self.frame, 2.5, 5)
        self.assertEqual(output.shape, self.frame.shape)
        np.testing.assert_array_equal(self.frame, original)
        centre = output[130:230, 280:360]
        self.assertGreater((centre == 255).all(axis=2).mean(), .1)  # white digit strokes

    def test_flashes_right_after_each_new_second(self):
        just_ticked = render_countdown(self.frame, 2.95, 5).mean()
        mid_second = render_countdown(self.frame, 2.5, 5).mean()
        self.assertGreater(just_ticked, mid_second + 20)

    def test_capture_flash_fades_out(self):
        start = render_capture_flash(self.frame, 0).mean()
        later = render_capture_flash(self.frame, CAPTURE_FLASH / 2).mean()
        self.assertGreater(start, later)
        self.assertGreater(later, self.frame.mean())
        np.testing.assert_array_equal(render_capture_flash(self.frame, CAPTURE_FLASH), self.frame)


class EngineCountdownTests(unittest.TestCase):
    def run_engine(self, settings, frames, on_frame):
        ready = Event(); capture = Mock(); virtual = Mock(); sent = []; calls = 0
        def read():
            nonlocal calls
            ready.wait(3); calls += 1
            on_frame(engine, calls)
            if calls >= frames: engine.stop.set()
            return True, self.live.copy()
        capture.read.side_effect = read
        virtual.send.side_effect = lambda frame: sent.append(frame.copy())
        with patch('sumi.engine.Scene', return_value=self.scene), \
             patch.object(Engine, '_open_capture', return_value=capture), \
             patch.object(Engine, '_open_virtual', return_value=virtual), \
             patch.object(Engine, '_inference', return_value=None):
            engine = Engine(settings)
            ready.set(); engine.thread.join(5)
        self.assertFalse(engine.thread.is_alive())
        return engine, sent

    def test_calibration_shows_countdown_but_samples_raw_frames(self):
        self.scene = Scene(); self.scene.propose = Mock()
        self.live = np.full((180, 320, 3), 60, np.uint8)
        def step(engine, calls):
            if calls == 1: engine.commands.put('calibrate')
        engine, sent = self.run_engine(Settings(effect='instant', dynamic_background=False, capture_seconds=30),
                                       4, step)
        self.assertTrue(any(not np.array_equal(frame, self.live) for frame in sent))
        self.scene.propose.assert_not_called()  # 30 s countdown still running
        self.assertIn('30 s', engine.message)

    def test_snap_waits_for_the_configured_delay(self):
        self.scene = Scene()
        self.scene.background = np.full((180, 320, 3), 40, np.uint8)
        mask = np.zeros((180, 320), np.float32); mask[25:175, 115:205] = 1
        self.live = self.scene.background.copy(); self.live[mask > 0] = 180
        def step(engine, calls):
            with engine.lock:
                stamp = monotonic()
                engine.silhouette = Silhouette(stamp, self.live.copy(), mask.copy())
                engine.observation = (stamp, calls == 2, 1)
                engine.observation_effect = 'dust'
        engine, _ = self.run_engine(Settings(effect='dust', hold=2, dynamic_background=False, snap_delay=10), 6, step)
        self.assertFalse(self.scene.hidden)
        self.assertIn('Estalo', engine.message)


if __name__ == '__main__':
    unittest.main()
