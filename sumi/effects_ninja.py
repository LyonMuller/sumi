"""Ninja-style exits: a kawarimi (smoke and a wooden log) and shadow clones in smoke.

Both effects keep the person at full resolution, composite only inside bounded regions
and are driven purely by elapsed time, so the first and last frames are bit-exact.
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np

from .effects import Silhouette, TeleportEffect, smooth
from .paths import resource_root
from .scene import Frame
from .smoke import SmokePuff, tiles

Rect = tuple[int, int, int, int]


@lru_cache(maxsize=1)
def log_sprite() -> np.ndarray:
    """Log cropped to its opaque pixels, premultiplied float32 BGRA (alpha 0..255)."""
    image = cv2.imread(str(resource_root() / 'assets' / 'effects' / 'tronco.png'), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise ValueError('Imagem do tronco ausente ou sem transparência.')
    x, y, w, h = cv2.boundingRect((image[:, :, 3] > 8).astype(np.uint8))
    sprite = image[y:y + h, x:x + w].astype(np.float32)
    sprite[:, :, :3] *= sprite[:, :, 3:4] / 255
    return sprite


try:  # Pay the one-off decode and noise-tile costs at import, not at effect start.
    log_sprite()
    tiles()
except Exception:  # pragma: no cover - surfaced when an effect is created
    pass


def union(rects: list[Rect]) -> Rect:
    return (min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects))


def over(frame: Frame, patch: Frame, alpha8: np.ndarray, x: int, y: int) -> None:
    """Alpha-blend a uint8 patch with a uint8 alpha onto frame at (x, y), clipped."""
    fh, fw = frame.shape[:2]
    ph, pw = patch.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(fw, x + pw), min(fh, y + ph)
    if x1 <= x0 or y1 <= y0:
        return
    sub = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
    a = alpha8[sub]
    inv = 255 - a
    roi = frame[y0:y1, x0:x1]
    frame[y0:y1, x0:x1] = cv2.add(cv2.multiply(roi, cv2.merge((inv, inv, inv)), scale=1 / 255),
                                  cv2.multiply(patch[sub], cv2.merge((a, a, a)), scale=1 / 255))


class NinjaEffect(TeleportEffect):
    """Shared plumbing: endpoints, region bookkeeping and body-shaped smoke."""

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        self.fh, self.fw = subject.frame.shape[:2]
        self.alpha8 = np.clip(self.alpha * 255 + .5, 0, 255).astype(np.uint8)
        rows = np.flatnonzero(self.alpha.max(axis=1) > .4)
        left, top, right, bottom = self.box
        self.top_row, self.bottom_row = int(rows[0]), int(rows[-1])
        self.body_w = max(1, right - left)
        self.body_h = max(1, self.bottom_row - self.top_row)

    def finish_setup(self, rects: list[Rect]) -> None:
        """Declare every pixel the effect may touch (tests and callers can rely on it)."""
        self.region = union([self.box, *rects])

    def body_puff(self, mask: np.ndarray, origin: tuple[int, int], width: int, delay: float,
                  life: float, seed: int, reach: float = .26) -> SmokePuff:
        """A cloud that starts as a shrunken copy of the body, so nothing pokes out of it."""
        small = cv2.resize(mask, (max(2, mask.shape[1] // 4), max(2, mask.shape[0] // 4)), interpolation=cv2.INTER_AREA)
        size = max(1, int(width * .035 / 4)) * 2 + 1
        small = cv2.erode((small > .4).astype(np.uint8), np.ones((size, size), np.uint8)).astype(np.float32)
        return SmokePuff((self.fh, self.fw), small, origin, reach * width, seed=seed, delay=delay, life=life,
                         size=(mask.shape[1], mask.shape[0]))

    def endpoint(self, live: Frame, background: Frame, now: float) -> tuple[float, Frame | None]:
        if live.shape != background.shape or live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')
        t = float(now - self.started)
        if t >= self.duration:
            return t, background.copy() if self.hidden_target else live.copy()
        if t <= 0:
            return t, live.copy() if self.hidden_target else background.copy()
        return t, None

    def render(self, live: Frame, background: Frame, now: float) -> Frame:
        t, done = self.endpoint(live, background, now)
        if done is not None:
            return done
        frame = background.copy()
        self.compose(frame, t)
        return frame

    def compose(self, frame: Frame, t: float) -> None:
        raise NotImplementedError

    def draw_person(self, frame: Frame, fade: float = 1.0, dy: int = 0) -> None:
        if fade <= 0:
            return
        alpha = self.alpha8 if fade >= 1 else cv2.convertScaleAbs(self.alpha8, alpha=fade)
        over(frame, self.person, alpha, self.box[0], self.box[1] + dy)


class KawarimiEffect(NinjaEffect):
    """Poof, a log stands where you were, then tips over and falls out of the frame."""
    duration = 1.3
    exit_duration, return_duration = 1.3, 1.15
    drop_start = .62     # exit: the log lets go
    drop_time = .26      # return: the log lands
    swap_at = .36        # return: poof that swaps the log for the person
    tilt = -3.0

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        self.duration = self.exit_duration if hidden_target else self.return_duration
        left, top, right, bottom = self.box
        columns = self.alpha[int(self.top_row + self.body_h * .35):int(self.top_row + self.body_h * .8) + 1]
        weights = columns.sum(axis=0)
        xs = np.arange(self.alpha.shape[1], dtype=np.float32)
        self.cx = left + float((weights * xs).sum() / max(weights.sum(), 1e-3))
        self.cy = top + self.top_row + .55 * self.body_h
        sprite = log_sprite()
        height = max(24, round(self.body_h * .6))
        width = max(12, round(height * sprite.shape[1] / sprite.shape[0]))
        self.sprite = np.clip(cv2.resize(sprite, (width, height), interpolation=cv2.INTER_AREA) + .5, 0, 255).astype(np.uint8)
        self.diag = int(math.hypot(width, height)) + 4
        torso = max(self.body_w * .5, width)
        delay = 0.0 if hidden_target else self.swap_at
        life = .75 if hidden_target else .72
        mask = self.alpha.copy()
        cv2.circle(mask, (round(self.cx - left), round(self.cy - top)), round(torso * .3), 1.0, -1)
        self.puffs = [self.body_puff(mask, (left, top), self.body_w, delay, life, 5, .2)]
        # Fall: gravity so that the log leaves the bottom of the frame just before the end.
        travel = self.fh + height * .8 - self.cy
        fall = max(.2, self.duration - self.drop_start - .08)
        self.gravity = 2 * travel / fall ** 2
        # Return: the log arrives from above.
        self.arrival = self.cy + height * .8
        half = self.diag // 2 + 2
        rects: list[Rect] = [(max(0, int(self.cx) - half), 0, min(self.fw, int(self.cx) + half), self.fh)]
        self.finish_setup(rects + [p.rect for p in self.puffs])

    def draw_log(self, frame: Frame, dx: float, dy: float, angle: float) -> None:
        h, w = self.sprite.shape[:2]
        d = self.diag
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        matrix[:, 2] += (d / 2 - w / 2, d / 2 - h / 2)
        warped = cv2.warpAffine(self.sprite, matrix, (d, d), flags=cv2.INTER_LINEAR)
        x, y = round(self.cx + dx - d / 2), round(self.cy + dy - d / 2)
        fh, fw = frame.shape[:2]
        x0, y0, x1, y1 = max(0, x), max(0, y), min(fw, x + d), min(fh, y + d)
        if x1 <= x0 or y1 <= y0:
            return
        part = np.ascontiguousarray(warped[y0 - y:y1 - y, x0 - x:x1 - x])
        inv = 255 - cv2.extractChannel(part, 3)
        frame[y0:y1, x0:x1] = cv2.add(cv2.multiply(frame[y0:y1, x0:x1], cv2.merge((inv, inv, inv)), scale=1 / 255),
                                      cv2.cvtColor(part, cv2.COLOR_BGRA2BGR))

    def compose(self, frame: Frame, t: float) -> None:
        if self.hidden_target:
            self.draw_person(frame, 1 - smooth((t - .02) / .07))
            if t > .07:
                s = max(0.0, t - self.drop_start)
                self.draw_log(frame, 80 * s * s, .5 * self.gravity * s * s, self.tilt - 220 * s * s)
        else:
            if t < self.swap_at + .07:
                k = min(1.0, t / self.drop_time)
                fall = (1 - k * k)
                bounce = 5 * math.sin(math.pi * min(1.0, max(0.0, (t - self.drop_time) / .1))) * (t > self.drop_time)
                self.draw_log(frame, 0, -fall * self.arrival - bounce, self.tilt + 24 * fall * fall)
            else:
                s = t - self.swap_at - .07
                self.draw_person(frame, 1.0, -round(10 * max(0.0, 1 - s / .35) ** 2))
        for puff in self.puffs:
            puff.render_at(frame, t)


# Depth rows: size, extra lift, brightness and colour kept for clones further back.
ROWS = ((1.0, 0.0, .94, 0.0), (.74, .05, .85, .14), (.58, .10, .76, .28))
WAVES = (2, 2, 4)          # clones added per wave: 2, then 4, then 8 in total
MAX_LEVEL = len(WAVES)


@dataclass
class Cutout:
    """The person cut out of one silhouette, cheap enough to make several times a second."""
    t: float
    box: Rect
    person: Frame
    alpha: np.ndarray
    low: np.ndarray                      # whole-frame mask at 1/4 resolution
    shoulder: int                        # frame row where the shoulders start
    scaled_cache: dict = field(default_factory=dict)

    def scaled(self, scale: float, row: int = 0) -> tuple[Frame, np.ndarray]:
        key = (round(scale, 3), row)
        if key not in self.scaled_cache:
            h, w = self.alpha.shape
            size = (max(8, round(w * scale)), max(8, round(h * scale)))
            source, mask = self.person, self.alpha
            if scale <= .5:                      # small clones start from a half-size copy, which is cheaper
                if 'half' not in self.scaled_cache:
                    self.scaled_cache['half'] = (cv2.resize(self.person, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA),
                                                 cv2.resize(self.alpha, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA))
                source, mask = self.scaled_cache['half']
            person = cv2.resize(source, size, interpolation=cv2.INTER_AREA)
            _, _, brightness, grey = ROWS[row]
            if grey:
                mono = cv2.cvtColor(cv2.cvtColor(person, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                person = cv2.addWeighted(person, 1 - grey, mono, grey, 0)
            person = cv2.convertScaleAbs(person, alpha=brightness)
            alpha = cv2.resize(mask, size, interpolation=cv2.INTER_AREA)
            self.scaled_cache[key] = (person, np.clip(alpha * 255 + .5, 0, 255).astype(np.uint8))
        return self.scaled_cache[key]


def cut_person(subject: Silhouette) -> Cutout | None:
    mask = np.clip(subject.mask, 0, 1)
    h, w = mask.shape
    low = cv2.resize(mask, (max(2, w // 4), max(2, h // 4)), interpolation=cv2.INTER_AREA)
    x, y, bw, bh = cv2.boundingRect((low > .4).astype(np.uint8))
    if bw * bh < 25:
        return None
    pad = max(8, round(bw * 4 * .04))
    box = (max(0, x * 4 - pad), max(0, y * 4 - pad), min(w, (x + bw) * 4 + pad), min(h, (y + bh) * 4 + pad))
    left, top, right, bottom = box
    widths = (low[y:y + bh] > .4).sum(axis=1)
    wide = np.flatnonzero(widths >= .75 * widths.max())
    shoulder = (y + int(wide[0])) * 4 if wide.size else top + (bottom - top) // 3
    alpha = cv2.GaussianBlur(mask[top:bottom, left:right], (0, 0), 1.0)
    return Cutout(subject.captured_at, box, subject.frame[top:bottom, left:right].copy(), alpha, low, shoulder)


class ShadowCloneEffect(NinjaEffect):
    """Persistent shadow clones that stay behind the live person until dismissed.

    `hidden_target=True` is the transition that turns the first wave ON (poofs, then the clones
    stay); `False` dismisses every clone (poofs, then the plain live frame). Between the two,
    `render_steady` draws them from the freshest silhouettes, each lagging a little, and
    `summon` adds further waves (2, 4, 8 clones) in rows further back. The person is never
    hidden; clones are only ever drawn behind the live image.
    """
    persistent = True
    on_duration, off_duration = .8, .65
    duration = .8
    history_size = 8
    arrival = .8         # seconds for one wave to finish arriving

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float,
                 carry: 'ShadowCloneEffect | None' = None) -> None:
        # Not NinjaEffect.__init__: the heavy whole-person preparation is not needed here.
        if subject.mask.shape != subject.frame.shape[:2] or not np.isfinite(subject.mask).all():
            raise ValueError('Recorte de pessoa inválido.')
        self.subject, self.hidden_target, self.started = subject, hidden_target, started
        self.duration = self.on_duration if hidden_target else self.off_duration
        self.fh, self.fw = subject.frame.shape[:2]
        cut = cut_person(subject)
        if cut is None:
            raise ValueError('Não encontrei uma silhueta. Entre no enquadramento.')
        self.last: float | None = None
        self.bg_key: object = None
        self.bg_small: np.ndarray | None = None
        if carry is not None:
            self.history, self.specs, self.last_subject, self.level = (
                carry.history, carry.specs, carry.last_subject, carry.level)
            self.feed(subject)
        else:
            self.history: deque[Cutout] = deque([cut], maxlen=self.history_size)
            self.last_subject = subject
            self.specs = self.plan(cut.box)
            self.level = 1
        for spec in self.specs:
            spec['puff'] = None
        self.arrivals: list[float] = []
        placed = self.layout(started)
        if hidden_target:
            self.spawn(1, placed, started)
            smoke = [spec['puff'] for spec in self.specs if spec['puff']]
        else:                      # one cloud per depth row keeps eight poofs cheap
            smoke = [self.group_puff(group, 0.0, .5, row) for row in range(len(ROWS))
                     if (group := [item for item in placed if item[0]['row'] == row])]
        self.puffs = smoke
        margin = [(max(0, x - 40), max(0, y - 40), min(self.fw, x + p.shape[1] + 40), self.fh)
                  for _, p, _, x, y in placed]
        self.region = union([puff.rect for puff in smoke] + margin)

    @property
    def count(self) -> int:
        return sum(WAVES[:self.level])

    def group_puff(self, group: list, delay: float, life: float, seed: int) -> SmokePuff:
        """One cloud shaped by several clones at once (their alphas merged on a shared canvas)."""
        x0, y0 = max(0, min(x for _, _, _, x, _ in group)), max(0, min(y for _, _, _, _, y in group))
        x1 = min(self.fw, max(x + a.shape[1] for _, _, a, x, _ in group))
        y1 = min(self.fh, max(y + a.shape[0] for _, _, a, _, y in group))
        canvas = np.zeros((y1 - y0, x1 - x0), np.float32)
        for _, _, alpha8, x, y in group:
            ax0, ay0 = max(x, x0), max(y, y0)
            ax1, ay1 = min(x + alpha8.shape[1], x1), min(y + alpha8.shape[0], y1)
            if ax1 > ax0 and ay1 > ay0:
                part = alpha8[ay0 - y:ay1 - y, ax0 - x:ax1 - x].astype(np.float32) / 255
                np.maximum(canvas[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0], part, out=canvas[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0])
        width = int(np.mean([a.shape[1] for _, _, a, _, _ in group]))
        return self.body_puff(canvas, (x0, y0), width, delay, life, 20 + seed, .24)

    def spawn(self, level: int, placed: list, now: float) -> None:
        """Start the poofs and the pop-in of every clone of one wave (one cloud per side)."""
        for side in (-1, 1):
            group = [item for item in placed if item[0]['level'] == level and (item[0]['off'] > 0) == (side > 0)]
            for item in group:
                item[0]['born'], item[0]['puff'] = now, None
            if group:
                first = min(group, key=lambda item: item[0]['index'])[0]
                first['puff'] = self.group_puff(group, .07 * first['index'], .65, level * 2 + side)
        self.arrivals.append(now)

    def summon(self, subject: Silhouette | None, now: float) -> int:
        """Add the next wave; returns the new clone count, or 0 when already at the maximum."""
        if self.level >= MAX_LEVEL:
            return 0
        if subject is not None:
            self.feed(subject)
        self.level += 1
        self.spawn(self.level, self.layout(now), now)
        return self.count

    def plan(self, box: Rect) -> list[dict]:
        """All three waves, as offsets from the person's centre; farthest rows are drawn first."""
        left, _, right, _ = box
        cx0, w = (left + right) / 2, max(1, right - left)
        base = .86
        for factor in (.86, .76, .66, .56, .48, .42):       # row 0 shrinks to fit beside the person
            base = factor
            if .5 * factor * w <= min(self.fw - 6 - (cx0 + w / 2), cx0 - w / 2 - 6):
                break
        specs: list[dict] = []
        rows = {1: [(-1, .5 * base * w + w / 2), (1, .5 * base * w + w / 2)],
                2: [(-1, .78 * w), (1, .78 * w)],
                3: [(-1, .30 * w), (1, .30 * w), (-1, 1.12 * w), (1, 1.12 * w)]}
        for level, items in rows.items():
            row = 0 if level == 1 else 1 if level == 2 else 2
            for index, (side, reach) in enumerate(items):
                scale = (base if row == 0 else max(base, .6)) * ROWS[row][0] * (1.0 if level < 3 or index < 2 else .9)
                if level == 1:
                    offset = side * (w / 2 + .5 * base * w) - 0   # outer edge half a clone beyond the person
                else:
                    offset = side * reach
                specs.append(dict(scale=scale, off=offset, row=row, level=level, index=index, lag=.10 + .035 * len(specs),
                                  phase=len(specs) * 1.7, born=-1e9))
        specs.sort(key=lambda spec: (-spec['row'], -spec['index']))
        return specs

    def feed(self, subject: Silhouette) -> None:
        """Remember a newer silhouette; stale or foreign ones are ignored."""
        if (subject.frame.shape[:2] != (self.fh, self.fw) or subject.mask.shape != (self.fh, self.fw)
                or subject.captured_at <= self.history[-1].t or not np.isfinite(subject.mask).all()):
            return
        cut = cut_person(subject)
        if cut is not None:
            self.history.append(cut)
            self.last_subject = subject

    def pick(self, when: float) -> Cutout:
        for item in reversed(self.history):
            if item.t <= when:
                return item
        return self.history[0]

    def layout(self, now: float) -> list[tuple[dict, Frame, np.ndarray, int, int]]:
        """Where every clone of the current waves is drawn now: lagging, following the person,
        inside the frame, back rows lifted so they peek out above and beside the person."""
        dt = 0.0 if self.last is None else min(.2, max(0.0, now - self.last))
        follow = 1 - math.exp(-dt * 12)
        placed = []
        for spec in self.specs:
            if spec['level'] > self.level:
                continue
            item = self.pick(now - spec['lag'])
            person, alpha8 = item.scaled(spec['scale'], spec['row'])
            h, w = alpha8.shape
            left, top, right, bottom = item.box
            tx = min(max((left + right) / 2 + spec['off'], w / 2 + 2), self.fw - w / 2 - 2)
            ty = bottom - ROWS[spec['row']][1] * (bottom - top)
            hidden = min(tx + w / 2, right - .08 * (right - left)) - max(tx - w / 2, left + .08 * (right - left))
            if spec['row'] and hidden > .5 * w:          # mostly behind the person: show the head above the shoulders
                ty = min(ty, item.shoulder + .4 * h)
            if 'sx' not in spec:
                spec['sx'], spec['sy'] = tx, ty
            spec['sx'] += (tx - spec['sx']) * follow
            spec['sy'] += (ty - spec['sy']) * follow
            sway = round(2.4 * math.sin(2 * math.pi * .9 * now + spec['phase']))
            placed.append((spec, person, alpha8, round(spec['sx'] - w / 2), round(spec['sy'] - h) + sway))
        return placed

    def person_alpha(self, live: Frame, background: Frame | None) -> np.ndarray:
        """Where the live person stands right now (stale mask, dilated, plus a background difference)."""
        low = self.history[-1].low
        near = cv2.GaussianBlur(cv2.dilate(low, np.ones((5, 5), np.uint8)), (0, 0), 1.2)
        if background is not None and background.shape == live.shape:
            lh, lw = low.shape
            small = cv2.resize(live, (lw, lh), interpolation=cv2.INTER_AREA)
            if self.bg_key is not background:
                self.bg_key = background
                self.bg_small = cv2.resize(background, (lw, lh), interpolation=cv2.INTER_AREA)
            diff = cv2.absdiff(small, self.bg_small).max(axis=2).astype(np.float32)
            # Only trusted next to the person, so a drifting background cannot erase the clones.
            reach = cv2.dilate(low, np.ones((17, 17), np.uint8))
            near = np.maximum(near, np.clip((diff - 18) / 28, 0, 1) * (reach > .3))
        return cv2.resize(np.clip(near * 255 + .5, 0, 255).astype(np.uint8), (self.fw, self.fh),
                          interpolation=cv2.INTER_LINEAR)

    def draw(self, live: Frame, background: Frame | None, now: float, t: float, mode: str) -> Frame:
        """mode 'steady' keeps every clone; 'off' poofs them away (t is the time since it began)."""
        frame = live.copy()
        placed = self.layout(now)
        self.last = now
        presence = self.person_alpha(live, background)
        fade = 1 - smooth((t - .02) / .07) if mode == 'off' else 1.0
        for spec, person, alpha8, x, y in placed:
            if fade <= 0 or now < spec['born'] + .07 + .07 * spec['index']:
                continue
            h, w = alpha8.shape
            x0, y0, x1, y1 = max(0, x), max(0, y), min(self.fw, x + w), min(self.fh, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            sub = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
            alpha = alpha8[sub] if fade >= 1 else cv2.convertScaleAbs(alpha8[sub], alpha=fade)
            alpha = cv2.multiply(alpha, 255 - presence[y0:y1, x0:x1], scale=1 / 255)
            over(frame, np.ascontiguousarray(person[sub]), alpha, x0, y0)
        if mode == 'off':
            for puff in self.puffs:
                puff.render_at(frame, t)
        else:
            for spec in self.specs:
                puff = spec['puff']
                if puff is not None:
                    if now - spec['born'] >= puff.life + puff.delay:
                        spec['puff'] = None
                    else:
                        puff.render_at(frame, now - spec['born'])
        return frame

    def arriving(self, now: float) -> bool:
        return any(now - born < self.arrival for born in self.arrivals)

    def render_steady(self, live: Frame, background: Frame | None, now: float) -> Frame:
        if live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')
        return self.draw(live, background, now, 99.0, 'steady')

    def render(self, live: Frame, background: Frame, now: float) -> Frame:
        if live.shape != background.shape or live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')
        t = float(now - self.started)
        if self.hidden_target:                       # first wave arrives
            return live.copy() if t <= 0 else self.draw(live, background, now, t, 'steady')
        if t >= self.duration:                       # clones dismissed: the plain live frame
            return live.copy()
        return self.draw(live, background, now, t, 'steady' if t <= 0 else 'off')
