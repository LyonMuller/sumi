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
WAVE_MIN_CHARGE = .35       # opening before this much charge is only a gesture, not a shot
WAVE_FULL_CHARGE = .85      # tracking lost after this much charge (and growing hands) still fires
WAVE_GRACE = .5             # the pose may flicker this long without dropping the ball
WAVE_WINDOW = 1.0           # the release has to come within this long after the last charged frame
WAVE_GROWTH = 1.12          # hands this much larger than a moment ago: pushed at the camera
WAVE_OPEN_MARGIN = .06      # opening = finger curl this far above the curl while charging ...
WAVE_OPEN_CURL = .96        # ... but never needing more than this
WAVE_MAX_GAP = .5           # a frame gap longer than this resets the recognizer


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


def _face_ok(face: Face) -> bool:
    return face.height >= 20 and face.width >= 20 and all(isfinite(v) for v in (face.x, face.y, face.width, face.height))


def wave_ball(hands: Sequence[Hand], face: Face, slack: float = 1.0) -> Ball | None:
    """Two similar hands with palms and wrists together, as large as hands near this face."""
    if len(hands) != 2 or not all(valid_hand(hand) for hand in hands) or not _face_ok(face):
        return None
    a, b = hands
    pa, pb = distance(a, 0, 9), distance(b, 0, 9)
    size = (pa+pb)/2
    if not (.45 < pa/pb < 2.2 and .12 < size/face.height < 1.6):
        return None
    ca, cb = palm_centre(a), palm_centre(b)
    if dist(ca, cb) > 2.1*size*slack or dist((a[0].x, a[0].y), (b[0].x, b[0].y)) > 2.0*size*slack:
        return None
    return Ball((ca[0]+cb[0])/2, (ca[1]+cb[1])/2, size)


def hand_ball(hand: Hand) -> Ball:
    """The ball when only one of the two hands is tracked: at the palm of that hand."""
    centre = palm_centre(hand)
    return Ball(centre[0], centre[1], distance(hand, 0, 9))


def charge_hand(hand: Hand, face: Face) -> bool:
    """One hand that could be holding the charge: below the mouth, hand-sized, relaxed (neither flat nor a fist)."""
    if not valid_hand(hand) or not _face_ok(face):
        return False
    x, y = palm_centre(hand)
    if not (.12 < distance(hand, 0, 9)/face.height < 1.6 and y > face.y+face.height*.6 and y < face.y+face.height*8
            and abs(x-(face.x+face.width/2)) < face.width*6):
        return False
    return .3 <= finger_curl(hand) <= .97


def charge_pose(hands: Sequence[Hand], face: Face) -> bool:
    """Both hands cupped together anywhere below the mouth, beside or in front of the chest: the energy wave charge."""
    ball = wave_ball(hands, face)
    if ball is None or not all(charge_hand(hand, face) for hand in hands):
        return False
    # Palms roughly face each other, so the hands point roughly the same way.
    d0 = (hands[0][9].x-hands[0][0].x, hands[0][9].y-hands[0][0].y)
    d1 = (hands[1][9].x-hands[1][0].x, hands[1][9].y-hands[1][0].y)
    cosine = (d0[0]*d1[0]+d0[1]*d1[1])/(dist((0, 0), d0)*dist((0, 0), d1))
    return degrees(acos(max(-1.0, min(1.0, cosine)))) < 120


def opening_hand(hand: Hand, base: float = 0.0) -> bool:
    """A hand that is opening: at least three extended fingers and straighter than the charge was."""
    if not valid_hand(hand) or sum(extended(hand, b) for b in (5, 9, 13, 17)) < 3:
        return False
    return finger_curl(hand) >= min(WAVE_OPEN_CURL, base+WAVE_OPEN_MARGIN)


def push_pose(hands: Sequence[Hand], face: Face) -> bool:
    """Both hands open and together in front of the body (kept as a strict reference pose)."""
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
        self.curl_base = 0.0
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

    def _end_charge(self) -> None:
        self.charge_since, self.level = None, 0.0
        self.trail.clear()

    def _fire(self, ball: Ball | None, now: float) -> Recognition:
        level = self.level
        self._pulse()
        self._end_charge()
        return Recognition(True, 1.0, 'Onda disparada! Baixe as mãos antes de repetir.', False, level, ball)

    def _growing(self) -> bool:
        """Were the hands getting larger (closer to the camera) over the last frames?"""
        if len(self.trail) < 3 or self.trail[-1][0]-self.trail[0][0] < .12:
            return False
        sizes = [size for _, size, _ in self.trail]
        early = sorted(sizes[:max(1, len(sizes)//2)])
        return sizes[-1]/early[len(early)//2] >= WAVE_GROWTH

    def _wave(self, hands: Sequence[Hand], face: Face, now: float, instruction: str) -> Recognition:
        """Charge with cupped hands below the mouth, then open them (or push): the pulse is the shot."""
        valid = [hand for hand in hands if valid_hand(hand)]
        charged = charge_pose(hands, face)
        if not self.armed:
            # At start-up and after a shot the pose has to be released before it counts again.
            if charged or any(charge_hand(hand, face) or opening_hand(hand) for hand in valid):
                self.neutral_since = None
            else:
                self._neutral(now)
            return Recognition(False, 0, 'Baixe as mãos antes de carregar de novo.' if hands else instruction)
        centre = face.x+face.width/2
        ball = wave_ball(hands, face, 1.3)
        if ball is None and len(valid) == 1:
            ball = hand_ball(valid[0])
        if self.charge_since is not None:
            gap = now-self.charge_seen
            if gap > WAVE_WINDOW:
                self._end_charge()
            else:
                if valid:
                    size = sum(distance(hand, 0, 9) for hand in valid)/len(valid)
                    if not self.trail or now > self.trail[-1][0]:
                        self.trail.append((now, size, abs((ball or self.last_ball or Ball(centre, 0, 0)).x-centre)))
                    while self.trail and now-self.trail[0][0] > .7:
                        self.trail.popleft()
                opened = [hand for hand in valid if opening_hand(hand, self.curl_base)]
                if opened and self.level >= WAVE_MIN_CHARGE:
                    return self._fire(ball or self.last_ball, now)
                if not valid and self.level >= WAVE_FULL_CHARGE and self._growing():
                    return self._fire(self.last_ball, now)
        keep = [hand for hand in valid if charge_hand(hand, face)]
        if charged or (self.charge_since is not None and keep):
            if self.charge_since is None:
                self.charge_since = now
                self.trail.clear()
                self.curl_base = 0.0
            curl = sum(finger_curl(hand) for hand in keep)/len(keep)
            self.curl_base = curl if self.curl_base == 0.0 else self.curl_base*.8+curl*.2
            ball = ball or self.last_ball
            self.charge_seen = now
            self.last_ball = ball
            self.level = min(1.0, (now-self.charge_since)/WAVE_CHARGE_SECONDS)
            if not self.trail or now > self.trail[-1][0]:
                size = sum(distance(hand, 0, 9) for hand in keep)/len(keep)
                self.trail.append((now, size, abs(ball.x-centre)))
            while self.trail and now-self.trail[0][0] > .7:
                self.trail.popleft()
            return Recognition(False, self.level, 'Carga completa! Abra as mãos e empurre.' if self.level >= 1
                               else 'Carregando… mantenha as mãos juntas.', True, self.level, ball)
        if self.charge_since is not None:
            # Between the pose and the release: the ball lingers while tracking flickers.
            gap = now-self.charge_seen
            return Recognition(False, self.level, 'Agora abra as mãos e empurre.',
                               gap <= WAVE_GRACE, self.level, self.last_ball)
        if len(valid) == 1 and charge_hand(valid[0], face):
            return Recognition(False, 0, 'Só vejo uma mão. Junte as duas mãos em concha.')
        if charged is False and len(valid) == 2 and all(charge_hand(hand, face) for hand in valid):
            return Recognition(False, 0, 'Aproxime as duas mãos, palma com palma, em concha.')
        return Recognition(False, 0, 'Junte as duas mãos em concha na frente do peito.' if valid else instruction)

    def update(self, hands: Sequence[Hand], face: Face | None, now: float, effect: str) -> Recognition:
        guide = guide_for(effect)
        if effect != self.mode:
            self.reset()
            self.mode = effect
        if not isfinite(now):
            self.reset()
            return Recognition(False, 0, 'Aguardando uma observação válida.')
        if self.last is not None and (now <= self.last or now-self.last > WAVE_MAX_GAP):
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
