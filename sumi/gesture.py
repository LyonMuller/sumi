from __future__ import annotations
from dataclasses import dataclass
import math
from math import dist, isfinite
from typing import Sequence

@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float = 0.0

@dataclass(frozen=True)
class Face:
    x: float
    y: float
    width: float
    height: float


def goku_pose(hand: Sequence[Point], face: Face | None) -> bool:
    """Pixel coordinates; geometry stays independent of MediaPipe and video APIs."""
    if len(hand) != 21 or face is None:
        return False
    if not all(isfinite(v) for p in hand for v in (p.x, p.y, p.z)):
        return False
    if not all(isfinite(v) for v in (face.x, face.y, face.width, face.height)):
        return False
    if min(face.width, face.height) < 20:
        return False
    def distance(a: int, b: int) -> float:
        return dist((hand[a].x, hand[a].y), (hand[b].x, hand[b].y))
    palm = distance(0, 9)
    if palm < 12 or not 0.15 < palm / face.height < 1.3:
        return False
    def extended(base: int) -> bool:
        length = sum(distance(i, i + 1) for i in range(base, base + 3))
        return (length > 1 and distance(base, base + 3) / length > 0.88
                and distance(0, base + 3) > distance(0, base + 1) * 1.18)
    if not extended(5) or not extended(9) or extended(13) or extended(17):
        return False
    if not 0.03 * palm < distance(8, 12) < 0.48 * palm:
        return False
    for tip in (8, 12):
        p = hand[tip]
        if not (face.x + face.width * 0.08 <= p.x <= face.x + face.width * 0.92
                and face.y - face.height * 0.18 <= p.y <= face.y + face.height * 0.28):
            return False
    return True


def _finger_up(hand: Sequence[Point], base: int) -> bool:
    """Finger chain base..base+3 is straight and reaches away from the wrist."""
    def d(a: int, b: int) -> float:
        return dist((hand[a].x, hand[a].y), (hand[b].x, hand[b].y))
    length = sum(d(i, i + 1) for i in range(base, base + 3))
    return length > 1 and d(base, base + 3) / length > .85 and d(0, base + 3) > d(0, base + 1) * 1.14


def _cross_ready(hand: Sequence[Point]) -> tuple[tuple[float, float], tuple[float, float], float] | None:
    """Index and middle together and straight, ring and pinky curled: (base, tip, palm size)."""
    if len(hand) != 21 or not all(isfinite(v) for p in hand for v in (p.x, p.y, p.z)):
        return None
    palm = dist((hand[0].x, hand[0].y), (hand[9].x, hand[9].y))
    if palm < 12 or not (_finger_up(hand, 5) and _finger_up(hand, 9)
                         and not _finger_up(hand, 13) and not _finger_up(hand, 17)):
        return None
    if dist((hand[8].x, hand[8].y), (hand[12].x, hand[12].y)) > palm * .65:
        return None
    base = ((hand[5].x + hand[9].x) / 2, (hand[5].y + hand[9].y) / 2)
    tip = ((hand[8].x + hand[12].x) / 2, (hand[8].y + hand[12].y) / 2)
    return base, tip, palm


def _segments_cross(a0, a1, b0, b1) -> bool:
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a0, a1, b0) * side(a0, a1, b1) < 0 and side(b0, b1, a0) * side(b0, b1, a1) < 0


def cross_pose(hands: Sequence[Sequence[Point]], face: Face | None) -> bool:
    """Both hands show the two-finger seal and the fingers cross like a plus sign, below the face."""
    if len(hands) != 2 or face is None:
        return False
    if not all(isfinite(v) for v in (face.x, face.y, face.width, face.height)) or min(face.width, face.height) < 20:
        return False
    seals = [_cross_ready(hand) for hand in hands]
    if None in seals:
        return False
    (b0, t0, p0), (b1, t1, p1) = seals
    if not (.12 < p0 / face.height < 1.6 and .12 < p1 / face.height < 1.6 and .5 < p0 / p1 < 2):
        return False
    # Perpendicular-ish: the angle between finger directions stays in 50..130 degrees.
    d0, d1 = (t0[0] - b0[0], t0[1] - b0[1]), (t1[0] - b1[0], t1[1] - b1[1])
    n0, n1 = math.hypot(*d0), math.hypot(*d1)
    if n0 < 1 or n1 < 1:
        return False
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (d0[0] * d1[0] + d0[1] * d1[1]) / (n0 * n1)))))
    if not 50 <= angle <= 130:
        return False
    # The two finger segments must actually intersect (a little slack at the tips).
    def stretch(base, tip):
        return base, (tip[0] + (tip[0] - base[0]) * .15, tip[1] + (tip[1] - base[1]) * .15)
    if not _segments_cross(*stretch(b0, t0), *stretch(b1, t1)):
        return False
    # In front of the chest: hands under the face, centred on it, fingertips off the face.
    for hand, tip in zip(hands, (t0, t1)):
        if not (face.y + face.height * .75 < hand[9].y < face.y + face.height * 3.6
                and abs(hand[9].x - (face.x + face.width / 2)) < face.width * 1.6):
            return False
        for index in (8, 12):
            p = hand[index]
            if (face.x - face.width * .1 < p.x < face.x + face.width * 1.1
                    and face.y - face.height * .1 < p.y < face.y + face.height * 1.05):
                return False
    return True


class HoldGate:
    """Require release, then continuous fresh observations before one trigger."""
    def __init__(self, hold_seconds: float = 1.0) -> None:
        if not 0.6 <= hold_seconds <= 3.0:
            raise ValueError('Tempo do gesto deve ficar entre 0,6 e 3 segundos.')
        self.hold_seconds = hold_seconds
        self.reset()

    def reset(self) -> None:
        self.armed = False
        self.started: float | None = None
        self.released: float | None = None
        self.last: float | None = None
        self.progress = 0.0

    def update(self, matched: bool, now: float) -> bool:
        if not isfinite(now):
            self.reset()
            return False
        if self.last is not None and (now <= self.last or now - self.last > 0.3):
            self.reset()
        self.last = now
        if not matched:
            self.started = None
            self.progress = 0.0
            if self.released is None:
                self.released = now
            if now - self.released >= 0.35:
                self.armed = True
            return False
        self.released = None
        if not self.armed:
            return False
        if self.started is None:
            self.started = now
        self.progress = min(1.0, (now - self.started) / self.hold_seconds)
        if self.progress < 1.0:
            return False
        self.reset()
        return True
