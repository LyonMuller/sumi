"""Pure geometry and temporal motion recognition; no camera or audio dependencies."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from math import acos, degrees, dist, isfinite
from typing import Sequence

from .gesture import Face, Point, cross_pose, goku_pose
from .gesture_guides import guide_for

Hand = Sequence[Point]


def distance(hand: Hand, a: int, b: int) -> float:
    return dist((hand[a].x, hand[a].y), (hand[b].x, hand[b].y))


def valid_hand(hand: Hand) -> bool:
    return len(hand) == 21 and all(isfinite(v) for point in hand for v in (point.x, point.y, point.z)) and distance(hand, 0, 9) >= 12


def extended(hand: Hand, base: int) -> bool:
    length = sum(distance(hand, i, i+1) for i in range(base, base+3))
    return length > 1 and distance(hand, base, base+3)/length > .85 and distance(hand, 0, base+3) > distance(hand, 0, base+1)*1.14


def open_palm(hand: Hand) -> bool:
    return valid_hand(hand) and all(extended(hand, base) for base in (5, 9, 13, 17))


def ninja_pose(hands: Sequence[Hand], face: Face) -> bool:
    if len(hands) != 1 or not near_face(hands[0],face):
        return False
    hand=hands[0]
    palm=distance(hand,0,9)
    return (extended(hand,5) and extended(hand,9)
            and not extended(hand,13) and not extended(hand,17)
            and distance(hand,8,12)<palm*.65
            and hand[8].y<hand[5].y-palm*.18
            and hand[12].y<hand[9].y-palm*.18)


def near_face(hand:Hand,face:Face) -> bool:
    return (valid_hand(hand) and face.height>=20 and face.width>=20
            and .12<distance(hand,0,9)/face.height<1.8
            and abs(hand[0].x-(face.x+face.width/2))<face.width*2.8
            and face.y-face.height*.9<hand[9].y<face.y+face.height*2.6)


def farewell_pose(hands:Sequence[Hand],face:Face) -> bool:
    if len(hands)!=1 or not near_face(hands[0],face):
        return False
    hand=hands[0]
    visible=0
    for base in (5,9,13,17):
        length=sum(distance(hand,i,i+1) for i in range(base,base+3))
        # Natural palms have curved fingers; accept three clearly unfolded fingers.
        if length>1 and distance(hand,base,base+3)/length>.78 and distance(hand,0,base+3)>distance(hand,0,base+1)*1.04:
            visible+=1
    return visible>=3


def portal_pose(hands: Sequence[Hand], face: Face) -> bool:
    if len(hands) != 2 or not all(open_palm(hand) for hand in hands):
        return False
    left, right = sorted(hands, key=lambda hand: hand[9].x)
    center = face.x+face.width/2
    span = right[9].x-left[9].x
    return (left[9].x < center-face.width*.3 and right[9].x > center+face.width*.3
            and face.width*.9 < span < face.width*3.5
            and all(face.y-face.height*.5 < hand[9].y < face.y+face.height*1.8 for hand in hands))


PALM = (0, 5, 9, 13, 17)
WAVE_CHARGE_SECONDS = 1.2   # holding the cupped hands this long gives a full charge
WAVE_MIN_CHARGE = .35       # a push before this much charge is only a gesture, not a shot
WAVE_GRACE = .25            # the pose may flicker this long without dropping the charge
WAVE_WINDOW = .6            # the push has to start within this long after the last charged frame
WAVE_GROWTH = 1.15          # hands this much larger than while charging: pushed at the camera
WAVE_SHIFT = .5             # ... or this many face widths closer to the middle of the body


@dataclass(frozen=True)
class Ball:
    """Where two hands held together meet; x, y and size use the units of the input points."""
    x: float
    y: float
    size: float


def palm_centre(hand: Hand) -> tuple[float, float]:
    return (sum(hand[i].x for i in PALM)/len(PALM), sum(hand[i].y for i in PALM)/len(PALM))


def finger_curl(hand: Hand) -> float:
    """Mean over the four fingers of straight distance / chain length: 1 is straight, about .4 a fist."""
    ratios = []
    for base in (5, 9, 13, 17):
        length = sum(distance(hand, i, i+1) for i in range(base, base+3))
        if length <= 1:
            return 0.0
        ratios.append(distance(hand, base, base+3)/length)
    return sum(ratios)/4


def wave_ball(hands: Sequence[Hand], face: Face, slack: float = 1.0) -> Ball | None:
    """Two similar hands with palms and wrists together, as large as hands near this face."""
    if len(hands) != 2 or not all(valid_hand(hand) for hand in hands):
        return None
    if not (face.height >= 20 and face.width >= 20 and all(isfinite(v) for v in (face.x, face.y, face.width, face.height))):
        return None
    a, b = hands
    pa, pb = distance(a, 0, 9), distance(b, 0, 9)
    size = (pa+pb)/2
    if not (.55 < pa/pb < 1.8 and .15 < size/face.height < 1.4):
        return None
    ca, cb = palm_centre(a), palm_centre(b)
    if dist(ca, cb) > 1.7*size*slack or dist((a[0].x, a[0].y), (b[0].x, b[0].y)) > 1.6*size*slack:
        return None
    return Ball((ca[0]+cb[0])/2, (ca[1]+cb[1])/2, size)


def charge_pose(hands: Sequence[Hand], face: Face) -> bool:
    """Both hands cupped together beside the body, under the chin: the charge of the energy wave."""
    ball = wave_ball(hands, face)
    if ball is None:
        return False
    # Beside the torso (either side), not in front of the face or the chest: clasped hands stay harmless.
    side = abs(ball.x-(face.x+face.width/2))/face.width
    if not (.8 < side < 4.5 and face.y+face.height*.9 < ball.y < face.y+face.height*5):
        return False
    # Relaxed, curled fingers: neither flat open palms nor fists.
    if not all(.35 <= finger_curl(hand) <= .93 for hand in hands):
        return False
    # Palms face each other, so the hands point the same way.
    d0 = (hands[0][9].x-hands[0][0].x, hands[0][9].y-hands[0][0].y)
    d1 = (hands[1][9].x-hands[1][0].x, hands[1][9].y-hands[1][0].y)
    cosine = (d0[0]*d1[0]+d0[1]*d1[1])/(dist((0, 0), d0)*dist((0, 0), d1))
    return degrees(acos(max(-1.0, min(1.0, cosine)))) < 80


def push_pose(hands: Sequence[Hand], face: Face) -> bool:
    """Both hands open and together in front of the body: the release of the energy wave."""
    ball = wave_ball(hands, face, 1.15)
    if ball is None:
        return False
    if not (abs(ball.x-(face.x+face.width/2)) < face.width*3.5 and face.y+face.height*.3 < ball.y < face.y+face.height*5):
        return False
    return all(sum(extended(hand, base) for base in (5, 9, 13, 17)) >= 3 for hand in hands)


@dataclass(frozen=True)
class Recognition:
    matched: bool
    progress: float
    hint: str
    charging: bool = False       # energy wave: the ball should be on screen
    charge: float = 0.0          # energy wave: 0..1
    ball: Ball | None = None     # energy wave: where the hands meet, when there are two


class GestureRecognizer:
    """Hold poses use Engine's HoldGate; motion emits only one fresh, deliberate pulse."""
    def __init__(self) -> None:
        self.mode = ''
        self.reset()

    def reset(self) -> None:
        self.last: float | None = None
        self.neutral_since: float | None = None
        self.armed = False
        self.prepared: tuple[float, Point, float, float] | None = None
        self.charge_since: float | None = None
        self.charge_seen = 0.0
        self.level = 0.0
        self.last_ball: Ball | None = None
        self.trail: deque[tuple[float, float, float]] = deque()

    def _neutral(self, now: float) -> None:
        self.prepared = None
        if self.neutral_since is None:
            self.neutral_since = now
        if now-self.neutral_since >= .35:
            self.armed = True

    def _pulse(self) -> Recognition:
        self.armed = False
        self.neutral_since = None
        self.prepared = None
        return Recognition(True, 1.0, 'Gesto reconhecido. Solte a mão antes de repetir.')

    def _wave(self, hands: Sequence[Hand], face: Face, now: float, instruction: str) -> Recognition:
        """Charge with cupped hands at the side, then push them open: the pulse is the shot."""
        charged, pushed = charge_pose(hands, face), push_pose(hands, face)
        ball = wave_ball(hands, face, 1.15)
        if not self.armed:
            # At start-up and after a shot the pose has to be released before it counts again.
            if charged or pushed:
                self.neutral_since = None
            else:
                self._neutral(now)
            return Recognition(False, 0, 'Baixe as mãos antes de carregar de novo.' if hands else instruction)
        centre = face.x+face.width/2
        if self.charge_since is not None and pushed and self.level >= WAVE_MIN_CHARGE and now-self.charge_seen <= WAVE_WINDOW and ball is not None:
            sizes = sorted(size for _, size, _ in self.trail)
            offsets = sorted(offset for _, _, offset in self.trail)
            if sizes and (ball.size/sizes[len(sizes)//2] >= WAVE_GROWTH
                          or offsets[len(offsets)//2]-abs(ball.x-centre) >= WAVE_SHIFT*face.width):
                level = self.level
                self._pulse()
                self.charge_since, self.level = None, 0.0
                self.trail.clear()
                return Recognition(True, 1.0, 'Onda disparada! Baixe as mãos antes de repetir.', False, level, ball)
        if charged and ball is not None:
            if self.charge_since is None:
                self.charge_since = now
                self.trail.clear()
            self.charge_seen = now
            self.last_ball = ball
            self.level = min(1.0, (now-self.charge_since)/WAVE_CHARGE_SECONDS)
            self.trail.append((now, ball.size, abs(ball.x-centre)))
            while self.trail and now-self.trail[0][0] > .7:
                self.trail.popleft()
            return Recognition(False, self.level, 'Carga completa! Empurre as mãos abertas para a frente.' if self.level >= 1
                               else 'Carregando… mantenha as mãos juntas.', True, self.level, ball)
        if self.charge_since is not None:
            gap = now-self.charge_seen
            if gap <= WAVE_WINDOW:
                # Between the pose and the push: the ball lingers while the hands open.
                return Recognition(False, self.level, 'Agora empurre as mãos para a frente.',
                                   gap <= WAVE_GRACE or pushed, self.level, ball or self.last_ball)
            self.charge_since, self.level = None, 0.0
            self.trail.clear()
        return Recognition(False, 0, instruction)

    def update(self, hands: Sequence[Hand], face: Face | None, now: float, effect: str) -> Recognition:
        guide = guide_for(effect)
        if effect != self.mode:
            self.reset()
            self.mode = effect
        if not isfinite(now):
            self.reset()
            return Recognition(False, 0, 'Aguardando uma observação válida.')
        if self.last is not None and (now <= self.last or now-self.last > .3):
            self.reset()
        self.last = now
        if face is None or not all(isfinite(v) for v in (face.x, face.y, face.width, face.height)) or min(face.width, face.height) < 20:
            self.reset()
            return Recognition(False, 0, 'Mostre somente seu rosto e mantenha a câmera estável.')
        if guide.kind == 'manual':
            return Recognition(False, 0, guide.instruction)
        if guide.kind == 'wave':
            return self._wave(hands, face, now, guide.instruction)
        if not guide.motion:
            matched = (len(hands) == 1 and goku_pose(hands[0], face) if guide.kind == 'forehead' else
                       ninja_pose(hands, face) if guide.kind == 'ninja' else
                       farewell_pose(hands, face) if guide.kind == 'palm' else
                       cross_pose(hands, face) if guide.kind == 'cross' else portal_pose(hands, face))
            return Recognition(matched, 0, 'Mantenha a posição…' if matched else guide.instruction)
        if len(hands) != 1 or not valid_hand(hands[0]):
            if not hands:
                self._neutral(now)
            else:
                self.reset()
            return Recognition(False, 0, 'Mostre uma mão inteira, bem iluminada.')
        hand = hands[0]
        palm = distance(hand, 0, 9)
        # Motions must stay near this one face, not be a tiny/background hand.
        if not .15 < palm/face.height < 1.3 or abs(hand[0].x-(face.x+face.width/2)) > face.width*2.5:
            self.reset()
            return Recognition(False, 0, 'Aproxime a mão do rosto, sem cobri-lo.')
        tip = 12 if guide.kind == 'snap' else 8
        touching = distance(hand, 4, tip)/palm < .25
        if not self.armed:
            if not touching:
                self._neutral(now)
            else:
                self.neutral_since = None
            return Recognition(False, 0, 'Solte os dedos antes de preparar o próximo gesto.')
        if touching:
            self.neutral_since = None
            if self.prepared is None:
                self.prepared = (now, hand[0], distance(hand, 0, tip)/palm, palm)
            elapsed = now-self.prepared[0]
            if elapsed > 1:
                self.armed = False
                self.prepared = None
                return Recognition(False, 0, 'Preparação longa demais. Solte e tente novamente.')
            return Recognition(False, min(.8, elapsed/.12*.8), 'Agora estale os dedos.' if tip == 12 else 'Agora abra a pinça.')
        if self.prepared is not None:
            began, wrist, reach, old_palm = self.prepared
            elapsed = now-began
            stable = dist((wrist.x, wrist.y), (hand[0].x, hand[0].y)) < old_palm*.65 and .7 < palm/old_palm < 1.4
            separated = distance(hand, 4, tip)/palm > (.4 if tip == 12 else .6)
            # A snap's middle finger must fall toward the palm; opening a pinch is insufficient.
            folded = reach-distance(hand, 0, tip)/palm > .12
            if .07 <= elapsed <= (.8 if tip == 12 else .9) and stable and separated and (folded or tip == 8):
                return self._pulse()
            if elapsed > .9 or not stable:
                self.prepared = None
            else:
                return Recognition(False, .8, 'Complete o movimento mantendo a mão visível.')
        self._neutral(now)
        return Recognition(False, 0, guide.instruction)
