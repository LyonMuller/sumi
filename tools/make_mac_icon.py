"""Turn full-bleed square artwork into a macOS app icon PNG.

    python -m tools.make_mac_icon ARTWORK.png assets/brand/app-icon-macos.png

Follows Apple's icon grid: the shape is an 824 px continuous-corner rounded square
centered in a 1024 px canvas, with a soft drop shadow in the transparent margin.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import cv2
import numpy as np

CANVAS = 1024
SHAPE = 824
SUPERSAMPLE = 4


def squircle(size: int, exponent: float = 5.0) -> np.ndarray:
    """Superellipse mask: close to Apple's continuous corners, antialiased."""
    big = size * SUPERSAMPLE
    axis = (np.arange(big, dtype=np.float32) + 0.5) / big * 2 - 1
    x, y = np.meshgrid(axis, axis)
    inside = (np.abs(x) ** exponent + np.abs(y) ** exponent) <= 1
    return cv2.resize(inside.astype(np.float32), (size, size), interpolation=cv2.INTER_AREA)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('artwork', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    art = cv2.imread(str(args.artwork), cv2.IMREAD_COLOR)
    if art is None:
        raise SystemExit(f'Não consegui abrir {args.artwork}')
    side = min(art.shape[:2])
    top, left = (art.shape[0] - side) // 2, (art.shape[1] - side) // 2
    art = cv2.resize(art[top:top + side, left:left + side], (SHAPE, SHAPE), interpolation=cv2.INTER_AREA)
    mask = squircle(SHAPE)
    offset = (CANVAS - SHAPE) // 2
    alpha = np.zeros((CANVAS, CANVAS), np.float32)
    alpha[offset:offset + SHAPE, offset:offset + SHAPE] = mask
    # Shadow: blurred shape, nudged down, under the icon.
    shadow = cv2.GaussianBlur(np.roll(alpha, 12, axis=0), (0, 0), 14) * 0.35
    color = np.zeros((CANVAS, CANVAS, 3), np.float32)
    color[offset:offset + SHAPE, offset:offset + SHAPE] = art
    out_alpha = alpha + shadow * (1 - alpha)
    safe = np.maximum(out_alpha, 1e-6)[:, :, None]
    out_color = color * (alpha[:, :, None] / safe)  # shadow pixels are black
    image = np.dstack([np.clip(out_color, 0, 255), np.clip(out_alpha * 255, 0, 255)]).astype(np.uint8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.output), image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    print(args.output)


if __name__ == '__main__':
    main()
