from pathlib import Path
from time import perf_counter
from unittest.mock import patch
import numpy as np
from sumi.vision import Detector,Segmenter
from sumi.app import App
from sumi.devices import list_cameras
from sumi.effect_catalog import LABELS
import tkinter as tk

root=Path(__file__).resolve().parent
blank=np.zeros((720,1280,3),np.uint8)
detector=Detector(root/'models')
try:
    assert detector.detect(blank,1.0)==(False,0)
finally:
    detector.close()
segmenter=Segmenter(root/'models')
try:
    result=segmenter.capture(blank,1.0)
    assert result.mask.shape==(720,1280)
    assert np.isfinite(result.mask).all()
    print('SEGMENTER_OK: mask shape/range',result.mask.shape,float(result.mask.min()),float(result.mask.max()))
finally:
    segmenter.close()
print('MODELS_OK: hand, face and silhouette initialized and executed')
print('CAMERAS:',[(c.index,c.name) for c in list_cameras()])
window=tk.Tk()
window.withdraw()
app=App(window)
window.update_idletasks()
assert app.controller.engine is None
assert not app.leave_enabled.get()
assert app.controller.countdown.deadline is None
assert len(app.inputs)==4
assert app.effect.get() in LABELS
app.toggle_settings()
assert app.settings_visible
app.hide_settings()
assert not app.settings_visible
app.hotkey.ready.wait(1)
print('HOTKEY_OK: global F8 registered =',app.hotkey.registered)
app.close()
while not app.controller.stopped(): window.update()
print('GUI_OK: controls initialize without opening webcam')
