"""Checks run INSIDE the frozen bundle, without a camera: resources, models, inference, effects.

Built by verify-engine.sh with the same recipe as the engine (entry point swapped), never shipped.
Prints one JSON line; exit code 0 only when every check passed.
"""
import hashlib
import json
import re
import subprocess
import sys
import traceback
from time import perf_counter

report = {'frozen': bool(getattr(sys, 'frozen', False)), 'checks': {}}


def check(name):
    def wrap(function):
        try:
            report['checks'][name] = function() or 'ok'
        except Exception:
            report['checks'][name] = 'FAILED: ' + traceback.format_exc(limit=4)
        return function
    return wrap


import cv2
import numpy as np
from sumi.paths import extension_folder, resource_root

root = resource_root()
report['resource_root'] = str(root)


@check('opencv_without_ffmpeg')
def _():
    info = cv2.getBuildInformation()
    ffmpeg = re.search(r'^\s*FFMPEG:\s+(\S+)', info, re.MULTILINE)
    avfoundation = re.search(r'^\s*AVFoundation:\s+(\S+)', info, re.MULTILINE)
    assert (ffmpeg is None or ffmpeg.group(1) == 'NO') and avfoundation and avfoundation.group(1) == 'YES'
    return f'{cv2.__version__} FFMPEG={ffmpeg.group(1) if ffmpeg else "absent"} AVFoundation=YES'


@check('model_hashes')
def _():
    from sumi.model_assets import MODEL_ASSETS
    for name, (_, digest) in MODEL_ASSETS.items():
        assert hashlib.sha256((root / 'models' / name).read_bytes()).hexdigest() == digest, name
    return f'{len(MODEL_ASSETS)} models'


@check('assets')
def _():
    from sumi.gesture_guides import GUIDES
    names = {guide.image for guide in GUIDES.values()}
    for name in names:
        image = cv2.imread(str(root / 'assets' / 'gestures' / name), cv2.IMREAD_UNCHANGED)
        assert image is not None and image.shape[0] > 10, name
    tronco = cv2.imread(str(root / 'assets' / 'effects' / 'tronco.png'), cv2.IMREAD_UNCHANGED)
    assert tronco is not None and tronco.shape[2] == 4
    assert (root / 'assets' / 'brand' / 'app-icon-macos.png').is_file()
    return f'{len(names)} gesture images, effect and brand art'


@check('hand_face_inference')
def _():
    from sumi.vision import Detector
    detector = Detector(root / 'models')
    try:
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        detector.detect(frame, 1.0, 'anime')
        detector.detect(frame, 1.1, 'portal')
    finally:
        detector.close()


@check('segmentation')
def _():
    from sumi.vision import Segmenter
    segmenter = Segmenter(root / 'models')
    try:
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        result = segmenter.capture(frame, 1.0)
        assert result.mask.shape == frame.shape[:2]
    finally:
        segmenter.close()


@check('every_effect_renders')
def _():
    from sumi.effect_catalog import EFFECTS
    from sumi.effects import Silhouette
    background = np.full((360, 640, 3), 40, np.uint8)
    mask = np.zeros((360, 640), np.float32)
    cv2.circle(mask, (320, 90), 44, 1, -1)
    cv2.ellipse(mask, (320, 250), (80, 130), 0, 0, 360, 1, -1)
    live = background.copy()
    live[mask > 0] = (80, 140, 210)
    subject = Silhouette(10, live, mask)
    began = perf_counter()
    for name, kind in EFFECTS.items():
        effect = kind(subject, True, 10)
        for p in (0.1, 0.5, 0.9):
            out = effect.render(live, background, 10 + p * effect.duration)
            assert out.shape == live.shape, name
    return f'{len(EFFECTS)} effects in {perf_counter() - began:.1f}s'


@check('meet_extension_export')
def _():
    folder = extension_folder()
    assert (folder / 'manifest.json').is_file() and (folder / 'background.js').is_file()
    return str(folder)


@check('video_output_program')
def _():
    from sumi.virtual_output import output_command, output_environment
    command = output_command()
    result = subprocess.run(command + ['--self-test'], capture_output=True, timeout=60,
                            env=output_environment())
    answer = json.loads(result.stdout)
    assert answer.get('ok') and not answer.get('forbidden_imports'), answer
    return command[0]


@check('no_unwanted_modules')
def _():
    for name in ('tkinter', 'customtkinter', 'PIL', 'pyvirtualcam', 'sounddevice'):
        assert name not in sys.modules, name
    assert 'matplotlib.pyplot' in sys.modules  # the stub that satisfies mediapipe's import


report['ok'] = all(value != '' and not str(value).startswith('FAILED') for value in report['checks'].values())
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(0 if report['ok'] else 1)
