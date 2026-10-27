"""Portal exit/return: a swirling vortex opens beside the person and pulls them in."""
from __future__ import annotations

import math

import cv2
import numpy as np

from .effects import Silhouette, TeleportEffect, smooth
from .scene import Frame

S = 4  # downscale factor of the soft fields (vortex, glow); the person stays full-res
TAU = 2 * math.pi

# BGR palette (0..1): white-hot rim, orange core, cyan fringe, violet depth.
HOT = np.array((0.82, 0.93, 1.0), np.float32)
ORANGE = np.array((0.10, 0.52, 1.0), np.float32)
CYAN = np.array((1.0, 0.74, 0.28), np.float32)
VIOLET = np.array((0.80, 0.18, 0.55), np.float32)
DEEP = np.array((0.16, 0.04, 0.10), np.float32)


def _c01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _back_out(x: float, c: float = 1.2) -> float:
    x = _c01(x) - 1.0
    return 1.0 + (c + 1.0) * x ** 3 + c * x ** 2


def _bump(p: float, at: float, width: float) -> float:
    return math.exp(-((p - at) / width) ** 2)


def _tile_noise(rows: int, cols: int, rng: np.random.Generator) -> np.ndarray:
    """Seamlessly tileable fractal noise in 0..1."""
    total = np.zeros((rows, cols), np.float32)
    amp = 1.0
    for cells in (4, 8, 16):
        lat = rng.random((cells, cells * 2)).astype(np.float32)
        padded = np.pad(lat, 2, mode='wrap')
        big = cv2.resize(padded, (padded.shape[1] * (cols // (cells * 2)), padded.shape[0] * (rows // cells)),
                         interpolation=cv2.INTER_CUBIC)
        k0, k1 = 2 * (rows // cells), 2 * (cols // (cells * 2))
        total += big[k0:k0 + rows, k1:k1 + cols] * amp
        amp *= 0.55
    total -= total.min()
    return total / max(float(total.max()), 1e-6)


def blend_rest(effect: 'PortalEffect', out: np.ndarray) -> None:
    pl, pt, pr, pb = effect.person_box
    prem = effect.prem
    inv = cv2.cvtColor(255 - prem[:, :, 3], cv2.COLOR_GRAY2BGR)
    out[pt:pb, pl:pr] = cv2.add(cv2.multiply(out[pt:pb, pl:pr], inv, scale=1 / 255.0),
                                cv2.cvtColor(prem, cv2.COLOR_BGRA2BGR))


class PortalEffect(TeleportEffect):
    duration = 1.15
    eager = False  # streaks/halo from the base class are not used

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        height, width = subject.mask.shape
        pl, pt, pr, pb = self.box
        bw, bh = pr - pl, pb - pt
        self.size = (width, height)
        # Portal on the side with more free space, half behind the shoulder.
        side = 1 if width - pr >= pl else -1
        ry = min(0.40 * height, 0.62 * bh)
        rx = 0.50 * ry
        edge = pr if side > 0 else pl
        cx = edge + side * rx * 0.30
        cx = min(max(cx, rx * 1.15), width - rx * 1.4)
        cy = min(max(pt + 0.52 * bh, ry * 1.1), height - ry * 1.1)
        self.c = (float(cx), float(cy))
        self.r = (float(rx), float(ry))
        # Fixed glow rect (portal plus bloom), aligned to the low-res grid.
        self.prect = self._align(cx - 1.85 * rx, cy - 1.85 * ry, cx + 1.85 * rx, cy + 1.85 * ry)
        # Person: premultiplied BGRA at full resolution.
        a8 = cv2.convertScaleAbs(self.alpha, alpha=255.0)
        prem = cv2.multiply(self.person, cv2.cvtColor(a8, cv2.COLOR_GRAY2BGR), scale=1 / 255.0)
        self.prem = cv2.merge([prem[:, :, 0], prem[:, :, 1], prem[:, :, 2], a8])
        # Where the cutout is cut by the frame border, feather it while it moves and ignore the cut for rim light.
        cut = self.alpha
        touch = (pl <= 0 and cut[:, 0].max() > 0.3, pt <= 0 and cut[0, :].max() > 0.3,
                 pr >= width and cut[:, -1].max() > 0.3, pb >= height and cut[-1, :].max() > 0.3)
        pad = 32
        wrap = self.alpha
        for amounts in ((pad, 0, 0, 0), (0, pad, 0, 0), (0, 0, pad, 0), (0, 0, 0, pad)):
            wrap = cv2.copyMakeBorder(wrap, *amounts, cv2.BORDER_CONSTANT, value=0)
        if any(touch):
            xs = np.arange(bw, dtype=np.float32)
            ys = np.arange(bh, dtype=np.float32)
            dx = np.full(bw, 1e4, np.float32)
            dy = np.full(bh, 1e4, np.float32)
            if touch[0]: dx = np.minimum(dx, xs)
            if touch[2]: dx = np.minimum(dx, bw - 1 - xs)
            if touch[1]: dy = np.minimum(dy, ys)
            if touch[3]: dy = np.minimum(dy, bh - 1 - ys)
            dist = np.minimum(dy[:, None], dx[None, :])
            ramp = np.clip(dist / 140.0, 0, 1)
            ramp = ramp * ramp * (3 - 2 * ramp)
            for amounts in ((pad, 0, 0, 0), (0, pad, 0, 0), (0, 0, pad, 0), (0, 0, 0, pad)):
                ramp = cv2.copyMakeBorder(ramp, *amounts, cv2.BORDER_CONSTANT, value=1.0)
            wrap = cv2.merge([wrap, ramp])
            self.ramp = True
        else:
            self.ramp = None
        size = (-(-wrap.shape[1] // S), -(-wrap.shape[0] // S))
        self.wrap_lr = cv2.resize(wrap, size, interpolation=cv2.INTER_AREA)
        self.wrap_scale = (wrap.shape[1] / size[0], wrap.shape[0] / size[1])
        self.pad = pad
        self.p0 = (pl + bw / 2.0, pt + bh / 2.0)
        self.person_box = (pl, pt, pr, pb)
        self.hrad = 0.5 * math.hypot(bw, bh)
        # Motion direction towards the portal and a curved path bulging upwards.
        vx, vy = cx - self.p0[0], cy - self.p0[1]
        dist = math.hypot(vx, vy) or 1.0
        self.u = (vx / dist, vy / dist)
        self.bulge = -0.22 * dist if abs(vx) > abs(vy) else 0.22 * dist
        # Working ROI = person (with room to twirl/bulge) + portal rect.
        pad = int(0.14 * max(bw, bh) + abs(self.bulge))
        roi = self._align(min(pl - pad, self.prect[0]), min(pt - pad, self.prect[1]),
                          max(pr + pad, self.prect[2]), max(pb + pad, self.prect[3]))
        self.box = roi
        # Low-res coordinate grids (cell centres in frame pixels).
        lw, lh = -(-width // S), -(-height // S)
        xs = np.arange(lw, dtype=np.float32) * S + (S - 1) / 2
        ys = np.arange(lh, dtype=np.float32) * S + (S - 1) / 2
        self.gx = np.broadcast_to(xs[None, :], (lh, lw))
        self.gy = np.broadcast_to(ys[:, None], (lh, lw))
        sl = self._cells(self.prect)
        self.pdxn = np.ascontiguousarray((self.gx[sl] - cx) / rx, np.float32)
        self.pdyn = np.ascontiguousarray((self.gy[sl] - cy) / ry, np.float32)
        self._bg_key = None
        self._pending = None
        self._cover = np.zeros((lh, lw), np.float32)
        self.pal_solid = np.stack((DEEP, VIOLET, CYAN, ORANGE, HOT)).astype(np.float32) * 255.0
        self.pal_add = np.stack((CYAN, VIOLET, ORANGE, HOT)).astype(np.float32)
        self.tint = np.array((1.0, 0.75, 1.0), np.float32)
        rng = np.random.default_rng(1207)
        self.noise = _tile_noise(64, 128, rng)
        self.sparks = [(float(rng.uniform(0, TAU)), float(rng.uniform(0.12, 0.85)), float(rng.uniform(0.0, 0.3)),
                        int(rng.integers(0, 3)), int(rng.integers(1, 3))) for _ in range(34)]
        self.spark_colors = [(255, 240, 210), (90, 190, 255), (255, 215, 90)]

    def _align(self, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        w, h = self.size
        x0 = max(0, int(x0) // S * S)
        y0 = max(0, int(y0) // S * S)
        x1 = min(w, -(-int(math.ceil(x1)) // S) * S)
        y1 = min(h, -(-int(math.ceil(y1)) // S) * S)
        return x0, y0, x1, y1

    def _cells(self, rect):
        x0, y0, x1, y1 = rect
        return slice(y0 // S, -(-y1 // S)), slice(x0 // S, -(-x1 // S))

    def _up(self, img: np.ndarray, rect) -> np.ndarray:
        x0, y0, x1, y1 = rect
        w, h = x1 - x0, y1 - y0
        out = cv2.resize(img, ((img.shape[1]) * S, (img.shape[0]) * S), interpolation=cv2.INTER_LINEAR)
        return out[:h, :w]

    # ---- timeline ---------------------------------------------------------------
    def _pull(self, p: float) -> float:
        """Person progress towards the portal: 0 in place, 1 inside the portal."""
        if self.hidden_target:
            anticipation = -0.05 * math.sin(math.pi * _c01((p - 0.16) / 0.13))
            return anticipation + _c01((p - 0.28) / 0.46) ** 2.3
        return 1.0 - _back_out((p - 0.10) / 0.62, 1.25)

    def _portal(self, p: float):
        """Return (open scale x, y, intensity, flash, spark events)."""
        if self.hidden_target:
            o = smooth(p / 0.20)
            close = _c01((p - 0.76) / 0.14) ** 2
            flash = 0.25 * _bump(p, 0.03, 0.03) + _bump(p, 0.775, 0.04)
            events = ((0.77, 1.0),)
        else:
            o = smooth(p / 0.12)
            close = _c01((p - 0.80) / 0.12) ** 1.6
            flash = _bump(p, 0.07, 0.04) + 0.5 * _bump(p, 0.84, 0.035)
            events = ((0.06, 0.9), (0.83, 0.45))
        sc = 1.0 - close
        ay = smooth(_c01(o * 1.8)) * sc ** 0.6
        ax = (0.04 + 0.96 * smooth(_c01((o - 0.05) / 0.95)) ** 1.4) * sc ** 1.6 * (1.0 if o > 0 else 0.0)
        power = _c01(o * 4) * _c01(sc * 3)
        return ax, ay, power, flash, events

    def _pos(self, e: float):
        px, py = self.p0
        ux, uy = self.u
        bend = math.sin(math.pi * min(max(e, 0.0), 1.0)) * self.bulge
        return (px + (self.c[0] - px) * e - uy * bend, py + (self.c[1] - py) * e + ux * bend)

    # ---- rendering --------------------------------------------------------------
    def render(self, live: Frame, background: Frame, now: float) -> Frame:
        if live.shape != background.shape or live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')
        p = min(1.0, max(0.0, (now - self.started) / self.duration))
        if p >= 1:
            return background.copy() if self.hidden_target else live.copy()
        if p <= 0:
            return live.copy() if self.hidden_target else background.copy()
        out = background.copy()
        t = p * self.duration
        ax, ay, power, flash, events = self._portal(p)
        e = self._pull(p)
        portal_on = ax > 0.012 and ay > 0.012
        sparks = [(max(0.0, (p - t0) / 0.2), k) for t0, k in events if 0 <= p - t0 < 0.2]
        glow = np.zeros(self.gx.shape + (3,), np.float32)
        gl_rect = None

        # Person: full-resolution remap of the captured cutout.
        fade = smooth((0.99 - e) / 0.14) if not self.hidden_target else 1 - smooth((e - 0.86) / 0.14)
        person_rect = None
        self._pending = None
        self._cover.fill(0)
        if fade > 0.004 and e < 1.0:
            person_rect = self._person(out, e, fade, p, glow)

        if portal_on or sparks:
            gl_rect = self.prect
            if portal_on:
                self._portal_layers(out, background, ax, ay, power, flash, t, p, sparks, glow)

        if self._pending is not None:
            sl2, layer = self._pending
            glow[sl2] += layer * (1.0 - self._cover[sl2])[:, :, None]
        rects = [r for r in (gl_rect, person_rect) if r is not None]
        if not rects:
            return out
        ux0 = min(r[0] for r in rects)
        uy0 = min(r[1] for r in rects)
        ux1 = max(r[2] for r in rects)
        uy1 = max(r[3] for r in rects)
        rect = (ux0, uy0, ux1, uy1)
        sl = self._cells(rect)
        g8 = np.clip(glow[sl] * 255.0, 0, 255).astype(np.uint8)
        g_up = self._up(g8, rect)
        if sparks:
            self._draw_sparks(g_up, rect, sparks)
        region = out[uy0:uy1, ux0:ux1]
        out[uy0:uy1, ux0:ux1] = cv2.add(region, g_up)
        return out

    def _person(self, out, e, fade, p, glow):
        pl, pt, _, _ = self.person_box
        pos = self._pos(e)
        ec = min(max(e, 0.0), 1.0)
        s = max(0.035, (1.0 - ec)) ** 1.1 * (1.0 - 0.5 * min(e, 0.0)) if e < 1 else 0.035
        s = max(0.035, s)
        stretch = 0.35 * math.sin(math.pi * ec) ** 1.3
        twist = 2.6 * ec ** 1.4
        bw, bh = self.person_box[2] - pl, self.person_box[3] - pt
        mix = _c01(twist / 1.0)
        hx = (bw / 2 * (1 - mix) + self.hrad * mix) * s * (1 + stretch) * 1.1 + 10
        hy = (bh / 2 * (1 - mix) + self.hrad * mix) * s * (1 + stretch * 0.5) * 1.1 + 10
        rect = self._align(pos[0] - hx, pos[1] - hy, pos[0] + hx, pos[1] + hy)
        bx0, by0, bx1, by1 = self.box
        rect = (max(rect[0], bx0), max(rect[1], by0), min(rect[2], bx1), min(rect[3], by1))
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        if abs(e) < 0.003:
            # At rest the cutout is untouched: blend it straight from the captured crop.
            blend_rest(self, out)
            return self._align(*self.person_box)
        sl = self._cells(rect)
        ux, uy = self.u
        dx = self.gx[sl] - pos[0]
        dy = self.gy[sl] - pos[1]
        rad = self.hrad * s + 1.0
        rho = np.sqrt(dx * dx + dy * dy) / rad
        phi = twist * (1.0 - np.clip(rho / 1.25, 0, 1)) ** 2
        c, sn = np.cos(phi), np.sin(phi)
        dx2 = c * dx + sn * dy
        dy2 = c * dy - sn * dx
        du = dx2 * ux + dy2 * uy
        dv = dy2 * ux - dx2 * uy
        taper = 1.0 + 0.55 * ec * np.clip(du / rad, -1, 1)
        su = du / (s * (1 + stretch))
        sv = dv * (1 + 0.35 * stretch) * taper / s
        srcx = (self.p0[0] - pl) + su * ux - sv * uy
        srcy = (self.p0[1] - pt) + su * uy + sv * ux
        maps = self._up(np.stack((srcx, srcy), axis=-1).astype(np.float32), rect)
        rem = cv2.remap(self.prem, maps, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        # Low-res lookups through the same warp: silhouette (rim light) and border feather.
        lh, lw = srcx.shape
        kx, ky = self.wrap_scale
        lowmap = np.stack(((srcx + self.pad) / kx - 0.5, (srcy + self.pad) / ky - 0.5), axis=-1)
        look = cv2.remap(self.wrap_lr, lowmap.astype(np.float32), None, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 1) if self.ramp is not None else 0)
        if self.ramp is not None:
            aq, ramp = look[:, :, 0], look[:, :, 1]
            g = min(ec * 3.0, 1.0)
            gain_lr = 1.0 - g * (1.0 - ramp)
            rows = np.flatnonzero(gain_lr.min(axis=1) < 0.99)
            if rows.size:
                r0, r1 = max(0, (int(rows[0]) - 1) * S), min(rem.shape[0], (int(rows[-1]) + 2) * S)
                gain = cv2.convertScaleAbs(self._up(gain_lr.astype(np.float32), rect)[r0:r1], alpha=255.0)
                rem[r0:r1] = cv2.multiply(rem[r0:r1], cv2.cvtColor(gain, cv2.COLOR_GRAY2BGRA), scale=1 / 255.0)
            aq = aq * gain_lr
        else:
            aq = look
        if fade < 0.999:
            rem = cv2.convertScaleAbs(rem, alpha=fade)
        inv = cv2.cvtColor(255 - rem[:, :, 3], cv2.COLOR_GRAY2BGR)
        region = out[rect[1]:rect[3], rect[0]:rect[2]]
        out[rect[1]:rect[3], rect[0]:rect[2]] = cv2.add(cv2.multiply(region, inv, scale=1 / 255.0),
                                                        cv2.cvtColor(rem, cv2.COLOR_BGRA2BGR))
        # Light from the portal: rim wrap on the silhouette and a streak behind the motion.
        near = _c01(0.1 + 1.6 * ec) * _c01(self._portal(p)[2] * 1.5)
        inner = aq * (1.0 - cv2.GaussianBlur(aq, (0, 0), 2.2))
        halo = cv2.GaussianBlur(aq, (0, 0), 2.0) * (1.0 - aq)
        wrap = (inner * 1.0 + halo * 0.7) * near
        layer = wrap[:, :, None] * (0.75 * ORANGE + 0.25 * HOT)
        prev = self._pos(self._pull(max(0.0, p - 0.04)))
        vx, vy = (pos[0] - prev[0]) / S, (pos[1] - prev[1]) / S
        speed = math.hypot(vx, vy)
        if speed > 0.6:
            n = int(min(14, speed * 1.6))
            kern = np.zeros((2 * n + 1, 2 * n + 1), np.float32)
            for k in range(n + 1):
                kern[int(round(n + vy / speed * k)), int(round(n + vx / speed * k))] = 1.0 - k / (n + 1)
            kern /= kern.sum()
            smear = cv2.filter2D(aq, -1, kern)
            trail = np.clip(smear - aq, 0, 1) * _c01(speed / 12.0) * 0.6
            layer += trail[:, :, None] * (0.6 * CYAN + 0.5 * HOT)
        sl2 = (slice(rect[1] // S, rect[1] // S + lh), slice(rect[0] // S, rect[0] // S + lw))
        self._pending = (sl2, layer)
        return rect

    def _background_lr(self, background: Frame) -> tuple[np.ndarray, np.ndarray]:
        """Low-res background of the portal rect and its luma, cached while the background is unchanged."""
        x0, y0, x1, y1 = self.prect
        probe = background[y0:y1:97, x0:x1:89].tobytes()
        if self._bg_key != probe:
            lh, lw = self.pdxn.shape
            lr = cv2.resize(background[y0:y1, x0:x1], (lw, lh), interpolation=cv2.INTER_AREA)
            self._bg_cache = (lr, cv2.cvtColor(lr, cv2.COLOR_BGR2GRAY).astype(np.float32) * (1 / 255.0))
            self._bg_key = probe
        return self._bg_cache

    def _portal_layers(self, out, background, ax, ay, power, flash, t, p, sparks, glow):
        rect = self.prect
        x0, y0, x1, y1 = rect
        sl = self._cells(rect)
        cx, cy = self.c
        rx, ry = self.r
        ax, ay = max(ax, 0.02), max(ay, 0.02)
        dxn, dyn = self.pdxn, self.pdyn
        dx, dy = dxn * (1 / ax), dyn * (1 / ay)
        r = np.sqrt(dx * dx + dy * dy)
        th = np.arctan2(dy, dx)
        spin = t + 0.5 * (1 - power) ** 2
        rw = r / (1 + 0.022 * np.sin(3 * th + 6 * t) + 0.014 * np.sin(5 * th - 8 * t + 1))
        inner = np.clip(1.0 - rw, 0, 1)
        twist = th + 2.8 * inner ** 1.5 - 5.5 * spin
        nh, nw = self.noise.shape
        mapx = np.mod(twist * (nw / TAU), nw)
        mapy = np.mod((r * 0.55 - 0.9 * t) * nh, nh)
        noise = cv2.remap(self.noise, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        arms = (0.5 + 0.5 * np.cos(3 * twist)) ** 1.6
        # Background seen through the portal, twirled and darkened.
        bg, lum = self._background_lr(background)
        ang = 2.4 * inner ** 1.3 + 1.2 * spin
        ca, sa = np.cos(ang), np.sin(ang)
        k = 0.45 + 0.55 * np.clip(rw, 0, 1)
        qx, qy = (dxn * ca - dyn * sa) * k, (dxn * sa + dyn * ca) * k
        sx = (qx * (rx / S) + ((cx - x0) / S - 0.5)).astype(np.float32)
        sy = (qy * (ry / S) + ((cy - y0) / S - 0.5)).astype(np.float32)
        seen = cv2.remap(bg, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        # Interior and rim as weights over a small palette, resolved by one matrix product.
        brightness = arms * (0.45 + 0.9 * noise) * (0.30 + 0.7 * (1 - inner) ** 0.8) * 0.85
        depth = 0.30 + 0.70 * np.clip(r * 1.25, 0, 1) ** 1.2
        aa = max(0.04, min(1.0, 5.0 / (rx * ax)))
        cover = np.clip((1.0 - rw) / aa + 0.5, 0, 1) * min(1.0, power * 1.2 + 0.2)
        mod = 0.78 + 0.45 * noise + 0.12 * np.cos(2 * twist)
        d = rw - 1.0
        hot = np.exp(-(d / 0.035) ** 2)
        pulse = 1.0 + 0.06 * math.sin(10 * t)
        ra = np.clip(np.exp(-(d / 0.075) ** 2) * np.clip(mod, 0, 1.15) * (0.95 * pulse), 0, 1) * power
        fa = np.exp(-((d - 0.13) / 0.11) ** 2) * np.clip(d * 14, 0, 1) * (0.42 * power)
        rim_a = 1 - (1 - ra) * (1 - fa)
        hn = np.clip(hot * 1.2, 0, 1)
        kd = cover * (1 - rim_a) * depth
        kb = kd * brightness
        weights = np.stack((kd, kb * (1 - noise), kb * noise + fa * (1 - ra), ra * (1 - hn), ra * hn), axis=-1)
        prem_f = weights @ self.pal_solid
        prem_f += seen * ((kd * (0.30 / 255.0))[:, :, None] * self.tint)
        bloom = np.exp(-(d / 0.55) ** 2) * np.clip((1.75 - rw) / 0.5, 0, 1) * (0.22 * power) * (1.0 - 0.5 * lum)
        wo = hot * mod * (0.35 * pulse * power)
        wc, wh = bloom * 0.4, np.zeros_like(bloom)
        if flash > 0.01:
            rn = np.sqrt(dxn * dxn + dyn * dyn)
            burst = np.exp(-(rn / 0.8) ** 2) * (0.55 * flash)
            wo = wo + burst * 0.4
            wh = burst * 0.6 + np.exp(-(rn / 0.22) ** 2) * flash
            for ts, strength in sparks:
                wc = wc + np.exp(-((rn - (0.9 + 0.8 * ts)) / 0.09) ** 2) * ((1 - ts) * 0.6 * strength)
        glow[sl] += np.stack((wc, bloom * 0.6, wo, wh), axis=-1) @ self.pal_add
        self._cover[sl] = cover
        prem = cv2.convertScaleAbs(prem_f)
        a8 = cv2.convertScaleAbs(rim_a + cover * (1 - rim_a), alpha=255.0)
        up = self._up(cv2.merge([prem[:, :, 0], prem[:, :, 1], prem[:, :, 2], a8]), rect)
        inv = cv2.cvtColor(255 - up[:, :, 3], cv2.COLOR_GRAY2BGR)
        region = out[y0:y1, x0:x1]
        out[y0:y1, x0:x1] = cv2.add(cv2.multiply(region, inv, scale=1 / 255.0), cv2.cvtColor(up, cv2.COLOR_BGRA2BGR))

    def _draw_sparks(self, canvas: np.ndarray, rect, sparks) -> None:
        x0, y0, _, _ = rect
        cx, cy = self.c
        rx, ry = self.r
        for ts, strength in sparks:
            fade = strength
            if fade <= 0.02:
                continue
            for phi, speed, delay, color_i, thick in self.sparks:
                te = _c01((ts - delay) / (1 - delay))
                if te <= 0 or te >= 1:
                    continue
                head = 0.78 + 0.2 * speed + speed * (1 - (1 - te) ** 2)
                tt = max(0.0, te - 0.08)
                tail = 0.78 + 0.2 * speed + speed * (1 - (1 - tt) ** 2)
                a = phi
                p1 = (cx + math.cos(a) * rx * head - x0, cy + math.sin(a) * ry * head + 0.30 * ry * te * te - y0)
                p0 = (cx + math.cos(a) * rx * tail - x0, cy + math.sin(a) * ry * tail + 0.30 * ry * tt * tt - y0)
                col = tuple(int(c * min(1.0, strength * (1 - te) ** 1.2 * 1.5)) for c in self.spark_colors[color_i])
                cv2.line(canvas, (int(p0[0] * 16), int(p0[1] * 16)), (int(p1[0] * 16), int(p1[1] * 16)), col, thick + 1,
                         cv2.LINE_AA, 4)
                cv2.circle(canvas, (int(p1[0] * 16), int(p1[1] * 16)), 2 * 16 // 2, col, -1, cv2.LINE_AA, 4)
