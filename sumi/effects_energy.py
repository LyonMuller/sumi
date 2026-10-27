"""Energy wave: a ball of light grows between the hands, then fires a beam at the camera.

Nothing here hides the person. `EnergyCharge` is a live overlay that follows the hands while
the charge pose is held and fizzles out if it is dropped; `EnergyWaveEffect` is the one-shot
shot (flash, shake, beam, particles) after which the very same live frame comes back. Soft
fields are computed at reduced resolution inside bounded rectangles, as the portal does, and
every animation is a function of elapsed time only.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .effects import Silhouette, TeleportEffect, smooth
from .effects_portal import _tile_noise
from .scene import Frame

S = 4                      # downscale of the soft fields (halo, beam); the ball core uses BODY
BODY = 3
TAU = 2 * math.pi
Rect = tuple[int, int, int, int]

# BGR gradient of the energy, from the cold edge to the white-hot core.
_STOPS = ((0.0, (0, 0, 0)), (0.10, (120, 30, 4)), (0.28, (255, 105, 12)), (0.50, (255, 188, 52)),
          (0.70, (255, 232, 150)), (0.86, (255, 250, 226)), (1.0, (255, 255, 255)))
GLOW = np.array((255, 176, 70), np.float32)      # additive blue-cyan light
ICE = np.array((255, 244, 205), np.float32)      # pale light
SKY = np.array((255, 150, 40), np.float32)       # tint on skin and clothes
AURA = np.array((255, 185, 80), np.float32)     # faint halo around the silhouette
_STEPS = np.linspace(0, 1, 256)
LUT = np.stack([np.interp(_STEPS, [s[0] for s in _STOPS], [s[1][c] for s in _STOPS]) for c in range(3)],
               axis=-1).astype(np.float32)               # (256, 3) BGR
NOISE = _tile_noise(64, 128, np.random.default_rng(2112))
NOISE_BIG = np.ascontiguousarray(np.tile(NOISE, (8, 8)))      # repeated so affine lookups never need wrapping


def c01(x):
    return np.clip(x, 0.0, 1.0)


def align(rect: tuple[float, float, float, float], size: tuple[int, int], step: int = S) -> Rect:
    """Grow a rectangle to whole cells of `step` pixels and clip it to the frame (width, height)."""
    w, h = size
    x0 = max(0, int(math.floor(rect[0])) // step * step)
    y0 = max(0, int(math.floor(rect[1])) // step * step)
    x1 = min(w, -(-int(math.ceil(rect[2])) // step) * step)
    y1 = min(h, -(-int(math.ceil(rect[3])) // step) * step)
    return x0, y0, max(x0, x1), max(y0, y1)


def cells(rect: Rect, step: int = S) -> tuple[slice, slice]:
    x0, y0, x1, y1 = rect
    return slice(y0 // step, -(-y1 // step)), slice(x0 // step, -(-x1 // step))


def upscale(img: np.ndarray, rect: Rect, step: int = S) -> np.ndarray:
    x0, y0, x1, y1 = rect
    big = cv2.resize(img, (img.shape[1] * step, img.shape[0] * step), interpolation=cv2.INTER_LINEAR)
    return big[:y1 - y0, :x1 - x0]


def grids(rect: Rect, step: int = S) -> tuple[np.ndarray, np.ndarray]:
    """Cell-centre coordinates, in frame pixels, of every cell of the rectangle."""
    x0, y0, x1, y1 = rect
    xs = (np.arange(x0 // step, -(-x1 // step), dtype=np.float32) * step + (step - 1) / 2)
    ys = (np.arange(y0 // step, -(-y1 // step), dtype=np.float32) * step + (step - 1) / 2)
    return np.broadcast_to(xs[None, :], (len(ys), len(xs))), np.broadcast_to(ys[:, None], (len(ys), len(xs)))


def noise_field(shape: tuple[int, int], matrix: list[list[float]]) -> np.ndarray:
    """Noise tile looked up at an affine map of the cell grid (cells -> tile columns and rows), via one warp.

    The map is shifted by whole tiles so that it stays inside the repeated texture; the tile is seamless,
    so the shift changes nothing visible.
    """
    h, w = shape
    m = np.array(matrix, np.float64)
    for row, period in ((0, NOISE.shape[1]), (1, NOISE.shape[0])):
        corners = [m[row, 2] + m[row, 0] * i + m[row, 1] * j for i in (0, w - 1) for j in (0, h - 1)]
        m[row, 2] -= math.floor(min(corners) / period) * period
    return cv2.warpAffine(NOISE_BIG, m.astype(np.float32), (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def axis_noise(rect: Rect, step: int, origin: tuple[float, float], axis: tuple[float, float],
               period: tuple[float, float], offset: tuple[float, float]) -> np.ndarray:
    """Noise in the frame of a beam: along `axis` (period[0] px per tile) and across it (period[1] px)."""
    x0, y0, x1, y1 = rect
    w, h = -(-x1 // step) - x0 // step, -(-y1 // step) - y0 // step
    cx, cy = x0 + (step - 1) / 2 - origin[0], y0 + (step - 1) / 2 - origin[1]
    ux, uy = axis
    ka, kb = NOISE.shape[1] / period[0], NOISE.shape[0] / period[1]
    return noise_field((h, w), [[ka * step * ux, ka * step * uy, ka * (cx * ux + cy * uy) + offset[0]],
                                [-kb * step * uy, kb * step * ux, kb * (cy * ux - cx * uy) + offset[1]]])


def tone(live: Frame, rect: Rect, shape: tuple[int, int]) -> np.ndarray:
    """Light 1 on dark rooms, down to .5 over white walls, per cell: additive light must not blow out a bright scene."""
    x0, y0, x1, y1 = rect
    small = cv2.resize(live[y0:y1, x0:x1], (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return 1.0 - cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) * (0.5 / 255)


def composite(frame: Frame, rect: Rect, layer: np.ndarray, alpha: np.ndarray | None, step: int = S) -> None:
    """frame = frame * (1 - alpha) + layer (premultiplied), both given at reduced resolution."""
    x0, y0, x1, y1 = rect
    q = upscale(np.clip(layer, 0, 255).astype(np.uint8), rect, step)
    roi = frame[y0:y1, x0:x1]
    if alpha is None:
        frame[y0:y1, x0:x1] = cv2.add(roi, q)
        return
    inv = cv2.cvtColor(255 - upscale(np.clip(alpha * 255 + .5, 0, 255).astype(np.uint8), rect, step), cv2.COLOR_GRAY2BGR)
    frame[y0:y1, x0:x1] = cv2.add(cv2.multiply(roi, inv, scale=1 / 255.0), q)


def paint(canvas: np.ndarray, frame: Frame, origin: tuple[int, int]) -> None:
    """Add a small uint8 canvas of lines and sparks onto the frame at `origin`, clipped."""
    x, y = origin
    h, w = canvas.shape[:2]
    fh, fw = frame.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(fw, x + w), min(fh, y + h)
    if x1 > x0 and y1 > y0:
        frame[y0:y1, x0:x1] = cv2.add(frame[y0:y1, x0:x1], canvas[y0 - y:y1 - y, x0 - x:x1 - x])


def shifted(live: Frame, dx: int, dy: int) -> Frame:
    """The frame moved by (dx, dy), the uncovered border repeating the edge: a small camera shake."""
    if not dx and not dy:
        return live.copy()
    h, w = live.shape[:2]
    out = np.empty_like(live)
    sx0, sx1, dx0, dx1 = (0, w - dx, dx, w) if dx >= 0 else (-dx, w, 0, w + dx)
    sy0, sy1, dy0, dy1 = (0, h - dy, dy, h) if dy >= 0 else (-dy, h, 0, h + dy)
    out[dy0:dy1, dx0:dx1] = live[sy0:sy1, sx0:sx1]
    if dx > 0:
        out[dy0:dy1, :dx] = out[dy0:dy1, dx:dx + 1]
    elif dx < 0:
        out[dy0:dy1, dx:] = out[dy0:dy1, dx - 1:dx]
    if dy > 0:
        out[:dy] = out[dy:dy + 1]
    elif dy < 0:
        out[dy:] = out[dy - 1:dy]
    return out


def line(canvas: np.ndarray, a: tuple[float, float], b: tuple[float, float], color, width: int = 1) -> None:
    cv2.line(canvas, (round(a[0] * 16), round(a[1] * 16)), (round(b[0] * 16), round(b[1] * 16)), color, width,
             cv2.LINE_AA, 4)


def dot(canvas: np.ndarray, p: tuple[float, float], radius: float, color) -> None:
    cv2.circle(canvas, (round(p[0] * 16), round(p[1] * 16)), max(1, round(radius * 16)), color, -1, cv2.LINE_AA, 4)


def scaled(color, k: float) -> tuple[int, int, int]:
    k = max(0.0, min(1.0, k))
    return int(color[0] * k), int(color[1] * k), int(color[2] * k)


def flicker(t: float) -> float:
    return 1.0 + 0.09 * math.sin(TAU * 13.0 * t) + 0.06 * math.sin(TAU * 7.3 * t + 1.1) + 0.04 * math.sin(TAU * 23.0 * t + 2.3)


def person_cells(subject: Silhouette | None, size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, Rect] | None:
    """Silhouette at reduced resolution, its faint outer rim, and the pixels it covers (with margin)."""
    if subject is None or subject.mask.shape != (size[1], size[0]) or not np.isfinite(subject.mask).all():
        return None
    w, h = size
    low = cv2.resize(np.clip(subject.mask, 0, 1), (-(-w // S), -(-h // S)), interpolation=cv2.INTER_AREA)
    x, y, bw, bh = cv2.boundingRect((low > .3).astype(np.uint8))
    if bw * bh < 4:
        return None
    rim = c01(cv2.GaussianBlur(cv2.dilate(low, np.ones((3, 3), np.uint8)), (0, 0), 2.2) - low * .8) * 1.5
    return low, rim.astype(np.float32), align(((x - 3) * S, (y - 3) * S, (x + bw + 3) * S, (y + bh + 3) * S), size)


class EnergyCharge:
    """The ball between the hands while the charge pose is held: a live overlay, never part of the person."""
    FIZZLE = .42

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = 'idle'            # idle | charging | fizzle
        self.target: tuple[float, float, float] | None = None
        self.pos: tuple[float, float, float] | None = None    # smoothed (x, y, size)
        self.level = 0.0
        self.goal = 0.0
        self.since = self.lost = 0.0
        self.last: float | None = None
        self.cut: tuple[Silhouette, tuple | None] | None = None

    @property
    def charging(self) -> bool:
        return self.state == 'charging'

    @property
    def ball(self) -> tuple[float, float, float] | None:
        """Where the ball is now (x, y, hand size), also while it fizzles."""
        return self.pos

    def active(self, now: float) -> bool:
        return self.state == 'charging' or (self.state == 'fizzle' and now - self.lost < self.FIZZLE)

    def update(self, now: float, ball: tuple[float, float, float] | None, charge: float, charging: bool,
               subject: Silhouette | None = None) -> None:
        """Feed the newest recognition (hands in frame pixels); call every frame, with charging False when none."""
        if self.state == 'fizzle' and now - self.lost >= self.FIZZLE:
            self.reset()
        if charging and ball is not None and all(math.isfinite(v) for v in ball):
            if self.state != 'charging':
                if self.state == 'idle' or self.pos is None:
                    self.pos, self.level, self.since = ball, 0.0, now
                    self.last = None
                self.state = 'charging'
            self.target, self.goal = ball, min(1.0, max(0.0, charge))
        elif self.state == 'charging':
            self.state, self.lost = 'fizzle', now
        if subject is None:
            self.cut = None
        elif self.cut is None or self.cut[0] is not subject:
            self.cut = (subject, person_cells(subject, (subject.mask.shape[1], subject.mask.shape[0])))

    def render(self, live: Frame, now: float) -> Frame:
        """The live frame with the ball over it (a copy; the input is never touched)."""
        out = live.copy()
        if self.pos is None or not self.active(now):
            return out
        fh, fw = live.shape[:2]
        dt = 0.0 if self.last is None else min(.1, max(0.0, now - self.last))
        self.last = now
        if self.target is not None and self.state == 'charging':
            k = 1 - math.exp(-dt * 18)
            self.pos = tuple(p + (q - p) * k for p, q in zip(self.pos, self.target))
        self.level += (self.goal - self.level) * (1 - math.exp(-dt * 10))
        x, y, size = self.pos
        p = 0.0 if self.state == 'charging' else min(1.0, (now - self.lost) / self.FIZZLE)
        level = self.level
        radius = min(.3 * min(fh, fw), max(10.0, size * .95 * (.3 + .7 * level ** .75) * float(smooth((now - self.since) / .22)) * (1 - p) ** 2))
        gain = (1.0 - p) * (1.0 + .22 * float(smooth((level - .8) / .2)))
        f = flicker(now)
        person = self.cut[1] if self.cut is not None and self.cut[0].frame.shape == live.shape else None
        # Light spilling around the ball, onto the room and onto the person nearby.
        reach = 4.6 * radius
        rect = align((x - reach, y - reach, x + reach, y + reach), (fw, fh))
        if rect[2] > rect[0] and rect[3] > rect[1]:
            gx, gy = grids(rect)
            r2 = (np.square(gx - x) + np.square(gy - y)) * (1 / (radius * radius))
            light = (np.exp(-r2 * (1 / 4.41)) * (.55 * gain * f))[:, :, None] * GLOW
            light += (np.exp(-r2 * (1 / 1.21)) * (.62 * gain * f))[:, :, None] * ICE
            if person is not None:
                near = np.exp(-r2 * (1 / 5.76)) * (.22 * gain * level * f) * person[0][cells(rect)]
                light += near[:, :, None] * SKY * .55
            light *= tone(live, rect, r2.shape)[:, :, None]
            composite(out, rect, light, None)
        if person is not None and level > .08:
            # The whole person takes a faint blue cast, and at full charge an aura clings to the silhouette.
            where = cells(person[2])
            full = float(smooth((level - .55) / .45)) * gain
            cast = (person[0][where] * (.06 * level * gain * f))[:, :, None] * SKY
            composite(out, person[2], cast + person[1][where][:, :, None] * (AURA * (.2 * full * f)), None)
        self._body(out, x, y, radius, now, gain, f, p, level)
        self._sparks(out, x, y, radius, now, gain, p, level)
        return out

    def _body(self, out: Frame, x: float, y: float, radius: float, now: float, gain: float, f: float,
              p: float, level: float) -> None:
        fh, fw = out.shape[:2]
        extent = 1.6 * radius
        rect = align((x - extent, y - extent, x + extent, y + extent), (fw, fh), BODY)
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return
        gx, gy = grids(rect, BODY)
        dx, dy = gx - x, gy - y
        theta = np.arctan2(dy, dx)
        edge = 1 + .06 * np.sin(5 * theta + 9 * now) + .04 * np.sin(8 * theta - 13 * now + 1.3)
        rho = np.hypot(dx, dy) / (radius * math.sqrt(f) * edge)
        # Two noise layers turning against each other give the energy inside its swirl.
        period = (2.6 * radius, 1.3 * radius)
        swirl = .5 * (axis_noise(rect, BODY, (x, y), (math.cos(1.7 * now), math.sin(1.7 * now)), period, (0, 0))
                      + axis_noise(rect, BODY, (x, y), (math.cos(-2.3 * now + 1), math.sin(-2.3 * now + 1)), period, (30, 11)))
        rho2 = np.square(rho)
        core = np.exp(-rho2 * (1 / .1444))
        body = np.exp(-rho2 * rho * (1 / .729))
        rim = np.exp(-np.square(rho - .98) * 100)
        heat = c01((core * 1.05 + body * (.3 + .6 * swirl) * .8 + rim * .55) * (gain * f))
        alpha = c01(body * 1.05 + rim * .5) * (1 - p) ** .5
        composite(out, rect, LUT[(heat * 255).astype(np.intp)] * alpha[:, :, None], alpha, BODY)

    def _sparks(self, out: Frame, x: float, y: float, radius: float, now: float, gain: float, p: float,
                level: float) -> None:
        """Short electric arcs hugging the ball and bright sparks circling it; scattering when it fizzles."""
        reach = int(2.6 * radius) + 6
        ox, oy = int(x) - reach, int(y) - reach
        canvas = np.zeros((2 * reach, 2 * reach, 3), np.uint8)
        c = (x - ox, y - oy)
        step = int(now * 22)
        rng = np.random.default_rng(step * 7919 + 13)
        fade = (1 - p) * gain
        for _ in range(3 + int(5 * level)):
            a = rng.uniform(0, TAU)
            length = rng.uniform(1.25, 2.1) * radius
            w = rng.uniform(.4, 1.0)
            points = []
            for i in range(7):
                s = i / 6
                d = (.8 + (length / radius - .8) * s) * radius
                wobble = rng.normal(0, .05 * radius * s) + math.sin(s * 9 + step) * .05 * radius
                points.append((round((c[0] + math.cos(a) * d - math.sin(a) * wobble) * 16),
                               round((c[1] + math.sin(a) * d + math.cos(a) * wobble) * 16)))
            pts = np.array(points, np.int32)
            cv2.polylines(canvas, [pts], False, scaled((255, 170, 60), .55 * fade * w), 3, cv2.LINE_AA, 4)
            cv2.polylines(canvas, [pts], False, scaled((255, 250, 230), .95 * fade * w), 1, cv2.LINE_AA, 4)
        for i in range(10):
            speed = (1.0 + .45 * ((i * 5) % 3)) * (1 if i % 2 else -1)
            a = i * 2.399 + speed * 2.4 * now
            d = radius * (1.2 + 2.6 * p * (1 + .3 * (i % 4))) if p > 0 else radius * (1.22 + .22 * math.sin(now * 5 + i * 1.7))
            ta = a - speed * .16
            head = (c[0] + math.cos(a) * d, c[1] + math.sin(a) * d * .92)
            tail = (c[0] + math.cos(ta) * d, c[1] + math.sin(ta) * d * .92)
            line(canvas, tail, head, scaled((255, 190, 90), .8 * fade ** 1.2), 2)
            dot(canvas, head, 1.4 + (i % 3) * .5, scaled((255, 252, 240), fade ** 1.2))
        paint(canvas, out, (ox, oy))


class EnergyWaveEffect(TeleportEffect):
    """The shot: flash, a beam widening towards the viewer, particles, and then the plain live frame again.

    The person is never hidden, the background plate is not used, and `hidden_target` is ignored; the
    effect starts and ends on the untouched live frame, so it can sit between any two frames of the camera.
    """
    action = True            # a one-shot that keeps the person on stage (neither exit/return nor toggle)
    persistent = False
    duration = 1.5
    SLOPE = .7               # half-width growth of the beam per pixel of length

    def __init__(self, subject: Silhouette | None, hidden_target: bool, started: float,
                 ball: tuple[float, float, float] | None = None, charge: float = 1.0,
                 shape: tuple[int, int] | None = None) -> None:
        # Not TeleportEffect.__init__: no cut-out of the person is needed, only a soft light mask.
        if subject is not None and (subject.mask.shape != subject.frame.shape[:2] or not np.isfinite(subject.mask).all()):
            raise ValueError('Recorte de pessoa inválido.')
        size = shape if subject is None else subject.frame.shape[:2]
        if size is None:
            raise ValueError('Dimensões do quadro desconhecidas.')
        self.subject, self.hidden_target, self.started = subject, False, started
        self.fh, self.fw = int(size[0]), int(size[1])
        fw, fh = self.fw, self.fh
        self.cut = person_cells(subject, (fw, fh))
        self.head = self._head()
        if ball is None or not all(math.isfinite(v) for v in ball):
            ball = self._default_ball()
        mx, my, hand = ball
        self.mx, self.my = min(max(mx, .03 * fw), .97 * fw), min(max(my, .05 * fh), .97 * fh)
        self.power = .72 + .28 * min(1.0, max(0.0, charge))
        self.r0 = float(min(max(hand * .95, .06 * fh), .2 * fh))
        self.ux, self.uy, self.length = self._aim()
        self.vx, self.vy = -self.uy, self.ux
        reach = self.r0 + self.SLOPE * self.length
        ex, ey = self.mx + self.ux * self.length, self.my + self.uy * self.length
        corners = [(self.mx + s * self.vx * self.r0, self.my + s * self.vy * self.r0) for s in (-1, 1)]
        corners += [(ex + s * self.vx * reach, ey + s * self.vy * reach) for s in (-1, 1)]
        pad = 4 * self.r0
        xs, ys = [p[0] for p in corners] + [self.mx - pad, self.mx + pad], [p[1] for p in corners] + [self.my - pad, self.my + pad]
        self.rect = align((min(xs) - 24, min(ys) - 24, max(xs) + 24, max(ys) + 24), (fw, fh))
        self.region = (0, 0, fw, fh)          # the shake and the flash may touch any pixel
        gx, gy = grids(self.rect)
        self.a0 = ((gx - self.mx) * self.ux + (gy - self.my) * self.uy).astype(np.float32)
        self.b0 = ((gy - self.my) * self.ux - (gx - self.mx) * self.uy).astype(np.float32)
        self.low = None if self.cut is None else np.ascontiguousarray(self.cut[0][cells(self.rect)])
        rng = np.random.default_rng(1983)
        self.streaks = [(rng.uniform(-.92, .92), rng.uniform(0, 1.2), rng.uniform(.8, 1.7), rng.uniform(.10, .30),
                         int(rng.integers(1, 3))) for _ in range(26)]
        self.embers = [(rng.uniform(.02, .85), rng.uniform(-1, 1), rng.uniform(.35, 1.1), rng.uniform(.5, .95),
                        rng.uniform(25, 130), rng.uniform(-45, 45), rng.uniform(15, 70), rng.uniform(1.0, 2.6))
                       for _ in range(70)]
        self.sparks = [(rng.normal(0, .55), rng.uniform(200, 900), rng.uniform(.12, .32), rng.uniform(.35, .7)) for _ in range(26)]

    def _head(self) -> tuple[float, float, float]:
        """Roughly where the face is (x, y, radius), so the beam can fly past it."""
        if self.cut is not None:
            low = self.cut[0]
            rows = np.flatnonzero(low.max(axis=1) > .4)
            if rows.size:
                top, height = int(rows[0]), max(1, int(rows[-1] - rows[0]))
                band = low[top:top + max(1, int(height * .2))]
                cols = np.flatnonzero(band.max(axis=0) > .4)
                if cols.size:
                    return (float(cols.mean() + .5) * S, float(top + height * .09) * S,
                            max(.08 * self.fh, .5 * float(cols[-1] - cols[0] + 1) * S))
        return self.fw * .5, self.fh * .3, .12 * self.fh

    def _default_ball(self) -> tuple[float, float, float]:
        """No hands known (manual trigger): in front of the chest, a little to the right of the head."""
        hx, hy, _ = self.head
        return min(self.fw * .9, hx + .2 * self.fw), min(self.fh * .85, hy + .4 * self.fh), self.fh * .12

    def _exit(self, ux: float, uy: float) -> float:
        """Distance from the muzzle to the frame border along (ux, uy)."""
        limits = []
        if ux > 1e-6:
            limits.append((self.fw - self.mx) / ux)
        elif ux < -1e-6:
            limits.append(-self.mx / ux)
        if uy > 1e-6:
            limits.append((self.fh - self.my) / uy)
        elif uy < -1e-6:
            limits.append(-self.my / uy)
        return min(limits) if limits else float(self.fh)

    def _clear(self, ux: float, uy: float) -> float:
        """How many beam half-widths the face lies from the beam body along (ux, uy); 1 is touching its edge."""
        hx, hy, radius = self.head
        a = (hx - self.mx) * ux + (hy - self.my) * uy
        b = abs((hy - self.my) * ux - (hx - self.mx) * uy)
        if a <= 0:
            return 9.0 if math.hypot(a, b) > 2 * self.r0 + radius else 0.0
        return max(0.0, b - radius) / (self.r0 + self.SLOPE * a)

    def _aim(self) -> tuple[float, float, float]:
        """Fly diagonally past the head towards the corner on the hands' side: long, wide and clear of the face."""
        hx = self.head[0]
        side = 1.0 if self.mx > hx else -1.0
        if abs(self.mx - hx) < .08 * self.fw:
            side = 1.0 if self.fw - self.mx >= self.mx else -1.0
        best = None
        for degrees in (38, 26, 50, 14, 62, 0, -20, -40, 75, -60):
            a = math.radians(degrees)
            ux, uy = side * math.cos(a), -math.sin(a)
            visible, clear = self._exit(ux, uy), self._clear(ux, uy)
            score = min(visible, .9 * self.fh) / (.9 * self.fh) + min(clear, 1.5) * 2
            if best is None or score > best[0]:
                best = (score, ux, uy, visible)
            if clear >= 1.5 and visible >= .5 * self.fh:
                best = (score, ux, uy, visible)
                break
        _, ux, uy, visible = best
        return ux, uy, max(.4 * self.fh, visible) * 1.2

    # ---- timeline -------------------------------------------------------------------
    def envelope(self, t: float) -> dict[str, float]:
        grow = lambda x: 1 - (1 - min(1.0, max(0.0, x))) ** 3
        return {
            'power': float(smooth(t / .045) * (1 - smooth((t - .95) / .5)) * self.power),
            'head': self.length * grow(t / .22),
            'width': (.35 + .65 * grow(t / .28)) * (1 - .55 * float(smooth((t - .85) / .6))),
            'burst': math.exp(-t / .11),
            'flash': math.exp(-((t - .05) / .075) ** 2),
            'breakup': .85 * float(smooth((t - .88) / .56)),
            'shake': 7.0 * self.power * math.exp(-t / .30) * float(smooth(t / .02)),
        }

    def shake(self, t: float) -> tuple[int, int]:
        amp = self.envelope(t)['shake']
        return round(amp * math.sin(TAU * 17 * t + .6)), round(.7 * amp * math.cos(TAU * 21 * t))

    def render(self, live: Frame, background: Frame | None, now: float) -> Frame:
        if live.shape[:2] != (self.fh, self.fw) or (self.subject is not None and live.shape != self.subject.frame.shape):
            raise ValueError('Resolução mudou durante o efeito.')
        t = float(now - self.started)
        if t <= 0 or t >= self.duration:
            return live.copy()
        env = self.envelope(t)
        dx, dy = self.shake(t)
        out = shifted(live, dx, dy)
        mx, my = self.mx + dx, self.my + dy
        self._beam(out, live, t, env, mx, my)
        self._lines(out, t, env, mx, my)
        if env['flash'] > .02:
            k = .2 * env['flash'] * self.power
            out = cv2.add(out, (round(255 * k), round(246 * k), round(215 * k), 0))
        return out

    def _beam(self, out: Frame, live: Frame, t: float, env: dict[str, float], mx: float, my: float) -> None:
        rect = self.rect
        power, head, width = env['power'], env['head'], env['width']
        sx, sy = mx - self.mx, my - self.my
        a = self.a0 - (sx * self.ux + sy * self.uy)
        b = self.b0 - (sy * self.ux - sx * self.uy)
        length, r0 = self.length, self.r0
        w = np.maximum(a, 0)
        w *= width * self.SLOPE
        w += width * r0
        axis = (self.ux, self.uy)
        flow = axis_noise(rect, S, (mx, my), axis, (1.1 * length, .55 * length), (-t * 110, 0))
        det = axis_noise(rect, S, (mx, my), axis, (.5 * length, .12 * length), (-t * 260, 9))
        d = np.abs(b)
        d /= w * (1 + .3 * (flow - .5))
        d2 = np.square(d)
        front = c01((head - a) * (1 / (.1 * length)))
        back = c01((a + .6 * r0) * (1 / (.8 * r0)))
        energy = front * back * (.88 + .12 * np.cos(a * (TAU / (.3 * length)) - TAU * 2.3 * t))
        rr2 = np.square(a) + np.square(b)
        burst = np.exp(-rr2 * (1 / (r0 * (1.0 + 1.8 * float(smooth(t / .14)))) ** 2)) * env['burst']
        mod = .62 + .75 * det
        heat = energy * (.3 * np.exp(-np.square(d2)) * mod + .46 * np.exp(-d2 * (1 / .4)) + .62 * np.exp(-d2 * (1 / .06)))
        heat += burst * 1.2
        alpha = np.exp(-np.square(d2)) * (.55 + .6 * mod)
        alpha *= energy
        alpha += burst
        alpha *= power * c01((flow - env['breakup']) * 3 + 1)
        alpha = c01(alpha)
        if self.low is not None:
            alpha *= 1 - .5 * self.low
        layer = LUT[(c01(heat) * 255).astype(np.intp)] * alpha[:, :, None]
        halo = np.exp(-d2 * (1 / 3.6)) * energy * (.5 * power)
        halo += np.exp(-rr2 * (1 / (2.0 * r0) ** 2)) * (.4 * env['flash'])
        halo *= tone(live, rect, d.shape)
        layer += halo[:, :, None] * GLOW
        if self.low is not None:
            layer += (self.low * halo * .6)[:, :, None] * SKY
        composite(out, rect, layer, alpha)

    def _lines(self, out: Frame, t: float, env: dict[str, float], mx: float, my: float) -> None:
        """Energy streaks flowing along the cone, the shock ring at the muzzle, sparks and embers."""
        x0, y0, x1, y1 = self.rect
        canvas = np.zeros((y1 - y0, x1 - x0, 3), np.uint8)
        ox, oy = x0, y0
        power, head, width, length, r0 = env['power'], env['head'], env['width'], self.length, self.r0
        ux, uy, vx, vy = self.ux, self.uy, self.vx, self.vy
        at = lambda s, lat: (mx + ux * s + vx * lat * width * (r0 + self.SLOPE * max(s, 0)) * .92 - ox,
                             my + uy * s + vy * lat * width * (r0 + self.SLOPE * max(s, 0)) * .92 - oy)
        for lat, phase, speed, span, thick in self.streaks:
            tail = ((phase + speed * t * 1.15) % 1.25) * length - span * length * .2
            s0, s1 = max(0.0, tail), min(head, tail + span * length)
            if s1 - s0 < 4:
                continue
            k = power * (1 - abs(lat) ** 1.6) * (.45 + .55 * ((phase * 7) % 1))
            line(canvas, at(s0, lat), at(s1, lat), scaled((255, 190, 90), .5 * k), thick + 2)
            line(canvas, at(s0, lat), at(s1, lat), scaled((255, 250, 235), k), thick)
        if t < .3:
            fade = (1 - t / .3) ** 1.3 * self.power
            for i in range(13):                  # a starburst at the muzzle as the ball lets go, towards the beam
                angle = math.atan2(uy, ux) + (i / 12 - .5) * 1.9 + .05 * ((i * 5) % 3)
                near, far = r0 * (.5 + .4 * ((i * 7) % 3)), r0 * (2.2 + 2.6 * ((i * 5) % 4) / 3) * (.5 + t / .3)
                c = (mx - ox, my - oy)
                line(canvas, (c[0] + math.cos(angle) * near, c[1] + math.sin(angle) * near),
                     (c[0] + math.cos(angle) * far, c[1] + math.sin(angle) * far), scaled((255, 245, 215), fade), 2)
        for side, speed, delay, life in self.sparks:
            age = (t - delay * .3) / life
            if not 0 < age < 1:
                continue
            angle = math.atan2(uy, ux) + side
            d = speed * (1 - (1 - age) ** 2) * life
            tail = speed * (1 - (1 - max(0.0, age - .12)) ** 2) * life
            c = (mx - ox, my - oy)
            line(canvas, (c[0] + math.cos(angle) * tail, c[1] + math.sin(angle) * tail),
                 (c[0] + math.cos(angle) * d, c[1] + math.sin(angle) * d), scaled((255, 240, 200), (1 - age) * self.power), 2)
        for s, lat, born, life, drift, side, rise, size in self.embers:
            age = (t - (.55 + .35 * born)) / life
            if not 0 < age < 1:
                continue
            base = at(s * length, lat)
            px = base[0] + (ux * drift + vx * side) * age * life
            py = base[1] + (uy * drift + vy * side) * age * life - rise * age * life
            k = (1 - age) ** 1.4 * (.6 + .4 * math.sin(age * 40 + s * 30))
            dot(canvas, (px, py), size * (1 - .5 * age), scaled((255, 235, 170), k))
        paint(canvas, out, (ox, oy))
