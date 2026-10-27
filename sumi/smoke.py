"""Volumetric smoke puffs: layered billow noise, shaded and rendered at low resolution.

A puff grows from a source shape (disc or body silhouette). Density is a distance field
from the source, distorted by precomputed billow noise; it bursts out fast, drifts up and
erodes from the edges as a threshold rises. Fields are small float arrays inside a bounded
canvas and are upscaled once, so several puffs per frame stay cheap.
"""
from __future__ import annotations
import math

import cv2
import numpy as np

TILE = 256
_TILES: tuple[np.ndarray, np.ndarray] | None = None
LIGHT = np.array((252, 250, 248), np.float32)   # BGR, sunlit tops
SHADE = np.array((140, 136, 136), np.float32)   # BGR, cooler undersides


def _spectral_noise(seed: int, beta: float) -> np.ndarray:
    """Tileable 1/f^beta noise with unit deviation (FFT filtering wraps by design)."""
    spectrum = np.fft.rfft2(np.random.default_rng(seed).standard_normal((TILE, TILE)))
    fy = np.fft.fftfreq(TILE)[:, None]
    fx = np.fft.rfftfreq(TILE)[None, :]
    freq = np.hypot(fx, fy)
    freq[0, 0] = 1
    spectrum *= freq ** -beta
    spectrum[0, 0] = 0
    noise = np.fft.irfft2(spectrum, s=(TILE, TILE))
    return (noise / noise.std()).astype(np.float32)


def _domes(seed: int, count: int) -> np.ndarray:
    """Tileable Worley domes: round billows separated by sharp creases (0 at creases)."""
    points = np.random.default_rng(seed).integers(0, TILE, (count, 2))
    canvas = np.full((TILE * 3, TILE * 3), 255, np.uint8)
    for ox in range(3):
        for oy in range(3):
            canvas[points[:, 1] + oy * TILE, points[:, 0] + ox * TILE] = 0
    nearest = cv2.distanceTransform(canvas, cv2.DIST_L2, 5)[TILE:2 * TILE, TILE:2 * TILE]
    radius = 0.9 * TILE / math.sqrt(count)
    return np.sqrt(np.clip(1 - nearest / radius, 0, 1)).astype(np.float32)


def tiles() -> tuple[np.ndarray, np.ndarray]:
    """(warp, billow): warp has 2 signed channels, billow 2 dome channels (coarse, fine)."""
    global _TILES
    if _TILES is None:
        warp = np.dstack([_spectral_noise(11, 2.0), _spectral_noise(12, 2.0)]) * 0.5
        billow = np.dstack([_domes(21, 18), _domes(22, 52)])
        _TILES = (warp.astype(np.float32), billow)
    return _TILES


def smooth01(x: np.ndarray | float):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


class SmokePuff:
    """One billowing cloud. `render_at` returns the covered rect so callers can track ROIs."""

    def __init__(self, frame_shape: tuple[int, int], source: np.ndarray, origin: tuple[int, int],
                 reach: float, seed: int = 0, delay: float = 0.0, life: float = 1.0,
                 rise: float = 0.3, opacity: float = 0.94, size: tuple[int, int] | None = None) -> None:
        """`source` is a float mask (0..1) covering `size` (w, h) frame pixels at `origin` (x, y)."""
        fh, fw = frame_shape
        self.reach, self.delay, self.life, self.opacity = float(reach), delay, life, opacity
        self.rise = rise * reach
        sh, sw = (size[1], size[0]) if size else source.shape
        ox, oy = origin
        margin = int(reach * 1.5) + 4
        x0, y0 = max(0, ox - margin), max(0, oy - margin - int(self.rise))
        x1, y1 = min(fw, ox + sw + margin), min(fh, oy + sh + margin)
        self.rect = (x0, y0, x1, y1)
        w, h = x1 - x0, y1 - y0
        self.k = int(np.clip(round(max(w, h) / 190), 2, 7))
        k = self.k
        self.size = (w, h)
        self.low = (max(2, math.ceil(w / k)), max(2, math.ceil(h / k)))
        lw, lh = self.low
        cx, cy = ox - x0, oy - y0
        part = cv2.resize(source, (max(1, round(sw / k)), max(1, round(sh / k))), interpolation=cv2.INTER_AREA)
        low_source = np.zeros((lh, lw), np.float32)
        px, py = cx // k, cy // k
        ph, pw = min(part.shape[0], lh - py), min(part.shape[1], lw - px)
        low_source[py:py + ph, px:px + pw] = part[:ph, :pw]
        # Distance (in full-res pixels) from the source; zero inside it.
        self.dist0 = cv2.distanceTransform((low_source < 0.35).astype(np.uint8), cv2.DIST_L2, 3) * k
        rng = np.random.default_rng(seed)
        self.offset = rng.uniform(0, TILE, 4).astype(np.float32)
        ys, xs = np.mgrid[:lh, :lw].astype(np.float32)
        self.xs, self.ys = (xs + .5) * k, (ys + .5) * k
        self.period = max(60.0, reach * 2.4)
        self.src_box = (cx, cy, cx + sw, cy + sh)

    @classmethod
    def disc(cls, frame_shape: tuple[int, int], center: tuple[float, float], radius: float,
             reach: float, **kwargs) -> 'SmokePuff':
        r = max(2, int(radius))
        source = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
        cv2.circle(source, (r, r), r, 1.0, -1)
        return cls(frame_shape, source, (int(center[0]) - r, int(center[1]) - r), reach, **kwargs)

    def active(self, now: float) -> bool:
        return 0 < now - self.delay < self.life

    def _timeline(self, t: float) -> tuple[float, float, float, float, float]:
        burst = 1 - (1 - min(t / 0.12, 1.0)) ** 3
        reach = self.reach * (0.14 + 0.86 * burst) * (1 + 0.14 * max(0.0, t - 0.12))
        gone = float(np.clip((t - 0.08) / (self.life - 0.08), 0, 1))
        threshold = 0.02 + 1.35 * gone ** 1.15
        rise = self.rise * (1 - math.exp(-2.4 * t))
        ramp = float(smooth01(t / 0.035))
        return reach, threshold, rise, ramp, gone

    def render_at(self, frame: np.ndarray, now: float) -> tuple[int, int, int, int] | None:
        """Paint this puff over `frame` in place; returns the touched rect or None."""
        t = float(now - self.delay)
        if not 0 < t < self.life:
            return None
        reach, threshold, rise, ramp, gone = self._timeline(t)
        k = self.k
        lw, lh = self.low
        # Only the part of the canvas the cloud can reach right now.
        sx0, sy0, sx1, sy1 = self.src_box
        grow = reach * 1.35 + 6
        a0, a1 = max(0, int((sx0 - grow) // k)), min(lw, int((sx1 + grow) // k) + 2)
        b0, b1 = max(0, int((sy0 - grow - rise) // k)), min(lh, int((sy1 + grow) // k) + 2)
        if a1 - a0 < 2 or b1 - b0 < 2:
            return None
        dist = cv2.warpAffine(self.dist0, np.float32([[1, 0, 0], [0, 1, rise / k]]), (lw, lh),
                              flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)[b0:b1, a0:a1]
        xs, ys = self.xs[b0:b1, a0:a1], self.ys[b0:b1, a0:a1]
        warp_tile, billow_tile = tiles()
        scale = TILE / self.period
        ox, oy, wx, wy = self.offset
        roll = t * self.period * 0.35
        w2 = cv2.remap(warp_tile, (xs + wx) * scale * 0.5, (ys + wy + roll * 0.3) * scale * 0.5,
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        bend = reach * 0.45
        b = cv2.remap(billow_tile, (xs + w2[:, :, 0] * bend + ox + t * self.period * 0.06) * scale,
                      (ys + w2[:, :, 1] * bend + oy + roll) * scale, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        n = b[:, :, 0] * 0.68 + b[:, :, 1] * 0.32
        edge = 1.0 - dist / max(reach, 1.0)
        field = edge * 0.95 + (n - 0.5) * 0.85
        density = smooth01((field - threshold) / 0.42)
        # Billow height: lumps inside the cloud, rounded off toward the rim.
        height = cv2.GaussianBlur(density ** 0.8 * (0.2 + n), (0, 0), 1.0)
        gx = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3) / 8
        gy = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3) / 8
        soft = density
        # Thick-core darkening: a cheap wide blur through a 4x smaller copy.
        tiny = cv2.resize(density, (max(2, density.shape[1] // 4), max(2, density.shape[0] // 4)), interpolation=cv2.INTER_AREA)
        tiny = cv2.GaussianBlur(tiny, (0, 0), max(1.0, reach * 0.2 / k / 4))
        core = cv2.resize(tiny, (density.shape[1], density.shape[0]), interpolation=cv2.INTER_LINEAR)
        lit = 0.78 + 4.0 * (gy * 0.85 + gx * 0.35) - 0.38 * core * (0.6 + 0.4 * gone)
        lit += max(0.0, 1 - t / 0.10) * soft * 0.3
        lum = np.clip(lit, 0, 1)[:, :, None]
        color = SHADE + (LIGHT - SHADE) * lum
        alpha = soft * (0.55 + 0.45 * core) * smooth01(soft * 1.6) * (self.opacity * ramp * (1 - 0.35 * gone))
        hh, ww = alpha.shape
        w, h = (a1 - a0) * k, (b1 - b0) * k
        x0, y0 = self.rect[0] + a0 * k, self.rect[1] + b0 * k
        x1, y1 = min(self.rect[2], x0 + w), min(self.rect[3], y0 + h)
        pm = np.empty((alpha.shape[0], alpha.shape[1], 4), np.float32)
        np.multiply(color, alpha[:, :, None], out=pm[:, :, :3])
        pm[:, :, 3] = alpha * 255
        size = (x1 - x0, y1 - y0)
        up = cv2.resize(pm.astype(np.uint8), size, interpolation=cv2.INTER_LINEAR)
        color = cv2.cvtColor(up, cv2.COLOR_BGRA2BGR)
        inv = 255 - cv2.extractChannel(up, 3)
        roi = frame[y0:y1, x0:x1]
        frame[y0:y1, x0:x1] = cv2.add(cv2.multiply(roi, cv2.merge((inv, inv, inv)), scale=1 / 255), color)
        return x0, y0, x1, y1
