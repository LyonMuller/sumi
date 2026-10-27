import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import setup_models


class ModelInstallationTests(unittest.TestCase):
    def test_existing_corrupt_model_is_rejected_without_rewriting_manifest(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'model.task').write_bytes(b'altered')
            manifest=path/'checksums.json'; manifest.write_text('original')
            with patch.object(setup_models,'MODEL_ASSETS',{'model.task':('https://storage.googleapis.com/test',hashlib.sha256(b'valid').hexdigest())}):
                with self.assertRaises(ValueError): setup_models.prepare(path)
            self.assertEqual(manifest.read_text(),'original')

    def test_existing_valid_model_is_verified_without_network(self):
        with TemporaryDirectory() as folder:
            path=Path(folder); (path/'model.task').write_bytes(b'valid')
            assets={'model.task':('https://storage.googleapis.com/test',hashlib.sha256(b'valid').hexdigest())}
            with patch.object(setup_models,'MODEL_ASSETS',assets), patch('urllib.request.urlopen') as download:
                setup_models.prepare(path)
                download.assert_not_called()
            self.assertTrue((path/'checksums.json').exists())
