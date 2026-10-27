from __future__ import annotations
from dataclasses import dataclass
from functools import cached_property, lru_cache
import cv2
import numpy as np
from numpy.typing import NDArray
from .scene import Frame

Mask = NDArray[np.float32]

@dataclass(frozen=True)
class Silhouette:
    captured_at: float
    frame: Frame
    mask: Mask


def smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def ease_in(p: float) -> float:
    """Slow start (anticipation) then acceleration; reversed in time it eases out."""
    p = min(1.0, max(0.0, p))
    return 0.3 * p + 0.7 * p * p * p


def mix(base: Frame, layer: Frame, weight: NDArray[np.float32], scratch: NDArray[np.float32]) -> Frame:
    """base*(1-weight)+layer*weight on uint8 images, one fused multithreaded call."""
    np.subtract(1.0, weight, out=scratch)
    return cv2.blendLinear(base, layer, scratch, weight)


@lru_cache(maxsize=12)
def solid(shape: tuple[int, ...], color: tuple[int, int, int]) -> Frame:
    """Shared read-only flat-color image, so effects do not each allocate one."""
    image = np.empty(shape, np.uint8)
    image[:] = color
    image.flags.writeable = False
    return image


def vblur(alpha: Mask, size: int) -> Mask:
    """Vertical blur of a soft mask, computed at half resolution (it is a soft layer)."""
    h, w = alpha.shape
    small = cv2.resize(alpha, (max(2, w // 2), max(2, h // 2)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (1, size // 2 | 1), 0)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def streak_profiles(radius: int = 9) -> dict[int, tuple[NDArray[np.float32], NDArray[np.float32]]]:
    """Cross-section (core, glow) of a vertical light line, for 1 and 2 px widths."""
    dx = np.arange(-radius, radius + 1, dtype=np.float32)
    out = {}
    for width in (1, 2):
        core = np.clip(width * 0.5 + 0.5 - np.abs(dx), 0, 1)
        glow = np.exp(-dx * dx / (2 * 2.5 ** 2)) * 0.07 * width
        out[width] = (core.astype(np.float32), glow.astype(np.float32))
    return out


def paint_streak(roi: Frame, halo: Mask, col: int, head: int, tail: int, width: int, strength: float,
                 color: NDArray[np.float32], profiles, dark: float = 0.0) -> None:
    """Draw one vertical light line in place; the head (small y) is bright, the tail fades."""
    radius = (len(profiles[1][0]) - 1) // 2
    rh, rw = halo.shape
    y0, y1 = max(0, head), min(rh, tail + 1)
    x0, x1 = max(0, col - radius), min(rw, col + radius + 1)
    if y1 <= y0 or x1 <= x0 or strength <= 0.003:
        return
    core, glow = profiles[width]
    sl = slice(x0 - col + radius, x1 - col + radius)
    along = (tail - np.arange(y0, y1, dtype=np.float32)) / max(1, tail - head)
    along = np.minimum(along, np.minimum(1.0, (np.arange(y0, y1, dtype=np.float32) - head) / 3 + 0.25))
    gate = halo[y0:y1, x0:x1] * (np.clip(along, 0, 1)[:, None] * strength)
    light = np.minimum(gate * (core[sl] * 0.85 + glow[sl])[None, :], 0.9)[:, :, None]
    patch = roi[y0:y1, x0:x1]
    value = patch.astype(np.float32)
    if dark:
        value *= 1 - np.minimum(gate * (np.maximum(core[sl], glow[sl] * 3)[None, :] * dark), 0.5)[:, :, None]
    value = value * (1 - light) + color * light
    patch[:] = (value + 0.5).astype(np.uint8)


class TeleportEffect:
    """One captured silhouette; all animation uses elapsed time, never frame count."""
    duration = 0.48
    eager = True  # build streaks/halo/grids in __init__ (subclasses that never use them set False)

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        if subject.mask.shape != subject.frame.shape[:2] or not np.isfinite(subject.mask).all():
            raise ValueError('Recorte de pessoa inválido.')
        self.subject = subject
        self.hidden_target = hidden_target
        self.started = started
        occupied = cv2.compare(subject.mask, 0.4, cv2.CMP_GT)
        if cv2.countNonZero(occupied) < 100:
            raise ValueError('Não encontrei uma silhueta. Entre no enquadramento.')
        x, y, w, h = cv2.boundingRect(occupied)
        pad = max(12, round(w * 0.06))
        ih, iw = subject.mask.shape
        self.box = (max(0, x-pad), max(0, y-pad), min(iw, x+w+pad), min(ih, y+h+pad))
        left, top, right, bottom = self.box
        self.person = subject.frame[top:bottom,left:right].copy()
        self.alpha = cv2.GaussianBlur(np.clip(subject.mask[top:bottom,left:right], 0, 1), (0,0), 1.1)
        # Heavy or rarely used fields are built on first access (same meaning, no init cost).
        self._scratch = np.empty_like(self.alpha)
        if self.eager:
            self._prepare()

    @cached_property
    def _grid(self) -> tuple[Mask, Mask]:
        rh, rw = self.alpha.shape
        yy, xx = np.mgrid[:rh,:rw]
        return xx.astype(np.float32), yy.astype(np.float32)

    @cached_property
    def xx(self) -> Mask: return self._grid[0]

    @cached_property
    def yy(self) -> Mask: return self._grid[1]

    @cached_property
    def _aux(self):
        rh, rw = self.alpha.shape
        rng = np.random.default_rng(47)
        strips = rng.uniform(0,1,(1,max(2,rw//4))).astype(np.float32)
        strips = cv2.resize(strips,(rw,rh),interpolation=cv2.INTER_NEAREST)
        # Position streaks using actual occupied columns, avoiding a rectangular effect.
        columns = np.flatnonzero(self.alpha.max(axis=0) > 0.5)
        streaks: list[tuple[int,int,int,float,int]] = []
        for col in rng.choice(columns, size=min(30,len(columns)), replace=False):
            rows = np.flatnonzero(self.alpha[:,col] > 0.4)
            if rows.size:
                streaks.append((int(col),int(rows[0]),int(rows[-1]),float(rng.uniform(0.7,1.3)),int(rng.integers(1,3))))
        return strips, streaks

    @cached_property
    def strips(self) -> Mask: return self._aux[0]

    @cached_property
    def streaks(self) -> list[tuple[int,int,int,float,int]]: return self._aux[1]

    @cached_property
    def halo(self) -> Mask:
        # Dilation at half resolution; it only gates soft light, so detail is irrelevant.
        h, w = self.alpha.shape
        small = cv2.resize(self.alpha, (max(2, w//2), max(2, h//2)), interpolation=cv2.INTER_AREA)
        small = cv2.dilate(small, np.ones((5,5), np.uint8))
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def finished(self, now: float) -> bool:
        return now-self.started >= self.duration

    def _check(self, live: Frame, background: Frame) -> None:
        if live.shape != background.shape or live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')

    def render(self, live: Frame, background: Frame, now: float) -> Frame:
        self._check(live, background)
        p = min(1.0,max(0.0,(now-self.started)/self.duration))
        if p >= 1:
            return background.copy() if self.hidden_target else live.copy()
        if p <= 0:
            return live.copy() if self.hidden_target else background.copy()
        # Disappearance and return share one eased timeline in opposite directions.
        u = ease_in(p) if self.hidden_target else ease_in(1-p)
        return self._frame(background, u)

    def _prepare(self) -> None:
        """Touch every lazy field so the cost is paid in __init__, not in a rendered frame."""
        self._grid, self._aux, self.halo, self._trail, self._strips5, self._tint

    # Per-frame constants shared by the two effects below.
    @cached_property
    def _trail(self) -> Mask:
        return vblur(self.alpha, 31)

    @cached_property
    def _strips5(self) -> Mask:
        return self.strips * 5

    @cached_property
    def _tint(self) -> Frame:
        return np.full_like(self.person, (235,211,179))

    def _frame(self, background: Frame, u: float) -> Frame:
        energy = max(0.0,float(np.sin(np.pi*u)))
        left,top,right,bottom=self.box
        result=background.copy()
        roi=result[top:bottom,left:right]
        scratch=self._scratch
        # A pale, vertically stretched remnant persists after the body disappears.
        k=energy*0.16*(1-smooth((u-0.75)/0.25))
        if k>0.002:
            roi[:]=mix(roi,self._tint,self._trail*k,scratch)
        fade=1-smooth((u-0.10)/0.65)
        if fade>0.002:
            amp=energy*min(7,self.alpha.shape[1]*0.025)
            shift=(np.sin(np.arange(self.alpha.shape[0],dtype=np.float32)*0.075+u*32)*amp)[:,None]
            mapx=np.add(self.xx,shift,dtype=np.float32)
            warped=cv2.remap(self.person,mapx,self.yy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            opacity=np.subtract(self._strips5,(u*1.45-0.30)*5,dtype=np.float32)
            np.clip(opacity,0,1,out=opacity)
            opacity*=self.alpha
            opacity*=fade
            roi[:]=mix(roi,warped,opacity,scratch)
        if energy>0.01:
            rh=self.alpha.shape[0]
            color=np.array((255,239,213),np.float32)
            profiles=_PROFILES
            for col,y0,y1,speed,thickness in self.streaks:
                length=max(10,round((y1-y0)*0.5))
                center=round(y1-(u*1.65*speed)*(y1-y0+length))
                paint_streak(roi,self.halo,col,max(-length,center-length),min(rh+length,center),thickness,energy,color,profiles)
        # Keep unaffected background bit-exact outside the silhouette and glow.
        return result

_PROFILES = streak_profiles()

class AnimeTeleportEffect(TeleportEffect):
    """Cel-like colors, ink contour and a fast cut, followed by a short speed-line echo."""
    duration=0.42

    def __init__(self,subject:Silhouette,hidden_target:bool,started:float) -> None:
        super().__init__(subject,hidden_target,started)
        # Only the brief captured subject is stylized; the camera feed remains natural.
        softened=cv2.medianBlur(self.person,5)
        levels=((np.arange(256,dtype=np.uint16)//40)*40+20).clip(0,255).astype(np.uint8)
        self.natural=self.person
        self.cel=cv2.LUT(softened,levels)
        grey=cv2.cvtColor(softened,cv2.COLOR_BGR2GRAY)
        self.ink=(cv2.Canny(grey,55,130).astype(np.float32)/255)*self.alpha
        # Ink lines are baked into the cel layer, so no per-frame multiply is needed.
        self.cel=cv2.blendLinear(self.cel,np.zeros_like(self.cel),1-self.ink*.6,self.ink*.6)
        self.contour=cv2.morphologyEx((self.alpha>0.45).astype(np.uint8),cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8)).astype(np.float32)
        self.trail=vblur(self.alpha,41)
        self._ink_color=solid(self.person.shape,(28,25,24))
        self._echo_color=solid(self.person.shape,(250,211,150))
        self._grid,self.halo,self._aux

    def _prepare(self) -> None:
        pass  # this effect builds only what it uses, in __init__

    def _frame(self,background:Frame,u:float) -> Frame:
        energy=max(0.,float(np.sin(np.pi*u)))
        left,top,right,bottom=self.box
        result=background.copy()
        roi=result[top:bottom,left:right]
        scratch=self._scratch
        echo=max(0.,1-abs(u-.43)/.4)*.20
        if echo>0.002:
            roi[:]=mix(roi,self._echo_color,self.trail*echo,scratch)
        # A brief anticipation, a decisive disappearance, then only the echo.
        body=1-smooth((u-.14)/.28)
        if body>0.002:
            # The photo turns cel-shaded over the first instants instead of popping.
            c=smooth(u/.12)
            look=cv2.addWeighted(self.natural,1-c,self.cel,c,0) if c>0.003 else self.natural
            amp=energy*min(9,self.alpha.shape[1]*.03)
            if amp>0.05:
                shift=(np.sin(np.arange(self.alpha.shape[0],dtype=np.float32)*.045+u*30)*amp)[:,None]
                look=cv2.remap(look,np.add(self.xx,shift,dtype=np.float32),self.yy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
            alpha=np.multiply(self.alpha,body,dtype=np.float32)
            roi[:]=mix(roi,look,alpha,scratch)
            outline=np.multiply(self.contour,body*.85*c,dtype=np.float32)
            roi[:]=mix(roi,self._ink_color,outline,scratch)
        if energy>0.01:
            rh=self.alpha.shape[0]
            color=np.array((255,244,220),np.float32)
            for col,y0,y1,speed,width in self.streaks:
                length=max(18,round((y1-y0)*.7))
                end=round(y1+(0.20-u)*speed*(y1-y0+length)*1.8)
                paint_streak(roi,self.halo,col,end-length,end,width,energy,color,_PROFILES,dark=.45)
        return result
