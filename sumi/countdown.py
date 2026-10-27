"""Background-capture countdown drawn over the camera: a big number, a progress ring and flashes.

The overlay goes on the displayed image only; the background samples come from the raw frames.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

Frame = np.ndarray
TICK_FLASH = .22      # seconds a white pulse lasts when the number changes
CAPTURE_FLASH = .45   # seconds of the "photo" flash after the capture


def _flash(frame: Frame, strength: float) -> Frame:
    if strength <= 0:
        return frame
    white = np.full_like(frame, 255)
    return cv2.addWeighted(frame, 1 - strength, white, strength, 0)


def render_countdown(frame: Frame, remaining: float, total: float) -> Frame:
    """Frame with the seconds left (rounded up) in the centre, a ring emptying over `total`,
    and a short flash at each new second."""
    output = frame.copy()
    height, width = output.shape[:2]
    shade = np.zeros_like(output)
    output = cv2.addWeighted(output, .65, shade, .35, 0)

    number = max(1, math.ceil(remaining - 1e-6))
    centre = (width // 2, height // 2)
    radius = int(min(width, height) * .32)
    thickness = max(4, radius // 14)
    cv2.circle(output, centre, radius, (255, 255, 255), max(2, thickness // 3), cv2.LINE_AA)
    fraction = max(0.0, min(1.0, remaining / total)) if total > 0 else 0.0
    if fraction > 0:
        cv2.ellipse(output, centre, (radius, radius), -90, 0, 360 * fraction, (255, 255, 255),
                    thickness, cv2.LINE_AA)

    text = str(number)
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = radius * 1.1 / cv2.getTextSize('0', font, 1, 1)[0][1]
    weight = max(3, int(scale * 2.2))
    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, weight)
    origin = (centre[0] - text_width // 2, centre[1] + text_height // 2)
    cv2.putText(output, text, origin, font, scale, (0, 0, 0), weight + max(4, weight // 2), cv2.LINE_AA)
    cv2.putText(output, text, origin, font, scale, (255, 255, 255), weight, cv2.LINE_AA)

    label = 'Saia do enquadramento'
    label_scale = max(.7, height / 620)
    label_weight = max(1, int(label_scale * 2))
    (label_width, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, label_scale, label_weight)
    label_origin = (centre[0] - label_width // 2, min(height - 20, centre[1] + radius + int(50 * label_scale)))
    cv2.putText(output, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX, label_scale, (0, 0, 0),
                label_weight + 3, cv2.LINE_AA)
    cv2.putText(output, label, label_origin, cv2.FONT_HERSHEY_SIMPLEX, label_scale, (255, 255, 255),
                label_weight, cv2.LINE_AA)

    # Time since the number last changed: pulse right after each new second.
    since_tick = (number - remaining) if remaining < total else 1.0
    return _flash(output, .55 * (1 - since_tick / TICK_FLASH) if 0 <= since_tick < TICK_FLASH else 0)


def render_capture_flash(frame: Frame, elapsed: float) -> Frame:
    """White camera flash fading out after the background is captured."""
    if elapsed < 0 or elapsed >= CAPTURE_FLASH:
        return frame
    return _flash(frame, .9 * (1 - elapsed / CAPTURE_FLASH))
