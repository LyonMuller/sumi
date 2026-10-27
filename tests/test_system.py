from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2

from sumi import system
from sumi.paths import data_root
from sumi.preferences import load_preferences, save_preferences
from sumi.virtual_output import output_command


class SystemTests(unittest.TestCase):
    def test_macos_keeps_user_data_in_application_support(self):
        with patch.object(sys, 'platform', 'darwin'), \
             patch('pathlib.Path.home', return_value=Path('/Users/teste')), \
             patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(data_root(), Path('/Users/teste/Library/Application Support/Sumi'))
            self.assertEqual(system.user_data_label('startup-error.log'),
                             '~/Library/Application Support/Sumi/startup-error.log')

    def test_windows_label_uses_local_app_data(self):
        with patch.object(sys, 'platform', 'win32'):
            self.assertEqual(system.user_data_label('startup-error.log'),
                             '%LOCALAPPDATA%\\Sumi\\startup-error.log')

    def test_camera_api_follows_the_system(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(system.camera_backends(), (cv2.CAP_AVFOUNDATION,))
            self.assertEqual(system.enumeration_backend(), cv2.CAP_AVFOUNDATION)
        with patch.object(sys, 'platform', 'win32'):
            self.assertEqual(system.camera_backends(), (cv2.CAP_DSHOW, cv2.CAP_MSMF))

    def test_unity_capture_is_offered_only_on_windows(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(system.output_choices(), {'Só prévia': 'off', 'OBS Virtual Camera': 'obs'})
        with patch.object(sys, 'platform', 'win32'):
            self.assertEqual(system.output_choices()['Unity Capture'], 'unitycapture')

    def test_frozen_output_program_has_no_exe_suffix_on_macos(self):
        with patch.object(sys, 'platform', 'darwin'), \
             patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, '_MEIPASS', '/Applications/Sumi.app/Contents/Frameworks', create=True):
            self.assertEqual(Path(output_command()[0]),
                             Path('/Applications/Sumi.app/Contents/Frameworks/video_output/SumiVideoOutput'))

    def test_open_path_uses_the_macos_open_command(self):
        with patch.object(sys, 'platform', 'darwin'), patch('sumi.system.subprocess.run') as run:
            system.open_path(Path('/tmp/guia.html'))
        self.assertEqual(run.call_args.args[0], ['open', '/tmp/guia.html'])

    def test_open_path_failure_is_an_os_error(self):
        with patch.object(sys, 'platform', 'darwin'), \
             patch('sumi.system.subprocess.run', side_effect=FileNotFoundError('open')):
            with self.assertRaises(OSError):
                system.open_path(Path('/tmp/x'))

    def test_child_processes_hide_console_only_on_windows(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(system.hidden_process_flags(), 0)


if __name__ == '__main__':
    unittest.main()
