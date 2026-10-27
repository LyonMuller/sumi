"""Spirit bomb: a giant ball gathers above the raised hands, then flies at the camera and bursts.

Like the energy wave, nothing here hides the person. `SpiritCharge` is the live overlay while the
arms are up (the wave's ball, larger, with streaks of energy flowing in from the edges of the
frame); `SpiritBombEffect` is the one-shot throw: the ball grows towards the viewer until it fills
the frame, a white flash, a shock ring and the shake, then the untouched live frame again.
Every animation is a function of elapsed time only.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .effects import Silhouette, TeleportEffect, smooth
from .effects_energy import (GLOW, ICE, S, TAU, EnergyCharge, align, composite, dot, flicker, grids, line,
                             paint, scaled, shifted, tone)
from .scene import Frame

PALE = (255, 236, 190)      # BGR: the near-white blue of the gathered energy
DEEP = (255, 170, 70)


class SpiritCharge(EnergyCharge):
    """The giant ball above the raised hands, fed by streaks of energy from every side."""
    FIZZLE = .6

    def _radius(self, size: float, level: float, now: float, p: float, shape: tuple[int, int]) -> float:
        grow = float(smooth((now - self.since) / .35))
        return min(.34 * min(shape), max(14.0, size * (.22 + .85 * level ** .8) * grow * (1 - p) ** 2))

    def render(self, live: Frame, now: float) -> Frame:
        out = super().render(live, now)
        if self.pos is None or not self.active(now):
            return out
        fh, fw = out.shape[:2]
        x, y, size = self.pos
        p = 0.0 if self.state == 'charging' else min(1.0, (now - self.lost) / self.FIZZLE)
        radius = self._radius(size, self.level, now, p, (fh, fw))
        self._gather(out, x, y, radius, now, (1 - p) * (.55 + .45 * self.level))
        return out

    @staticmethod
    def _gather(out: Frame, x: float, y: float, radius: float, now: float, fade: float) -> None:
        """Thin streaks rushing in from far away to the ball, staggered so the flow never stops."""
        if fade <= .02:
            return
        fh, fw = out.shape[:2]
        far = math.hypot(fw, fh) * .75
        canvas = np.zeros_like(out)
        for i in range(28):
            angle = i * 2.399 + .3 * math.sin(i * 1.7)
            cycle = .75 + .35 * ((i * 7) % 5) / 4
            age = ((now / cycle) + i * .137) % 1.0
            d0 = radius * 1.05 + (far - radius) * (1 - age) ** 1.6
            d1 = d0 + (40 + 90 * (1 - age)) * (1 + .4 * (i % 3))
            ca, sa = math.cos(angle), math.sin(angle)
            k = fade * smooth(age / .2) * (1 - smooth((age - .85) / .15))
            line(canvas, (x + ca * d0, y + sa * d0), (x + ca * d1, y + sa * d1), scaled(DEEP, .45 * k), 3)
            line(canvas, (x + ca * d0, y + sa * d0), (x + ca * d1, y + sa * d1), scaled(PALE, .9 * k), 1)
            dot(canvas, (x + ca * d0, y + sa * d0), 1.6, scaled(PALE, k))
        paint(canvas, out, (0, 0))


class SpiritBombEffect(TeleportEffect):
    """The throw: the ball flies at the camera, fills the frame, bursts in white light and fades away.

    The person is never hidden, the background plate is not used, and `hidden_target` is ignored.
    """
    action = True
    persistent = False
    duration = 2.0
    IMPACT = .55             # seconds until the ball fills the frame

    def __init__(self, subject: Silhouette | None, hidden_target: bool, started: float,
                 ball: tuple[float, float, float] | None = None, charge: float = 1.0,
                 shape: tuple[int, int] | None = None) -> None:
        if subject is not None and (subject.mask.shape != subject.frame.shape[:2] or not np.isfinite(subject.mask).all()):
            raise ValueError('Recorte de pessoa inválido.')
        size = shape if subject is None else subject.frame.shape[:2]
        if size is None:
            raise ValueError('Dimensões do quadro desconhecidas.')
        self.subject, self.hidden_target, self.started = subject, False, started
        self.fh, self.fw = int(size[0]), int(size[1])
        self.region = (0, 0, self.fw, self.fh)
        if ball is None or not all(math.isfinite(v) for v in ball):
            ball = (self.fw * .5, self.fh * .16, self.fh * .26)
        bx, by, face = ball
        self.power = .75 + .25 * min(1.0, max(0.0, charge))
        self.mx = min(max(bx, .05 * self.fw), .95 * self.fw)
        self.my = min(max(by, .04 * self.fh), .9 * self.fh)
        self.r0 = float(min(.34 * min(self.fh, self.fw), max(14.0, face * (.22 + .85 * min(1.0, max(0.0, charge)) ** .8))))
        self.cx, self.cy = self.fw * .5, self.fh * .5
        self.big = .62 * math.hypot(self.fw, self.fh)
        self.orb = EnergyCharge()
        rng = np.random.default_rng(1989)
        self.shards = [(rng.uniform(0, TAU), rng.uniform(500, 1500), rng.uniform(0, .12), rng.uniform(.35, .8),
                        rng.uniform(1.2, 3.2)) for _ in range(46)]

    # ---- timeline -------------------------------------------------------------------
    def flight(self, t: float) -> tuple[float, float, float]:
        """Where the ball is and how big (x, y, radius) at time t before the impact."""
        u = min(1.0, max(0.0, t / self.IMPACT))
        move = u ** 2.2
        return (self.mx + (self.cx - self.mx) * move, self.my + (self.cy - self.my) * move,
                self.r0 + (self.big - self.r0) * u ** 3.4)

    def whiteout(self, t: float) -> float:
        """How much of the frame is covered by the white light of the burst (0..1)."""
        flash = math.exp(-((t - self.IMPACT) / .09) ** 2)
        linger = math.exp(-(t - self.IMPACT) / .3) if t >= self.IMPACT else 0.0
        return min(.96, (.96 * flash + .7 * linger) * self.power)

    def shake(self, t: float) -> tuple[int, int]:
        if t < self.IMPACT:
            amp = 3.0 * (t / self.IMPACT) ** 2
        else:
            amp = 16.0 * self.power * math.exp(-(t - self.IMPACT) / .28)
        return round(amp * math.sin(TAU * 19 * t + .4)), round(.8 * amp * math.cos(TAU * 23 * t))

    def render(self, live: Frame, background: Frame | None, now: float) -> Frame:
        if live.shape[:2] != (self.fh, self.fw) or (self.subject is not None and live.shape != self.subject.frame.shape):
            raise ValueError('Resolução mudou durante o efeito.')
        t = float(now - self.started)
        if t <= 0 or t >= self.duration:
            return live.copy()
        dx, dy = self.shake(t)
        out = shifted(live, dx, dy)
        if t < self.IMPACT + .05:
            x, y, r = self.flight(t)
            self._glow(out, live, x + dx, y + dy, r)
            self.orb._body(out, x + dx, y + dy, r, now, 1.0, flicker(now), 0.0, 1.0)
            self._speed_lines(out, x + dx, y + dy, r, t)
        white = self.whiteout(t)
        if white > .01:
            tint = np.empty_like(out)
            tint[:] = (255, 250, 238)
            out = cv2.addWeighted(out, 1 - white, tint, white, 0)
        if t >= self.IMPACT:
            self._shock(out, t - self.IMPACT)
        return out

    def _glow(self, out: Frame, live: Frame, x: float, y: float, r: float) -> None:
        """Blue light the ball throws on the room as it gets closer."""
        rect = align((0, 0, self.fw, self.fh), (self.fw, self.fh))
        gx, gy = grids(rect)
        d2 = (np.square(gx - x) + np.square(gy - y)) * (1 / (r * r))
        light = (np.exp(-d2 * (1 / 6.0)) * (.6 * self.power))[:, :, None] * GLOW
        light += (np.exp(-d2 * (1 / 1.8)) * (.45 * self.power))[:, :, None] * ICE
        light *= tone(live, rect, d2.shape)[:, :, None]
        composite(out, rect, light, None, S)

    def _speed_lines(self, out: Frame, x: float, y: float, r: float, t: float) -> None:
        """Anime zoom lines from the borders towards the ball, stronger as it closes in."""
        k = float(smooth((t - .08) / .3)) * (1 - float(smooth((t - self.IMPACT + .08) / .1)))
        if k <= .02:
            return
        canvas = np.zeros_like(out)
        far = math.hypot(self.fw, self.fh)
        step = int(t * 30)
        rng = np.random.default_rng(step * 31 + 7)
        for _ in range(36):
            angle = rng.uniform(0, TAU)
            near = r * rng.uniform(1.15, 1.6)
            ca, sa = math.cos(angle), math.sin(angle)
            line(canvas, (x + ca * near, y + sa * near), (x + ca * far, y + sa * far),
                 scaled(PALE, k * rng.uniform(.35, .8)), int(rng.integers(1, 3)))
        paint(canvas, out, (0, 0))

    def _shock(self, out: Frame, since: float) -> None:
        """After the burst: an expanding ring of light and shards flying out of the frame."""
        canvas = np.zeros_like(out)
        far = math.hypot(self.fw, self.fh)
        c = (self.cx, self.cy)
        for delay, width, color in ((0.0, 14, DEEP), (.0, 4, PALE), (.12, 8, DEEP)):
            q = (since - delay) / .8
            if 0 < q < 1:
                radius = far * .65 * (1 - (1 - q) ** 2)
                k = (1 - q) ** 1.3 * self.power
                cv2.circle(canvas, (round(c[0] * 16), round(c[1] * 16)), round(radius * 16), scaled(color, k),
                           max(1, round(width * (1 - .5 * q))), cv2.LINE_AA, 4)
        for angle, speed, delay, life, size in self.shards:
            age = (since - delay) / life
            if not 0 < age < 1:
                continue
            d = speed * life * (1 - (1 - age) ** 2) + .1 * far
            tail = d - 60 * (1 - age)
            ca, sa = math.cos(angle), math.sin(angle)
            k = (1 - age) ** 1.2 * self.power
            line(canvas, (c[0] + ca * tail, c[1] + sa * tail), (c[0] + ca * d, c[1] + sa * d), scaled(PALE, k), 2)
            dot(canvas, (c[0] + ca * d, c[1] + sa * d), size, scaled((255, 252, 240), k))
        paint(canvas, out, (0, 0))
