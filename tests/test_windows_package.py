from pathlib import Path
import json
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from sumi.paths import data_root, resource_root, extension_folder
from sumi.preferences import load_preferences, save_preferences
from tools.build_windows import check_inventory


class WindowsPackageTests(unittest.TestCase):
    def test_background_upgrade_switches_once_and_then_respects_the_choice(self):
        from sumi.preferences import apply_background_default
        preferences = {'background': 'live', 'effect': 'Portal'}
        apply_background_default(preferences)
        self.assertEqual(preferences['background'], 'static')
        self.assertEqual(preferences['effect'], 'Portal')
        preferences['background'] = 'live'
        apply_background_default(preferences)
        self.assertEqual(preferences['background'], 'live')

    def test_static_background_is_default_and_meet_setup_preserves_the_choice(self):
        from sumi.controller import Controller
        from sumi.engine import Settings
        from sumi.devices import CameraDevice
        self.assertFalse(Settings().dynamic_background)
        with tempfile.TemporaryDirectory() as folder:
            controller = Controller(preferences_path=Path(folder) / 'user_settings.json', bridge_factory=None,
                                    open_url=Mock())
            controller.set_background(True)
            controller.devices = [CameraDevice(0, 'OBS Virtual Camera', '', 700)]
            controller.prepare_meet()
            self.assertTrue(controller.dynamic)
            self.assertEqual(controller.output, 'OBS Virtual Camera')
            controller.open_url.assert_not_called()

    def test_extension_survives_onefile_temporary_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'temporary-runtime'
            from shutil import copytree, rmtree
            copytree(Path(__file__).resolve().parents[1] / 'meet_extension', source / 'meet_extension')
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', str(source), create=True), \
                 patch.object(sys, 'platform', 'win32'), \
                 patch.dict('os.environ', {'LOCALAPPDATA': str(base / 'profile')}):
                destination = extension_folder()
                (destination / 'popup.js').write_text('altered')
                extension_folder()
                expected = (source / 'meet_extension' / 'popup.js').read_bytes()
                self.assertEqual((destination / 'popup.js').read_bytes(), expected)
                self.assertTrue(source.resolve().is_relative_to(base.resolve()))
                rmtree(source)
                self.assertTrue((destination / 'manifest.json').is_file())
                self.assertEqual(len(list(destination.iterdir())), 9)
                self.assertFalse(list(destination.glob('*.tmp')))

    def test_model_bytes_support_unicode_paths_and_keep_pinned_hash_validation(self):
        from sumi.vision import model_options
        with tempfile.TemporaryDirectory() as folder:
            model_folder = Path(folder) / 'Usuário João' / 'modelos'
            model_folder.mkdir(parents=True)
            model = model_folder / 'test.task'
            model.write_bytes(b'valid model')
            assets = {'test.task': ('https://storage.googleapis.com/test', hashlib.sha256(b'valid model').hexdigest())}
            with patch('sumi.vision.MODEL_ASSETS', assets):
                options = model_options(model_folder, 'test.task')
                self.assertEqual(options.model_asset_buffer, b'valid model')
                self.assertIsNone(options.model_asset_path)
                model.write_bytes(b'corrupted model')
                with self.assertRaises(ValueError):
                    model_options(model_folder, 'test.task')

    def test_frozen_state_is_outside_immutable_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', str(base / 'readonly-app'), create=True), \
                 patch.object(sys, 'platform', 'win32'), \
                 patch.dict('os.environ', {'LOCALAPPDATA': str(base / 'profile')}):
                self.assertEqual(resource_root(), base / 'readonly-app')
                self.assertEqual(data_root(), base / 'profile' / 'Sumi')
                save_preferences({'effect': 'Portal'})
                self.assertEqual(load_preferences(), {'effect': 'Portal'})
                self.assertFalse(resource_root().exists())
                self.assertFalse((base / 'profile' / 'Sumi' / 'user_settings.tmp').exists())

    def test_extension_id_matches_manifest_key(self):
        import base64, hashlib, json
        from sumi.meet import EXTENSION_ID
        manifest = json.loads((Path(__file__).resolve().parents[1] / 'meet_extension' / 'manifest.json').read_text())
        digest = hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        self.assertEqual(EXTENSION_ID, ''.join(chr(ord('a') + int(c, 16)) for c in digest))

    def test_source_keeps_existing_development_settings_location(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(data_root(), Path(__file__).resolve().parents[1])

    def test_private_files_are_rejected_at_any_depth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / '_internal'
            nested.mkdir()
            (root / 'Sumi.exe').write_bytes(b'test')
            for name in ('.meet_pairing_key', 'user_settings.json', '.env', '.env.local', 'startup-error.log'):
                with self.subTest(name=name):
                    candidate = nested / name
                    candidate.write_text('private')
                    with self.assertRaises(ValueError):
                        check_inventory(root)
                    candidate.unlink()
            self.assertEqual(len(check_inventory(root)), 1)

    def test_missing_obs_guidance_never_installs_a_driver(self):
        from sumi.controller import Controller
        with tempfile.TemporaryDirectory() as folder:
            open_site = Mock()
            controller = Controller(preferences_path=Path(folder) / 'user_settings.json', bridge_factory=None,
                                    open_url=open_site)
            controller.output = 'Só prévia'
            controller.prepare_meet()
        open_site.assert_called_once_with('https://obsproject.com/download')
        self.assertEqual(controller.output, 'Só prévia')
        self.assertIn('Não encontrei OBS Virtual Camera', controller.output_help)

    def test_diagnostic_route_does_not_start_gui(self):
        from sumi.launcher import main
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            with patch.object(sys, 'argv', ['Sumi', '--self-test', '--report', str(report)]), \
                 patch('sumi.launcher.self_test', return_value={'ok': True}), \
                 patch('sumi.app.main') as gui:
                self.assertEqual(main(), 0)
                gui.assert_not_called()
            self.assertTrue(json.loads(report.read_text())['ok'])

    def test_failed_diagnostic_returns_error_exit_status(self):
        from sumi.launcher import main
        with patch.object(sys, 'argv', ['Sumi', '--self-test']), \
             patch('sumi.launcher.self_test', side_effect=RuntimeError('synthetic failure')), \
             patch('builtins.print'):
            self.assertEqual(main(), 1)
