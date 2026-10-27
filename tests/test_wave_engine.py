"""Engine wiring of the energy wave: a ball while charging, a one-shot beam, and the person never hides."""
import unittest
from threading import Event, Thread
from time import monotonic
from unittest.mock import Mock, patch

import cv2
import numpy as np

from sumi.engine import Engine, Settings
from sumi.effects import Silhouette
from sumi.scene import Scene
from sumi.vision import Detector

H, W = 180, 320
BALL = (230., 130., 36.)
FIRE = (170., 118., 52.)


class WaveEngineTests(unittest.TestCase):
    def run_engine(self, script, frames=150, hands=None, effect='kamehameha', fps=60):
        """`hands(call)` -> (charging, charge, ball, pulse) or None; `script` maps call number -> command."""
        background = np.full((H, W, 3), 90, np.uint8)
        mask = np.zeros((H, W), np.float32)
        cv2.ellipse(mask, (110, 120), (42, 70), 0, 0, 360, 1, -1)
        live = background.copy()
        live[mask > .5] = (200, 120, 60)
        scene = Scene()
        scene.background = background.copy()
        capture, virtual = Mock(), Mock()
        sent, states, silhouettes = [], [], []
        calls = 0
        ready = Event()

        def read():
            nonlocal calls
            ready.wait(3)
            calls += 1
            stamp = monotonic()
            with engine.lock:
                engine.silhouette = Silhouette(stamp, live.copy(), mask.copy())
                if hands is not None:
                    seen = hands(calls)
                    charging, charge, ball, pulse = seen if seen is not None else (False, 0.0, None, False)
                    engine.wave_obs = (stamp, charging, charge, ball)
                    engine.observation = (stamp, pulse, 1)
                    engine.observation_effect = effect
                    engine.gesture_progress = charge if charging else 0.0
            if calls in script:
                engine.commands.put(script[calls])
            if calls >= frames:
                engine.stop.set()
            return True, live.copy()

        def send(frame):
            sent.append(frame.copy())
            states.append((engine.hidden, engine.phase, engine.charging, engine.message, engine.progress, engine.clones))
            silhouettes.append(engine.need_silhouette.is_set())

        capture.read.side_effect = read
        virtual.send.side_effect = send
        with patch('sumi.engine.Scene', return_value=scene), \
             patch.object(Engine, '_open_capture', return_value=capture), \
             patch.object(Engine, '_open_virtual', return_value=virtual), \
             patch.object(Engine, '_inference', return_value=None):
            engine = Engine(Settings(effect=effect, hold=.6, fps=fps, dynamic_background=False))
            ready.set()
            engine.thread.join(30)
        self.assertFalse(engine.thread.is_alive())
        self.assertEqual(len(states), frames, (engine.phase, engine.message))
        return engine, live, sent, states, silhouettes

    @staticmethod
    def shot(charge_from=5, fire_at=60):
        """Charge from call `charge_from`, push at `fire_at`, hands stay up a while, then relax."""
        def hands(call):
            if charge_from <= call < fire_at:
                return True, min(1.0, (call - charge_from) / 50), BALL, False
            if call == fire_at:
                return False, 1.0, FIRE, True
            if fire_at < call < fire_at + 20:
                return False, 0.0, FIRE, False
            return None
        return hands

    def test_charge_shows_the_ball_then_the_push_fires_and_the_live_frame_returns(self):
        engine, live, sent, states, needs = self.run_engine({}, frames=190, hands=self.shot())
        self.assertFalse(any(hidden or phase == 'hidden' for hidden, phase, *_ in states))
        self.assertTrue(engine.disappearances.empty())
        self.assertFalse(engine.hidden)
        charging = [i for i, state in enumerate(states) if state[2]]
        self.assertGreater(len(charging), 30)
        self.assertTrue(all(states[i][1] == 'holding' for i in charging))
        self.assertTrue(all(states[i][1] != 'teleporting' for i in charging))
        self.assertTrue(all(np.any(sent[i] != live) for i in charging[10:]))           # the ball is drawn
        self.assertTrue(all(needs[i] for i in charging))                               # silhouette requested for the glow
        self.assertTrue(any('Carregando a onda' in state[3] for state in states))
        self.assertGreater(states[charging[-1]][4], .5)                               # progress bar = charge
        firing = [i for i, state in enumerate(states) if state[1] == 'teleporting']
        self.assertGreater(len(firing), 40)
        self.assertGreater(firing[0], charging[-1] - 3)
        self.assertTrue(any('Onda disparada!' == states[i][3] for i in firing))
        self.assertTrue(all(np.any(sent[i] != live) for i in firing[3:-3]))
        self.assertFalse(any(state[2] for i, state in enumerate(states) if i in firing))     # the ball is gone while firing
        np.testing.assert_array_equal(sent[0], live)
        np.testing.assert_array_equal(sent[-1], live)
        self.assertIn('Onda disparada', engine.message)
        self.assertEqual(states[-1][1], 'ready')

    def test_dropping_the_pose_without_a_push_fizzles_and_never_fires(self):
        def hands(call):
            return (True, min(1.0, call / 40), BALL, False) if 5 <= call < 50 else None
        engine, live, sent, states, _ = self.run_engine({}, frames=110, hands=hands)
        self.assertFalse(any(state[1] == 'teleporting' for state in states))
        self.assertTrue(any('A onda se desfez' in state[3] for state in states))
        self.assertFalse(any(state[0] for state in states))
        np.testing.assert_array_equal(sent[-1], live)
        self.assertFalse(engine.charging)

    def test_the_manual_button_fires_the_wave_without_hands_and_does_not_hide_anyone(self):
        engine, live, sent, states, _ = self.run_engine({5: 'toggle'}, frames=130)
        firing = [i for i, state in enumerate(states) if state[1] == 'teleporting']
        self.assertGreater(len(firing), 40)
        self.assertTrue(any(np.any(sent[i] != live) for i in firing))
        self.assertFalse(any(state[0] for state in states))
        self.assertTrue(engine.disappearances.empty())
        np.testing.assert_array_equal(sent[-1], live)

    def test_a_second_push_while_firing_is_ignored_and_restore_cancels_the_shot(self):
        def hands(call):
            first = self.shot()(call)
            return (False, 1.0, FIRE, True) if call in (70, 71) else first
        engine, live, sent, states, _ = self.run_engine({}, frames=190, hands=hands)
        firing = [i for i, state in enumerate(states) if state[1] == 'teleporting']
        self.assertEqual(firing, list(range(firing[0], firing[-1] + 1)))              # one continuous shot
        engine, live, sent, states, _ = self.run_engine({80: 'restore'}, frames=100, hands=self.shot())
        np.testing.assert_array_equal(sent[-1], live)
        self.assertFalse(any(state[0] for state in states))
        self.assertLess(sum(state[1] == 'teleporting' for state in states), 30)

    def test_with_clones_standing_the_gestures_belong_to_the_clones(self):
        script = {3: 'effect:clones', 6: 'toggle', 70: 'effect:kamehameha'}
        engine, live, sent, states, _ = self.run_engine(script, frames=170, hands=lambda call: self.shot(100, 130)(call) if call > 70 else None)
        self.assertTrue(states[-1][5])                                                # clones are still on
        self.assertFalse(any('Onda disparada' in state[3] for state in states))
        self.assertFalse(any(state[2] for state in states))                           # no ball while clones stand
        self.assertFalse(any(state[0] for state in states))

    def test_the_first_frame_without_a_silhouette_does_not_stop_the_shot(self):
        def hands(call):
            return (False, 1.0, FIRE, True) if call == 8 else None
        engine, live, sent, states, _ = self.run_engine({}, frames=120, hands=hands)
        # Fresh silhouettes arrive on every read in this harness; the shot must start immediately on the pulse.
        first = next(i for i, state in enumerate(states) if state[1] == 'teleporting')
        self.assertLessEqual(first, 12)


class FakeDetector:
    """A stand-in for the MediaPipe landmarkers: the faces and hands are scripted per call."""
    def __init__(self, faces, hands):
        self.faces, self.hands = faces, hands

    def detect_for_video(self, image, timestamp):
        return Mock(detections=self.faces, hand_landmarks=self.hands)


class DetectorScaleTests(unittest.TestCase):
    def test_the_ball_comes_back_in_full_frame_pixels_and_the_wave_fields_reset(self):
        from tests.test_wave_gesture import cupped, FACE
        frame = np.zeros((720, 1280, 3), np.uint8)
        # The detector works on a 640 px wide copy with normalised landmarks: express the fixture hands that way.
        small_w, small_h = 640, 360
        scale = 2.0                                               # frame / small
        hands_small = cupped(x=330, y=330, palm=45)
        normalised = [[Mock(x=p.x / small_w, y=p.y / small_h) for p in hand] for hand in hands_small]
        box = Mock(origin_x=FACE.x, origin_y=FACE.y, width=FACE.width, height=FACE.height)
        faces = [Mock(bounding_box=box)]
        detector = Detector.__new__(Detector)
        from sumi.recognition import GestureRecognizer
        detector.timestamp = -1
        detector.recognizer, detector.extra_recognizer = GestureRecognizer(), GestureRecognizer()
        detector.extra_matched, detector.progress, detector.hint = False, 0.0, ''
        detector._no_wave()
        detector.face = FakeDetector(faces, [])
        detector.hand = FakeDetector(faces, [])
        for i in range(12):                                       # arm: no hands for a while
            detector.detect(frame, 10 + i / 30, 'kamehameha')
        self.assertFalse(detector.charging)
        detector.hand = FakeDetector(faces, normalised)
        for i in range(12, 40):
            matched, faces_seen = detector.detect(frame, 10 + i / 30, 'kamehameha')
        self.assertFalse(matched)
        self.assertEqual(faces_seen, 1)
        self.assertTrue(detector.charging)
        self.assertGreater(detector.charge, .5)
        x, y, size = detector.ball
        from sumi.recognition import wave_ball
        expected = wave_ball(hands_small, FACE)
        self.assertAlmostEqual(x, expected.x * scale, delta=1)
        self.assertAlmostEqual(y, expected.y * scale, delta=1)
        self.assertAlmostEqual(size, expected.size * scale, delta=1)
        detector.detect(frame, 20, 'portal')                       # any other effect: nothing reported
        self.assertFalse(detector.charging)
        self.assertEqual(detector.charge, 0.0)
        detector.face = FakeDetector([], [])
        detector.detect(frame, 21, 'kamehameha')
        self.assertIsNone(detector.ball)


class PulseLatchTests(unittest.TestCase):
    def test_a_motion_pulse_survives_until_the_render_loop_has_seen_it(self):
        frame = np.zeros((18, 32, 3), np.uint8)
        outcomes = iter([(False, 1), (True, 1), (False, 1), (False, 1)])
        detector = Mock()
        detector.detect.side_effect = lambda *args: next(outcomes)
        detector.charging, detector.charge, detector.ball = False, 0.0, None
        detector.extra_matched, detector.progress, detector.hint = False, 0.0, ''
        with patch.object(Engine, '_run', return_value=None), \
             patch('sumi.engine.Detector', return_value=detector), \
             patch('sumi.engine.Segmenter', side_effect=RuntimeError('none')):
            engine = Engine(Settings(effect='dust', dynamic_background=False))
            engine.thread.join(1)
            worker = Thread(target=engine._inference, daemon=True)
            worker.start()
            try:
                def feed(stamp):
                    with engine.lock:
                        engine.raw = (stamp, frame)
                    deadline = monotonic() + 3
                    while engine.observation[0] < stamp and monotonic() < deadline:
                        engine.stop.wait(.005)
                    self.assertEqual(engine.observation[0], stamp)
                feed(1.0)
                self.assertEqual(engine.wave_obs, (1.0, False, 0.0, None))
                feed(1.03)
                self.assertTrue(engine.observation[1])
                feed(1.06)                      # the render loop has not looked yet: the pulse is kept
                self.assertTrue(engine.observation[1])
                engine.observation_seen = engine.observation[0]
                feed(1.09)                      # looked at it: nothing is repeated
                self.assertFalse(engine.observation[1])
            finally:
                engine.stop.set()
                worker.join(2)


if __name__ == '__main__':
    unittest.main()
