"""Original, deterministic webcam exits. No downloaded art or character assets."""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from .effects import Silhouette, TeleportEffect, mix, smooth, solid
from .scene import Frame


class CreativeEffect(TeleportEffect):
    """Animate a bounded cutout at <= 360px, then composite onto the live background."""
    duration = 0.9
    kind = 'puff'
    eager = False  # builds its own fields below

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        # Leave room for smoke, flight and the portal without touching the whole image.
        left, top, right, bottom = self.box
        height, width = subject.mask.shape
        pad = max(24, (right-left)//2)
        self.box = (max(0, left-pad), max(0, top-pad//2), min(width, right+pad), min(height, bottom+pad//2))
        left, top, right, bottom = self.box
        self.size = (right-left, bottom-top)
        # Smoke is deliberately soft; a smaller working canvas keeps its extra volume layers cheap.
        limit = 240 if self.kind == 'puff' else 360
        scale = min(1.0, limit/max(self.size))
        size = (max(2, round(self.size[0]*scale)), max(2, round(self.size[1]*scale)))
        self.person = cv2.resize(subject.frame[top:bottom, left:right], size)
        self.alpha = cv2.resize(np.clip(subject.mask[top:bottom, left:right], 0, 1), size)
        self.alpha = cv2.GaussianBlur(self.alpha, (0, 0), .8)
        self.h, self.w = self.alpha.shape
        self.yy, self.xx = np.mgrid[:self.h, :self.w].astype(np.float32)
        occupied = cv2.findNonZero((self.alpha > .4).astype(np.uint8))
        x, y, w, h = cv2.boundingRect(occupied)
        self.center = (x+w/2, y+h/2)
        self.body_size = (w, h)
        rng = np.random.default_rng(291)
        noise = rng.random((max(2, self.h//9), max(2, self.w//9))).astype(np.float32)
        self.noise = cv2.resize(noise, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        self.blocks = cv2.resize(noise, (self.w, self.h), interpolation=cv2.INTER_NEAREST)
        ys, xs = np.nonzero(self.alpha > .6)
        selected = rng.choice(len(xs), min(230, len(xs)), replace=False)
        self.particles = [(int(xs[i]), int(ys[i]), float(rng.uniform(.5, 1.5)), float(rng.uniform(-1, 1))) for i in selected]
        self.clouds = [(float(rng.uniform(-.5, .5)), float(rng.uniform(-.5, .5)), float(rng.uniform(.12, .25))) for _ in range(13)]
        if self.kind == 'puff':
            coarse=rng.random((18,18)).astype(np.float32)
            fine=rng.random((55,55)).astype(np.float32)
            self.smoke_noise=cv2.resize(coarse,(self.w,self.h),interpolation=cv2.INTER_CUBIC)*.7+cv2.resize(fine,(self.w,self.h),interpolation=cv2.INTER_LINEAR)*.3
            self.smoke_noise=cv2.GaussianBlur(self.smoke_noise,(0,0),1.1)
            self.smoke_core=cv2.dilate(self.alpha,np.ones((13,13),np.uint8))
            # Staggered lobes cover the actual torso/head, rather than a few disconnected discs.
            self.plumes=[(float(dx+rng.uniform(-.08,.08)),float(dy+rng.uniform(-.05,.05)),float(rng.uniform(.30,.42)),float(rng.uniform(.17,.24)),float(rng.uniform(.7,1.3)))
                         for dy in (-.44,-.22,0,.22,.44) for dx in (-.30,.30)]

    @staticmethod
    def over(base: Frame, color: Frame, alpha: np.ndarray) -> Frame:
        a = np.clip(alpha, 0, 1)[:, :, None]
        return np.clip(base.astype(np.float32)*(1-a)+color.astype(np.float32)*a, 0, 255).astype(np.uint8)

    def render(self, live: Frame, background: Frame, now: float) -> Frame:
        if live.shape != background.shape or live.shape != self.subject.frame.shape:
            raise ValueError('Resolução mudou durante o efeito.')
        p = min(1.0, max(0.0, (now-self.started)/self.duration))
        if p <= 0:
            return live.copy() if self.hidden_target else background.copy()
        if p >= 1:
            return background.copy() if self.hidden_target else live.copy()
        u = p if self.hidden_target else 1-p
        left, top, right, bottom = self.box
        patch = cv2.resize(background[top:bottom, left:right], (self.w, self.h))
        image, coverage = self._layers(patch, u)
        # Composite the effect delta, so unaffected background stays bit exact.
        full = cv2.resize(image, self.size, interpolation=cv2.INTER_LINEAR)
        alpha = cv2.resize(coverage, self.size, interpolation=cv2.INTER_LINEAR)
        result = background.copy()
        original = result[top:bottom, left:right]
        active = alpha > .002
        original[active] = full[active]
        return result

    def _layers(self, patch: Frame, u: float) -> tuple[Frame, np.ndarray]:
        if self.kind == 'puff':
            return self._puff(patch, u)
        if self.kind in ('digital', 'dust'):
            return self._dissolve(patch, u)
        return self._motion(patch, u)

    def _puff(self, patch: Frame, u: float) -> tuple[Frame, np.ndarray]:
        body = self.alpha*(1-smooth((u-.18)/.19))
        result = self.over(patch, self.person, body)
        density = np.zeros_like(self.alpha)
        volume = np.zeros_like(self.alpha)
        cx, cy = self.center
        bw, bh = self.body_size
        growth = .22+1.12*smooth(u/.40)
        drift = smooth((u-.35)/.65)
        flow_x=self.xx+np.sin(self.yy*.035+u*9)*4
        flow_y=self.yy+u*22
        noise=cv2.remap(self.smoke_noise,flow_x.astype(np.float32),flow_y.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
        for index,(dx,dy,rx,ry,speed) in enumerate(self.plumes):
            x=cx+dx*bw*growth+np.sin(u*6+index)*bw*.04*drift
            y=cy+dy*bh*growth-drift*bh*.20*speed
            q=((self.xx-x)/max(2,bw*rx*growth))**2+((self.yy-y)/max(2,bh*ry*growth))**2
            depth=np.clip(1-q,0,1)
            density=np.maximum(density,np.clip((1-q+(noise-.5)*.35)*7,0,1))
            volume=np.maximum(volume,depth)
        # The thick core hides the cut at the peak, even on a broad silhouette.
        core=self.smoke_core*smooth(u/.20)*(1-smooth((u-.40)/.25))
        density=np.maximum(density,core)
        envelope=smooth(u/.16)*(1-smooth((u-.50)/.50))
        clouds=cv2.GaussianBlur(density,(0,0),.85)*envelope
        shade=np.where(volume>.55,1.,np.where(volume>.16,.94,.84)).astype(np.float32)
        shade=np.clip(shade+(noise-.5)*.06,.78,1)
        smoke=(np.array((238,241,247),np.float32)*shade[:,:,None]).astype(np.uint8)
        shadow=cv2.GaussianBlur(clouds,(0,0),4)*.15
        result=self.over(result,np.full_like(patch,(118,112,111)),shadow)
        result = self.over(result, smoke, clouds)
        rim=cv2.morphologyEx(clouds,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))*.18
        result=self.over(result,np.full_like(patch,(137,133,137)),rim)
        return result, np.maximum(body, np.maximum(clouds,shadow))

    def _dissolve(self, patch: Frame, u: float) -> tuple[Frame, np.ndarray]:
        digital = self.kind == 'digital'
        field = self.blocks if digital else self.noise
        sweep = (self.xx/self.w)*.65+field*.35
        threshold = smooth((u-.04)/.80)
        survival = np.clip((sweep-threshold)*18, 0, 1)
        body = self.alpha*survival
        person = self.person
        if digital:
            small = cv2.resize(person, (max(2, self.w//10), max(2, self.h//10)), interpolation=cv2.INTER_AREA)
            person = cv2.resize(small, (self.w, self.h), interpolation=cv2.INTER_NEAREST)
            shift = np.sin(self.yy*.13+u*36)*smooth(u/.2)*5
            person = cv2.remap(person, self.xx+shift.astype(np.float32), self.yy, cv2.INTER_NEAREST)
        result = self.over(patch, person, body)
        flecks = np.zeros_like(self.alpha)
        colors = np.zeros_like(patch)
        for x, y, speed, drift in self.particles:
            activation = float(sweep[y, x])
            age = (threshold-activation)/.38
            if 0 < age < 1:
                px = round(x+age*self.w*.32*speed)
                py = round(y-age*self.h*.18+drift*age*25)
                radius = max(1, round((4 if digital else 2)*(1-age)))
                opacity = (1-age)*.9
                color = tuple(int(v) for v in self.person[y, x])
                if digital:
                    cv2.rectangle(flecks, (px, py), (px+radius, py+radius), opacity, -1)
                    cv2.rectangle(colors, (px, py), (px+radius, py+radius), color, -1)
                else:
                    cv2.circle(flecks, (px, py), radius, opacity, -1, cv2.LINE_AA)
                    cv2.circle(colors, (px, py), radius, color, -1, cv2.LINE_AA)
        return self.over(result, colors, flecks), np.maximum(body, flecks)

    def _motion(self, patch: Frame, u: float) -> tuple[Frame, np.ndarray]:
        cx, cy = self.center
        portal = self.kind == 'portal'
        travel = smooth((u-.12)/.70)
        sx = max(.01, 1-travel*.98) if portal else 1+.35*np.sin(np.pi*travel)
        sy = max(.01, 1-travel*.98) if portal else max(.5, 1-.35*np.sin(np.pi*travel))
        dx = travel*self.body_size[0]*.45 if portal else travel*self.w*1.45
        matrix = np.float32([[sx, 0, cx*(1-sx)+dx], [0, sy, cy*(1-sy)]])
        person = cv2.warpAffine(self.person, matrix, (self.w, self.h))
        alpha = cv2.warpAffine(self.alpha, matrix, (self.w, self.h))*(1-smooth((u-.75)/.20))
        result = patch.copy()
        coverage = alpha.copy()
        if portal:
            portal_mask = np.zeros_like(alpha)
            envelope = smooth(u/.16)*(1-smooth((u-.76)/.24))
            center = (round(cx+self.body_size[0]*.45), round(cy))
            axes = (max(2, round(self.body_size[0]*.30*envelope)), max(2, round(self.body_size[1]*.52*envelope)))
            cv2.ellipse(portal_mask, center, axes, 0, 0, 360, .7*envelope, -1, cv2.LINE_AA)
            result = self.over(result, np.full_like(patch, (59, 30, 42)), portal_mask)
            rim = np.zeros_like(alpha)
            cv2.ellipse(rim, center, axes, 0, 0, 360, envelope, 3, cv2.LINE_AA)
            result = self.over(result, np.full_like(patch, (255, 170, 105)), cv2.GaussianBlur(rim, (0, 0), 3)*.6)
            result = self.over(result, np.full_like(patch, (255, 227, 189)), rim)
            coverage = np.maximum(coverage, np.maximum(portal_mask, cv2.GaussianBlur(rim, (0, 0), 3)))
        else:
            # A stretched, translucent silhouette sells acceleration without a full-screen wipe.
            trail = cv2.GaussianBlur(alpha, (31, 1), 0)*np.sin(np.pi*travel)*.35
            result = self.over(result, np.full_like(patch, (220, 209, 192)), trail)
            coverage = np.maximum(coverage, trail)
        return self.over(result, person, alpha), coverage


@lru_cache(maxsize=32)
def _kernel(size: int, circle: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pixel offsets and weights of one particle: a soft disc or a hard square."""
    if circle:
        r = np.arange(-size - 1, size + 2)
        oy, ox = np.meshgrid(r, r, indexing='ij')
        weight = np.clip(size + .5 - np.hypot(ox, oy), 0, 1)
    else:
        r = np.arange(size) - size // 2
        oy, ox = np.meshgrid(r, r, indexing='ij')
        weight = np.ones(ox.shape)
    keep = weight.ravel() > .01
    return ox.ravel()[keep], oy.ravel()[keep], weight.ravel()[keep].astype(np.float32)


def splat(image: Frame, box: tuple[int, int, int, int], x: np.ndarray, y: np.ndarray, size: np.ndarray,
          opacity: np.ndarray, colors: np.ndarray, circle: bool) -> None:
    """Draw many particles at once (grouped by size), clipped to `box`, in place."""
    left, top, right, bottom = box
    for s in np.unique(size):
        pick = size == s
        ox, oy, kw = _kernel(int(s), circle)
        gx = x[pick, None] + ox[None]
        gy = y[pick, None] + oy[None]
        gw = opacity[pick, None] * kw[None]
        ok = (gx >= left) & (gx < right) & (gy >= top) & (gy < bottom) & (gw > .004)
        if not ok.any():
            continue
        col = np.broadcast_to(colors[pick, None, :], gx.shape + (3,))[ok].astype(np.float32)
        gx, gy, gw = gx[ok], gy[ok], gw[ok][:, None]
        now = image[gy, gx].astype(np.float32)
        image[gy, gx] = (now * (1 - gw) + col * gw + .5).astype(np.uint8)


class FullResEffect(TeleportEffect):
    """Person kept at camera resolution inside a tight box; effects live in a larger `box`.

    Everything time-independent is built in __init__; a frame only blends uint8 layers.
    """
    eager = False
    pads = (.08, .5, .2, 0.)   # fractions of the person's size: left, right, top, bottom
    span = .35                 # life of a particle, in dissolve-front units

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        self.tbox = self.box
        tl, tt, tr, tb = self.tbox
        ih, iw = subject.mask.shape
        w, h = tr - tl, tb - tt
        pl, pr, pt, pb = self.pads
        self.box = (max(0, tl - max(24, round(w*pl))), max(0, tt - max(12, round(h*pt))),
                    min(iw, tr + max(24, round(w*pr))), min(ih, tb + max(12, round(h*pb))))
        self.h, self.w = self.alpha.shape
        self.rng = np.random.default_rng(291)

    def _pick_particles(self, count: int) -> None:
        ys, xs = np.nonzero(self.alpha[::2, ::2] > .7)
        pick = self.rng.choice(len(xs), min(count, len(xs)), replace=False)
        self.px, self.py = xs[pick]*2, ys[pick]*2
        self.speed = self.rng.uniform(.6, 1.4, len(pick)).astype(np.float32)
        self.drift = self.rng.uniform(-1, 1, len(pick)).astype(np.float32)
        self.base = self.rng.uniform(.6, 1.4, len(pick)).astype(np.float32)
        self.color = self.person[self.py, self.px]
        self.act = self.sweep[self.py, self.px]

    def _front(self, u: float) -> float:
        """Dissolve front: starts left of every pixel, ends once the last particle is gone."""
        start = -1.0/self.gain
        return start + (1 + self.span - start)*min(1.0, max(0.0, (u-.02)/.96))

    def _frame(self, background: Frame, u: float) -> Frame:
        thr = self._front(u)
        result = background.copy()
        tl, tt, tr, tb = self.tbox
        tight = result[tt:tb, tl:tr]
        self._under(tight, u, thr)
        if thr < 1.0:
            weight = np.subtract(self.sweep_g, thr*self.gain, dtype=np.float32)
            np.clip(weight, 0, 1, out=weight)
            weight *= self.alpha
            tight[:] = mix(tight, self._layer(u, thr), weight, self._scratch)
        self._over(tight, u, thr)
        self._particles(result, u, thr)
        return result

    def _under(self, tight: Frame, u: float, thr: float) -> None:
        pass

    def _over(self, tight: Frame, u: float, thr: float) -> None:
        pass

    def _layer(self, u: float, thr: float) -> Frame:
        return self.person

    def _particles(self, result: Frame, u: float, thr: float) -> None:
        t = (thr - self.act)/self.span
        birth = 1.0/(self.span*self.gain)   # still sitting in place while the body fades out
        live = (t > -birth) & (t < 1)
        if not live.any():
            return
        t, sel = t[live], np.flatnonzero(live)
        age = np.clip(t, 0, 1)
        x, y = self._move(age, sel)
        size = np.maximum(1, np.rint(self.base[sel]*self._size(age))).astype(np.int32)
        opacity = np.where(t < 0, np.clip(1 + t*self.span*self.gain, 0, 1), self._fade(age)).astype(np.float32)
        tl, tt, _, _ = self.tbox
        splat(result, self.box, np.rint(x).astype(np.int32) + tl, np.rint(y).astype(np.int32) + tt,
              size, opacity, self.color[sel], self.circle)


class DigitalEffect(FullResEffect):
    """Scan front: the person turns to blocks, glitches sideways and flies off as squares."""
    kind = 'digital'
    duration = .85
    gain = 9.
    circle = False
    pads = (.08, .45, .2, 0.)

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        h, w = self.h, self.w
        cell = max(8, round(max(w, h)/32))
        grid = (max(2, round(w/cell)), max(2, round(h/cell)))
        noise = self.rng.random(grid[::-1]).astype(np.float32)
        column = (np.arange(grid[0], dtype=np.float32) + .5)/grid[0]
        sweep = column[None, :]*.6 + noise*.4
        self.sweep = cv2.resize(sweep, (w, h), interpolation=cv2.INTER_NEAREST)
        self.sweep_g = self.sweep*self.gain
        mosaic = cv2.resize(self.person, grid, interpolation=cv2.INTER_AREA)
        self.mosaic = cv2.resize(mosaic, (w, h), interpolation=cv2.INTER_NEAREST)
        self.bands = np.linspace(0, h, max(4, h//28) + 1).astype(int)
        self.band_phase = self.rng.uniform(0, 6.28, len(self.bands) - 1).astype(np.float32)
        self.glow_color = solid(self.person.shape, (255, 232, 140))
        self._pick_particles(int(np.clip(cv2.countNonZero((self.alpha > .5).view(np.uint8)) // 800, 200, 900)))

    def _move(self, age, sel):
        fly = age*age   # starts at rest, accelerates
        x = self.px[sel] + fly*self.w*.38*self.speed[sel]
        y = self.py[sel] - fly*self.h*.12*self.speed[sel] + self.drift[sel]*age*self.h*.04
        return x, y

    def _size(self, age):
        return 2 + 14*(1 - age**1.5)*self.w/1000

    def _fade(self, age):
        return 1 - age**2.5

    def _layer(self, u, thr):
        ramp = smooth(u/.1)
        look = self.person
        if ramp > .003:
            # Blocks appear just ahead of the scan front, not everywhere at once.
            band = np.subtract(self.sweep, thr, dtype=np.float32)
            np.multiply(band, -5*ramp, out=band)
            band += ramp
            np.clip(band, 0, 1, out=band)
            look = mix(self.person, self.mosaic, band, np.empty_like(band))
            amp = self.w*.012*smooth(u/.15)*(1 - smooth((u-.55)/.3))
            if amp > .5:
                for i in range(len(self.bands) - 1):
                    s = int(round(np.sin(self.band_phase[i]*3 + u*36)*amp*(i % 3 != 0)))
                    if s:
                        rows = look[self.bands[i]:self.bands[i+1]]
                        keep = rows.copy()
                        if s > 0:
                            rows[:, s:] = keep[:, :-s]
                            rows[:, :s] = keep[:, :1]
                        else:
                            rows[:, :s] = keep[:, -s:]
                            rows[:, s:] = keep[:, -1:]
        return look

    def _over(self, tight, u, thr):
        ramp = smooth(u/.1)
        if thr >= 1.08 or ramp < .01:
            return
        edge = np.subtract(self.sweep, thr + .02, dtype=np.float32)
        np.abs(edge, out=edge)
        edge *= -16
        edge += 1
        np.clip(edge, 0, 1, out=edge)
        edge *= self.alpha
        edge *= .55*ramp
        tight[:] = mix(tight, self.glow_color, edge, self._scratch)


class DustEffect(FullResEffect):
    """Grains erode away along a noisy front and are carried up and sideways by the wind."""
    kind = 'dust'
    duration = 1.15
    gain = 14.
    circle = True
    span = .42
    pads = (.1, .4, .15, 0.)

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        h, w = self.h, self.w

        def field(cell: int):
            grid = (max(2, w//cell), max(2, h//cell))
            return cv2.resize(self.rng.random(grid[::-1]).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        column = np.linspace(0, 1, w, dtype=np.float32)[None, :]
        self.sweep = column*.55 + field(90)*.30 + field(4)*.15
        self.sweep_g = self.sweep*self.gain
        # Soft haze layer at 1/6 resolution: the only part that is not full-res.
        self.hs = (max(2, w//6), max(2, h//6))
        self.h_alpha = cv2.resize(self.alpha, self.hs, interpolation=cv2.INTER_AREA)
        self.h_sweep = cv2.resize(self.sweep, self.hs, interpolation=cv2.INTER_AREA)
        mean = cv2.mean(self.person, mask=(self.alpha > .5).view(np.uint8))[:3]
        tone = tuple(int(.7*m + .3*c) for m, c in zip(mean, (215, 218, 226)))
        self.haze_color = solid(self.person.shape, tone)
        self._pick_particles(int(np.clip(cv2.countNonZero((self.alpha > .5).view(np.uint8)) // 350, 400, 1800)))

    def _move(self, age, sel):
        fly = age**1.7
        x = self.px[sel] + fly*self.w*.24*self.speed[sel] + np.sin(self.drift[sel]*6 + age*5)*age*self.w*.008
        y = self.py[sel] - age*self.h*.03*self.speed[sel] - fly*self.h*.10*self.speed[sel] + self.drift[sel]*age*self.h*.03
        return x, y

    def _size(self, age):
        return (1.5 + 2.5*(1 - age**1.3))*max(1, self.w/700)

    def _fade(self, age):
        return .9*(1 - age**2)

    def _under(self, tight, u, thr):
        envelope = 1 - smooth((u-.55)/.4)
        if envelope < .01:
            return
        sw, sh = self.hs
        gone = np.clip(self.h_sweep*self.gain - thr*self.gain, 0, 1)
        dens = self.h_alpha*(1 - gone)*np.clip(1 - (thr - self.h_sweep)/.5, 0, 1)
        shift = np.float32([[1, 0, u*u*sw*.12], [0, 1, -u*sh*.06]])
        dens = cv2.GaussianBlur(cv2.warpAffine(dens, shift, (sw, sh)), (0, 0), 2.2)
        haze = cv2.resize(dens, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        haze *= .55*envelope
        tight[:] = mix(tight, self.haze_color, haze, self._scratch)


class CartoonExitEffect(FullResEffect):
    """Crouch, then dash sideways with stretch and a speed smear; reversed on return."""
    kind = 'cartoon'
    duration = .65
    gain = 1.

    def __init__(self, subject: Silhouette, hidden_target: bool, started: float) -> None:
        super().__init__(subject, hidden_target, started)
        tl, tt, tr, tb = self.tbox
        left, top, _, bottom = self.box
        # The dash must be able to leave the frame, never be clipped inside it.
        self.box = (left, top, subject.mask.shape[1], bottom)
        occupied = cv2.compare(self.alpha, .4, cv2.CMP_GT)
        x, y, w, h = cv2.boundingRect(occupied)
        self.center = (x + w/2, y + h)   # squash/stretch pivots on the feet/bottom edge
        alpha8 = np.rint(self.alpha*255).astype(np.uint8)
        self.sprite = cv2.merge([self.person[:, :, 0], self.person[:, :, 1], self.person[:, :, 2], alpha8])
        self.distance = self.box[2] - tl + self.center[0]*.5 + 8
        self.tint = solid((bottom - top, self.box[2] - left, 3), (220, 209, 192))

    def _frame(self, background: Frame, u: float) -> Frame:
        result = background.copy()
        tl, tt, _, _ = self.tbox
        left, top, right, bottom = self.box
        cx, cy = self.center
        crouch = float(np.sin(np.pi*min(1.0, u/.16)))
        launch = min(1.0, max(0.0, (u-.08)/.92))
        speed = launch**1.4                      # 0..1, grows with the dash
        stretch = .35*smooth(min(1.0, launch*2))
        sx = (1 + stretch)*(1 + .05*crouch)
        sy = (1 - .75*stretch)*(1 - .07*crouch)
        dx = launch**2.2*self.distance - .04*self.w*crouch
        matrix = np.float32([[sx, 0, tl + cx*(1-sx) + dx], [0, sy, tt + cy*(1-sy)]])
        # Window in frame coordinates: the moved sprite plus room for its smear.
        corners = np.float32([[0, 0], [self.w, 0], [0, self.h], [self.w, self.h]])
        moved = corners@matrix[:, :2].T + matrix[:, 2]
        smear = int(self.w*.3*speed)
        forward = self.hidden_target
        x0 = int(np.floor(moved[:, 0].min())) - (smear if forward else 0)
        x1 = int(np.ceil(moved[:, 0].max())) + (0 if forward else smear)
        y0, y1 = int(np.floor(moved[:, 1].min())), int(np.ceil(moved[:, 1].max()))
        x0, y0, x1, y1 = max(left, x0), max(top, y0), min(right, x1), min(bottom, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return result
        window = result[y0:y1, x0:x1]
        shifted = matrix.copy()
        shifted[0, 2] -= x0
        shifted[1, 2] -= y0
        warped = cv2.warpAffine(self.sprite, shifted, (x1-x0, y1-y0), flags=cv2.INTER_LINEAR)
        body = warped[:, :, 3].astype(np.float32)
        body *= 1/255
        if smear > 3:
            trail = cv2.blur(body, (smear, 1), anchor=(0 if forward else smear-1, 0))
            trail *= .42*(1 - smooth((launch-.88)/.12))
            window[:] = mix(window, self.tint[:y1-y0, :x1-x0], trail, np.empty_like(trail))
        window[:] = mix(window, np.ascontiguousarray(warped[:, :, :3]), body, np.empty_like(body))
        return result


class PuffEffect(CreativeEffect):
    kind = 'puff'
    duration = 1.05

