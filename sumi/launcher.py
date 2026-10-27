"""Desktop entry point; diagnostics never open a webcam, window or Meet bridge."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import traceback

from . import __version__
from .paths import data_file, resource_root


def self_test() -> dict[str, object]:
    import cv2
    import numpy as np
    import customtkinter
    from PIL import Image
    from .app import App
    from .vision import Detector, Segmenter
    from .gesture_guides import GUIDES
    from .model_assets import MODEL_ASSETS
    from setup_models import verify_model
    from .virtual_output import VirtualOutput, output_command, output_environment
    from .system import hidden_process_flags
    import subprocess
    import zlib

    root = resource_root()
    for name, (_, digest) in MODEL_ASSETS.items():
        verify_model(root / 'models' / name, digest)
    for name in {guide.image for guide in GUIDES.values()}:
        with Image.open(root / 'assets' / 'gestures' / name) as image:
            image.verify()
    with Image.open(root / 'assets' / 'effects' / 'tronco.png') as image:
        image.verify()
    with Image.open(root / 'assets' / 'brand' / 'app-icon.ico') as icon:
        icon.verify()
    for name in ('GUIA_RAPIDO.html', 'meet_extension/manifest.json', 'LICENSE'):
        if not (root / name).is_file():
            raise FileNotFoundError(name)
    if getattr(sys, 'frozen', False):
        if not (root / 'customtkinter' / 'assets' / 'themes' / 'blue.json').is_file():
            raise FileNotFoundError('Tema da interface')
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    detector = Detector(root / 'models')
    try:
        detector.detect(frame, 1.0, 'anime')
    finally:
        detector.close()
    segmenter = Segmenter(root / 'models')
    try:
        result = segmenter.capture(frame, 1.0)
        if result.mask.shape != frame.shape[:2]:
            raise ValueError('Dimensões do recorte inválidas')
    finally:
        segmenter.close()
    worker = subprocess.run(output_command() + ['--self-test'], capture_output=True, timeout=30, check=True,
                            env=output_environment(), creationflags=hidden_process_flags())
    worker_report = json.loads(worker.stdout)
    if not worker_report.get('ok') or worker_report.get('forbidden_imports'):
        raise RuntimeError('O diagnóstico do processo de saída não passou.')
    output = VirtualOutput(320, 240, 30, 'obs', dry_run=True)
    try:
        output.send(frame)
        if output.last_crc32 != zlib.crc32(frame):
            raise RuntimeError('O quadro mudou no canal de saída.')
    finally:
        output.close()
    if 'pyvirtualcam' in sys.modules:
        raise RuntimeError('PyVirtualCam carregado indevidamente no processo principal.')
    manifest_path = root / 'bundle-build.json'
    signature = json.loads(manifest_path.read_text(encoding='utf-8')).get('runtime_signature') if manifest_path.is_file() else None
    return {'ok': True, 'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False)),
            'runtime_signature': signature,
            'checks': ['imports', 'assets', 'model_hashes', 'hand_face_inference', 'segmentation', 'independent_output_process', 'rawvideo_fidelity'],
            'camera_opened': False, 'network_used': False, 'virtual_output_tested': False}


def main() -> int:
    parser = argparse.ArgumentParser(description='Sumi')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--service', action='store_true', help='Run without a window, driven by a native shell')
    parser.add_argument('--preview', type=Path, help='Shared preview file for --service')
    parser.add_argument('--no-meet', action='store_true', help='Do not open the local Meet bridge')
    args = parser.parse_args()
    if args.service:
        from .service import main as run_service
        return run_service(args.preview, meet=not args.no_meet)
    if args.self_test:
        try:
            report = self_test()
        except Exception as error:
            report = {'ok': False, 'error': type(error).__name__, 'detail': str(error)}
        if args.report:
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        elif sys.stdout is not None:
            print(json.dumps(report, ensure_ascii=False))
        return 0 if report['ok'] else 1
    try:
        from .app import main as run_app
        run_app()
        return 0
    except Exception:
        # No video, preferences or pairing key is written to this startup log.
        try:
            data_file('startup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError:
            pass
        from .system import show_fatal_error, user_data_label
        show_fatal_error('Não foi possível abrir o Sumi. Reinstale o aplicativo. '
                         f'Detalhes técnicos ficam em {user_data_label("startup-error.log")}.')
        return 1
