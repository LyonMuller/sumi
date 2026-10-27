"""The energy wave: a charge overlay that follows the hands and a one-shot beam; the person never leaves."""
import math
import unittest
from statistics import median
from time import perf_counter

import cv2
import numpy as np

from sumi.effect_catalog import DESCRIPTIONS, EFFECTS, LABELS
from sumi.effects import Silhouette
from sumi.effects_energy import EnergyCharge, EnergyWaveEffect, shifted
from sumi.gesture_guides import GUIDES


def scene(width=1280, height=720, level=120, cx=None):
    cx = width // 2 if cx is None else cx
    mask = np.zeros((height, width), np.float32)
    cv2.circle(mask, (cx, int(height * .33)), height // 9, 1, -1)
    cv2.ellipse(mask, (cx, int(height * .9)), (width // 5, int(height * .38)), 0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 1.5)
    rng = np.random.default_rng(5)
    live = np.clip(rng.normal(level, 6, (height, width, 3)), 0, 255).astype(np.uint8)
    live[mask > .5] = (200, 120, 60)
    return live, Silhouette(10, live, mask)


def changed(frame, live, threshold=3):
    return np.abs(frame.astype(int) - live.astype(int)).max(axis=2) > threshold


class CatalogTests(unittest.TestCase):
    def test_the_wave_is_wired_with_a_generic_label_and_a_portuguese_description(self):
        self.assertIs(EFFECTS['kamehameha'], EnergyWaveEffect)
        self.assertEqual(LABELS['Onda de energia'], 'kamehameha')
        self.assertIn('mãos', DESCRIPTIONS['kamehameha'])
        for text in list(LABELS) + [DESCRIPTIONS['kamehameha']]:
            self.assertNotIn('ameha', text)                               # nothing trademarked in the interface
        self.assertEqual(GUIDES['kamehameha'].title, 'Onda de energia')
        self.assertTrue(EnergyWaveEffect.action)
        self.assertFalse(EnergyWaveEffect.persistent)

    def test_the_effect_fits_the_generic_interface_of_every_catalog_effect(self):
        live, subject = scene(320, 180)
        effect = EFFECTS['kamehameha'](subject, True, 10)
        self.assertGreater(effect.duration, 1.1)
        self.assertLess(effect.duration, 1.7)
        self.assertEqual(effect.render(live, live, 10 + effect.duration * .4).shape, live.shape)


class WaveEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live, cls.subject = scene()
        cls.ball = (900., 520., 110.)

    def make(self, **kwargs):
        kwargs.setdefault('ball', self.ball)
        return EnergyWaveEffect(self.subject, False, 10, **kwargs)

    def test_it_starts_and_ends_on_the_untouched_live_frame_bit_for_bit(self):
        for subject in (self.subject, None):
            with self.subTest(subject=subject is not None):
                effect = EnergyWaveEffect(subject, False, 10, ball=self.ball, shape=self.live.shape[:2])
                before = effect.render(self.live, None, 10)
                after = effect.render(self.live, None, 10 + effect.duration + .001)
                np.testing.assert_array_equal(before, self.live)
                np.testing.assert_array_equal(after, self.live)
                self.assertFalse(effect.finished(10 + effect.duration - .01))
                self.assertTrue(effect.finished(10 + effect.duration + .001))
                self.assertIsNot(after, self.live)

    def test_the_person_is_never_hidden_and_the_background_plate_is_never_needed(self):
        weird = np.full_like(self.live, 7)
        for hidden in (True, False):
            effect = EnergyWaveEffect(self.subject, hidden, 10, ball=self.ball)
            first = [effect.render(self.live, background, 10 + t) for t in (.3, .8, 1.2) for background in (None, weird)]
            self.assertTrue(all(np.array_equal(first[i], first[i + 1]) for i in (0, 2, 4)))
        a = EnergyWaveEffect(self.subject, True, 10, ball=self.ball).render(self.live, None, 10.5)
        b = EnergyWaveEffect(self.subject, False, 10, ball=self.ball).render(self.live, None, 10.5)
        np.testing.assert_array_equal(a, b)

    def test_the_beam_leaves_the_head_alone_whatever_side_the_hands_are_on(self):
        head = np.zeros(self.live.shape[:2], bool)
        head[40:200, 520:760] = True
        for x, y in ((900, 520), (380, 520), (650, 600), (1100, 300), (200, 650), (650, 450)):
            with self.subTest(hands=(x, y)):
                effect = self.make(ball=(x, y, 110.))
                for t in (.2, .45, .8):
                    frame = effect.render(self.live, None, 10 + t)
                    shifted_live = shifted(self.live, *effect.shake(t))
                    strong = np.abs(frame.astype(int) - shifted_live.astype(int)).max(axis=2) > 70
                    self.assertLess(strong[head].mean(), .05, (t, effect.ux, effect.uy))

    def test_the_beam_is_big_and_blue_white_and_the_person_stays_visible(self):
        effect = self.make()
        frame = effect.render(self.live, None, 10.5)
        diff = changed(frame, self.live, 25)
        self.assertGreater(diff.mean(), .12)                              # a big beam: more than 12 % of the picture
        lit = frame[diff]
        self.assertGreater(float(lit[:, 0].mean()), float(lit[:, 2].mean()) + 20)      # blue dominates (BGR)
        self.assertGreaterEqual(int(frame.max()), 250)                                  # white-hot core
        person = self.subject.mask > .9
        core = cv2.erode(person.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        covered = np.abs(frame.astype(int) - self.live.astype(int)).max(axis=2)[core]
        self.assertLess(float((covered > 120).mean()), .35)               # most of the person is still plainly there

    def test_the_picture_outside_the_beam_returns_exactly_once_the_shake_has_settled(self):
        effect = self.make()
        x0, y0, x1, y1 = effect.rect
        outside = np.ones(self.live.shape[:2], bool)
        outside[y0:y1, x0:x1] = False
        for t in (1.0, 1.2, 1.4):
            frame = effect.render(self.live, None, 10 + t)
            self.assertEqual(effect.shake(t), (0, 0))
            np.testing.assert_array_equal(frame[outside], self.live[outside])

    def test_flash_peaks_briefly_and_the_shake_is_a_few_pixels_that_decay(self):
        effect = self.make()
        flash = [effect.envelope(t / 100)['flash'] for t in range(0, 150)]
        self.assertAlmostEqual(max(flash), 1.0, delta=.02)
        self.assertLess(.03, flash.index(max(flash)) / 100 < .08)
        self.assertLess(effect.envelope(.4)['flash'], .01)
        shakes = [max(abs(v) for v in effect.shake(t / 60)) for t in range(0, 90)]
        self.assertLessEqual(max(shakes), 8)
        self.assertGreaterEqual(max(shakes), 3)
        self.assertEqual(max(shakes[60:]), 0)                              # settled well before the end
        self.assertGreater(effect.envelope(.1)['shake'], effect.envelope(.6)['shake'])

    def test_the_beam_dissipates_into_particles_and_fades_out(self):
        effect = self.make()
        amount = {}
        for t in (.2, .5, .9, 1.15, 1.3, 1.45):
            frame = effect.render(self.live, None, 10 + t)
            amount[t] = float(np.abs(frame.astype(int) - shifted(self.live, *effect.shake(t)).astype(int)).mean())
        self.assertGreater(amount[.5], amount[1.15])
        self.assertGreater(amount[1.15], amount[1.3])
        self.assertGreater(amount[1.3], amount[1.45])
        self.assertLess(amount[1.45], .6)
        self.assertGreater(amount[1.3], 0)                                 # embers still drifting

    def test_dark_rooms_glow_and_bright_rooms_do_not_blow_out(self):
        for level, name in ((20, 'dark'), (235, 'bright')):
            live, subject = scene(level=level)
            effect = EnergyWaveEffect(subject, False, 10, ball=self.ball)
            frame = effect.render(live, None, 10.45)
            diff = changed(frame, live, 20)
            self.assertGreater(diff.mean(), .08, name)
            if name == 'bright':
                # additive light on a white wall would vanish; the body of the beam keeps its colour
                lit = frame[diff]
                self.assertLess(float(np.percentile(lit[:, 2], 20)), 190)
                self.assertGreater(float(lit[:, 0].mean()) - float(lit[:, 2].mean()), 10)
            else:
                self.assertGreater(float(frame[diff][:, 0].mean()), 100)

    def test_robust_for_odd_hands_edges_and_missing_data(self):
        for ball in ((5., 5., 20.), (1275., 715., 400.), (640., 360., 1.), (-50., 900., 80.), (math.nan, 3., 5.), None):
            with self.subTest(ball=ball):
                effect = self.make(ball=ball)
                for t in (.05, .3, .7, 1.1):
                    frame = effect.render(self.live, None, 10 + t)
                    self.assertEqual(frame.shape, self.live.shape)
                    self.assertEqual(frame.dtype, np.uint8)
                    self.assertTrue(effect.rect[0] >= 0 and effect.rect[1] >= 0)
                    self.assertTrue(effect.rect[2] <= 1280 and effect.rect[3] <= 720)
        np.testing.assert_array_equal(self.make(ball=None).render(self.live, None, 10.4),
                                      self.make(ball=(math.nan, 0, 0)).render(self.live, None, 10.4))

    def test_does_not_mutate_inputs_and_is_deterministic(self):
        live, mask = self.live.copy(), self.subject.mask.copy()
        a = self.make().render(self.live, None, 10.5)
        b = self.make().render(self.live, None, 10.5)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(self.live, live)
        np.testing.assert_array_equal(self.subject.mask, mask)

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            EnergyWaveEffect(Silhouette(10, self.live, np.full(self.live.shape[:2], np.nan, np.float32)), False, 10)
        with self.assertRaises(ValueError):
            EnergyWaveEffect(None, False, 10)
        effect = self.make()
        with self.assertRaises(ValueError):
            effect.render(self.live[:100], None, 10.5)

    def test_it_works_on_small_and_vga_frames_without_a_silhouette(self):
        for w, h in ((320, 180), (640, 480)):
            effect = EnergyWaveEffect(None, False, 10, ball=(w * .7, h * .7, h * .12), shape=(h, w))
            live = np.full((h, w, 3), 90, np.uint8)
            self.assertTrue(np.any(effect.render(live, None, 10.4) != live))

    def test_frame_cost_stays_within_the_per_frame_budget(self):
        effect = self.make()
        costs = []
        for i in range(1, 30):
            best = 1e9
            for _ in range(3):
                start = perf_counter()
                effect.render(self.live, None, 10 + effect.duration * i / 30)
                best = min(best, perf_counter() - start)
            costs.append(best * 1000)
        self.assertLess(median(costs), 20)             # generous for a loaded box; the real target is ~4-8 ms


class ChargeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live, cls.subject = scene()

    def charge(self, level=1.0, ball=(900., 540., 110.), frames=40, subject=None, live=None):
        live = self.live if live is None else live
        fx = EnergyCharge()
        out = live
        for i in range(frames):
            now = 100 + i / 30
            fx.update(now, ball, level, True, subject)
            out = fx.render(live, now)
        return fx, out, 100 + (frames - 1) / 30

    def test_inactive_overlay_is_the_untouched_live_frame(self):
        fx = EnergyCharge()
        self.assertFalse(fx.active(1))
        frame = fx.render(self.live, 1)
        np.testing.assert_array_equal(frame, self.live)
        self.assertIsNot(frame, self.live)

    def test_the_ball_sits_between_the_palms_and_is_white_hot_in_the_middle(self):
        fx, frame, _ = self.charge()
        self.assertTrue(fx.active(100.5))
        diff = changed(frame, self.live, 30)
        ys, xs = np.nonzero(diff)
        self.assertAlmostEqual(float(xs.mean()), 900, delta=70)
        self.assertAlmostEqual(float(ys.mean()), 540, delta=70)
        self.assertGreaterEqual(int(frame[535:545, 895:905].min()), 235)
        ring = frame[470:610, 830:970].reshape(-1, 3).astype(int)
        self.assertGreater(float(ring[:, 0].mean()), float(ring[:, 2].mean()) + 15)    # cyan/blue glow

    def test_it_grows_with_the_charge_and_gets_a_boost_at_full_charge(self):
        sizes = {}
        for level in (.15, .5, 1.0):
            fx, frame, _ = self.charge(level=level, frames=60)
            sizes[level] = int(changed(frame, self.live, 30).sum())
        self.assertLess(sizes[.15], sizes[.5])
        self.assertLess(sizes[.5], sizes[1.0])
        self.assertGreater(sizes[1.0], 2 * sizes[.15])

    def test_it_follows_the_hands_smoothly_between_updates(self):
        fx, _, now = self.charge(frames=30)
        fx.update(now + .033, (500., 300., 110.), 1.0, True)
        fx.render(self.live, now + .033)
        x1 = fx.ball[0]
        self.assertLess(x1, 900)
        self.assertGreater(x1, 500)                                      # moved part of the way, not a jump
        for i in range(2, 40):
            fx.update(now + i * .033, (500., 300., 110.), 1.0, True)
            fx.render(self.live, now + i * .033)
        self.assertAlmostEqual(fx.ball[0], 500, delta=15)

    def test_it_fizzles_out_when_the_pose_is_dropped_and_is_gone_afterwards(self):
        fx, frame, now = self.charge()
        fx.update(now + .033, None, 0.0, False)
        self.assertTrue(fx.active(now + .1))
        self.assertFalse(fx.charging)
        fizzling = fx.render(self.live, now + .2)
        self.assertTrue(np.any(fizzling != self.live))
        self.assertLess(changed(fizzling, self.live, 30).sum(), changed(frame, self.live, 30).sum())
        self.assertFalse(fx.active(now + .033 + fx.FIZZLE + .01))
        np.testing.assert_array_equal(fx.render(self.live, now + .6), self.live)
        fx.update(now + .7, None, 0.0, False)
        self.assertIsNone(fx.ball)

    def test_charging_again_while_it_fizzles_brings_the_ball_back(self):
        fx, _, now = self.charge()
        fx.update(now + .033, None, 0.0, False)
        fx.update(now + .1, (905., 545., 110.), 1.0, True)
        self.assertTrue(fx.charging)
        self.assertGreater(changed(fx.render(self.live, now + .12), self.live, 30).sum(), 3000)

    def test_light_stays_near_the_hands_without_a_silhouette_and_near_the_person_with_one(self):
        _, frame, _ = self.charge(subject=None)
        x, y = 900, 540
        far = np.ones(self.live.shape[:2], bool)
        reach = int(4.6 * 110 * .95) + 12
        far[max(0, y - reach):y + reach, max(0, x - reach):x + reach] = False
        np.testing.assert_array_equal(frame[far], self.live[far])
        _, framed, _ = self.charge(subject=self.subject)
        self.assertTrue(np.any(framed[far] != self.live[far]))             # the person takes a faint blue cast
        person = self.subject.mask > .9
        self.assertGreater(float(framed[person & far][:, 0].mean()), float(self.live[person & far][:, 0].mean()) + 2)
        background = (self.subject.mask < .01) & far
        outside = cv2.dilate((self.subject.mask > .01).astype(np.uint8), np.ones((120, 120), np.uint8)) == 0
        np.testing.assert_array_equal(framed[background & outside], self.live[background & outside])

    def test_a_faint_aura_hugs_the_silhouette_only_at_full_charge(self):
        rim = cv2.dilate((self.subject.mask > .5).astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
        rim &= self.subject.mask < .02
        rim[:, 780:] = False                                               # away from the ball itself
        amounts = {}
        for level in (.3, 1.0):
            _, frame, _ = self.charge(level=level, subject=self.subject, frames=60)
            amounts[level] = float(np.abs(frame[rim].astype(int) - self.live[rim].astype(int)).mean())
        self.assertGreater(amounts[1.0], amounts[.3] + .5)
        self.assertLess(amounts[1.0], 40)                                  # faint, not a sticker outline

    def test_bright_rooms_do_not_blow_out_and_edges_and_nans_are_safe(self):
        live, _ = scene(level=240)
        _, frame, _ = self.charge(live=live)
        lit = changed(frame, live, 20)
        self.assertGreater(int(lit.sum()), 3000)
        self.assertLess(float(np.percentile(frame[lit][:, 2], 10)), 215)    # the blue body still reads on white
        for ball in ((2., 2., 60.), (1278., 718., 300.), (640., 360., 2.), (-100., 900., 80.)):
            fx, frame, _ = self.charge(ball=ball, frames=12)
            self.assertEqual(frame.shape, self.live.shape)
        fx = EnergyCharge()
        fx.update(1, (math.nan, 1, 1), 1.0, True)
        self.assertFalse(fx.active(1))

    def test_inputs_are_not_mutated_and_frames_are_deterministic(self):
        before = self.live.copy()
        _, a, now = self.charge()
        fx2, b, _ = self.charge()
        np.testing.assert_array_equal(self.live, before)
        np.testing.assert_array_equal(a, b)

    def test_frame_cost_at_720p(self):
        fx, _, now = self.charge(subject=self.subject, frames=20)
        costs = []
        for i in range(30):
            fx.update(now + i / 30, (900. + i, 540., 120.), 1.0, True, self.subject)
            best = 1e9
            for _ in range(3):
                start = perf_counter()
                fx.render(self.live, now + i / 30)
                best = min(best, perf_counter() - start)
            costs.append(best * 1000)
        self.assertLess(median(costs), 20)


if __name__ == '__main__':
    unittest.main()
