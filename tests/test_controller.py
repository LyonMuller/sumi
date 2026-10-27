from pathlib import Path
from queue import Queue
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

import numpy as np

from sumi.controller import Controller
from sumi.devices import CameraDevice
from sumi.preferences import load_preferences


class FakeThread:
    def __init__(self) -> None:
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive


class FakeEngine:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.running = True
        self.phase = 'uncalibrated'
        self.hidden = False
        self.thread = FakeThread()
        self.stop = Event()
        self.commands: Queue[str] = Queue()
        self.disappearances: Queue[tuple[float, bool]] = Queue()
        self.preview_revision = 3
        self.progress = 0.25
        self.vision_hint = 'Mostre o rosto e uma mão.'
        self.effect_error = ''
        self.gesture_error = ''
        self.gesture_release_required = False
        self.message = 'Câmera aberta'
        self.virtual_active = False

    def snapshot(self):
        return np.zeros((4, 6, 3), np.uint8), 'Câmera aberta', 29.5

    def _set_message(self, text: str) -> None:
        self.message = text


CAMERAS = [CameraDevice(0, 'FaceTime HD Camera', 'facetime', 1200),
           CameraDevice(1, 'OBS Virtual Camera', 'obs', 1200)]


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = Path(self.folder.name) / 'user_settings.json'
        self.engines: list[FakeEngine] = []

    def make(self) -> Controller:
        def factory(settings):
            engine = FakeEngine(settings)
            self.engines.append(engine)
            return engine
        controller = Controller(preferences_path=self.settings, engine_factory=factory,
                                camera_lister=lambda: list(CAMERAS), bridge_factory=None, open_url=Mock())
        controller.refresh_devices()
        for _ in range(200):
            if controller.accept_devices():
                break
            Event().wait(0.01)
        return controller

    def test_real_camera_is_selected_before_virtual_ones(self):
        controller = self.make()
        state = controller.tick()
        self.assertEqual(state.camera, 'FaceTime HD Camera · 0')
        self.assertEqual(state.primary_label, 'Iniciar câmera')
        self.assertTrue(state.primary_enabled)
        self.assertFalse(state.running)

    def test_start_creates_engine_with_chosen_options_and_saves_them(self):
        controller = self.make()
        controller.set_resolution('640 × 480')
        controller.set_background(True)
        with patch.object(sys, 'platform', 'darwin'):
            controller.set_output('Só prévia')
            controller.start()
        settings = self.engines[0].settings
        self.assertEqual((settings.width, settings.height, settings.virtual), (640, 480, 'off'))
        self.assertTrue(settings.dynamic_background)
        saved = load_preferences(self.settings)
        self.assertEqual(saved['camera_path'], 'facetime')
        self.assertEqual(saved['background'], 'live')
        # The next launch keeps the chosen background instead of resetting it.
        self.assertEqual(Controller(preferences_path=self.settings, bridge_factory=None).dynamic, True)

    def test_running_state_drives_primary_action_and_locks_inputs(self):
        controller = self.make()
        controller.start()
        state = controller.tick()
        self.assertEqual(state.primary_label, 'Capturar fundo (4 s)')
        self.assertFalse(state.inputs_enabled)
        self.assertEqual(state.start_label, 'Parar câmera')
        self.assertEqual(state.performance, '29.5 FPS · Teleporte anime')
        self.assertEqual(state.frame.shape, (4, 6, 3))
        controller.primary_action()
        self.assertEqual(self.engines[0].commands.get_nowait(), 'calibrate')
        with self.assertRaises(ValueError):
            controller.set_resolution('640 × 480')

    def test_stop_and_close_wait_for_engine_thread(self):
        controller = self.make()
        controller.start()
        controller.close()
        engine = self.engines[0]
        self.assertTrue(engine.stop.is_set())
        self.assertEqual(controller.tick().start_label, 'Parando…')
        self.assertFalse(controller.stopped())
        engine.running = False
        engine.thread.alive = False
        self.assertTrue(controller.stopped())
        self.assertEqual(controller.tick().start_label, 'Iniciar câmera')

    def test_effect_change_reaches_running_engine_and_is_saved(self):
        controller = self.make()
        controller.start()
        controller.set_effect('Portal')
        self.assertEqual(self.engines[0].commands.get_nowait(), 'effect:portal')
        self.assertEqual(load_preferences(self.settings)['effect'], 'Portal')
        with self.assertRaises(ValueError):
            controller.set_effect('Inexistente')

    def test_no_camera_points_to_system_permission(self):
        controller = Controller(preferences_path=self.settings, camera_lister=lambda: [], bridge_factory=None)
        with patch.object(sys, 'platform', 'darwin'):
            controller.refresh_devices()
            while not controller.accept_devices():
                Event().wait(0.01)
        state = controller.tick()
        self.assertEqual(state.camera, 'Nenhuma webcam encontrada')
        self.assertIn('Privacidade e Segurança', state.hint)
        self.assertFalse(state.primary_enabled)

    def test_public_state_is_json_ready(self):
        import json
        controller = self.make()
        controller.start()
        data = controller.tick().public()
        self.assertNotIn('frame', data)
        json.dumps(data)

    def test_wait_for_frame_wakes_on_new_engine_frame(self):
        controller = self.make()
        self.assertFalse(controller.wait_for_frame(0.01), 'no camera: nothing to wait for')
        controller.start()
        engine = self.engines[0]
        engine.frame_ready = Event()
        self.assertFalse(controller.wait_for_frame(0.01))
        engine.frame_ready.set()
        self.assertTrue(controller.wait_for_frame(1.0))
        self.assertFalse(engine.frame_ready.is_set(), 'the signal is consumed')


if __name__ == '__main__':
    unittest.main()
