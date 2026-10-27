import unittest
from statistics import median
from time import perf_counter

import cv2
import numpy as np

from sumi.effect_catalog import EFFECTS, LABELS
from sumi.effects import Silhouette
from sumi.effects_ninja import KawarimiEffect, ShadowCloneEffect, log_sprite
from sumi.smoke import SmokePuff

KINDS = (KawarimiEffect, ShadowCloneEffect)


def scene(width=1280, height=720, cx=640):
    mask = np.zeros((height, width), np.float32)
    cv2.circle(mask, (cx, int(height * .35)), height // 9, 1, -1)
    cv2.ellipse(mask, (cx, int(height * .85)), (width // 7, int(height * .38)), 0, 0, 360, 1, -1)
    rng = np.random.default_rng(3)
    background = np.clip(rng.normal(120, 12, (height, width, 3)), 0, 255).astype(np.uint8)
    live = background.copy()
    live[mask > .5] = (200, 120, 60)
    return live, background, Silhouette(10, live, mask)


class NinjaEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live, cls.background, cls.subject = scene()

    def test_log_asset_loads_with_transparency(self):
        sprite = log_sprite()
        self.assertEqual(sprite.ndim, 3)
        self.assertEqual(sprite.shape[2], 4)
        self.assertGreater(sprite.shape[0], 100)
        self.assertGreater(float(sprite[:, :, 3].max()), 250)
        self.assertLess(float(sprite[:, :, 3].min()), 5)

    def test_catalog_wiring(self):
        self.assertIs(EFFECTS['puff'], KawarimiEffect)
        self.assertIs(EFFECTS['clones'], ShadowCloneEffect)
        self.assertEqual(LABELS['Kawarimi · tronco'], 'puff')
        self.assertEqual(LABELS['Clones de sombra'], 'clones')

    def test_kawarimi_endpoints_are_bit_exact_in_both_directions(self):
        for hidden in (True, False):
            with self.subTest(hidden=hidden):
                effect = KawarimiEffect(self.subject, hidden, 10)
                first = effect.render(self.live, self.background, 10)
                last = effect.render(self.live, self.background, 10 + effect.duration + .001)
                np.testing.assert_array_equal(first, self.live if hidden else self.background)
                np.testing.assert_array_equal(last, self.background if hidden else self.live)
                self.assertTrue(effect.finished(10 + effect.duration + .001))

    def test_clones_start_from_live_end_on_live_and_join_seamlessly_to_the_steady_state(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        np.testing.assert_array_equal(on.render(self.live, self.background, 10), self.live)
        end = 10 + on.duration + .001
        steady = on.render_steady(self.live, self.background, end)
        np.testing.assert_array_equal(on.render(self.live, self.background, end), steady)
        self.assertTrue(on.finished(end))
        self.assertTrue(np.any(steady != self.live))
        off = ShadowCloneEffect(self.subject, False, end, carry=on)
        np.testing.assert_array_equal(off.render(self.live, self.background, end), steady)
        np.testing.assert_array_equal(off.render(self.live, self.background, end + off.duration + .001), self.live)
        self.assertTrue(off.finished(end + off.duration + .001))

    def test_steady_clones_keep_the_person_untouched_and_never_use_the_background(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        core = cv2.erode((self.subject.mask > .95).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        weird = np.full_like(self.background, 7)
        for background in (self.background, weird, None):
            frame = on.render_steady(self.live, background, 12)
            np.testing.assert_array_equal(frame[core], self.live[core])
            self.assertTrue(np.any(frame != self.live))

    def test_clones_follow_the_person_with_a_lag(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        active = [spec for spec in on.specs if spec['level'] <= on.level]
        before = [(spec['sx'], spec['sy']) for spec in active]
        live2, bg2, subject2 = scene(cx=500)
        subject2 = Silhouette(11, subject2.frame, subject2.mask)
        on.render_steady(self.live, self.background, 11.0)
        on.feed(subject2)
        on.render_steady(live2, bg2, 11.05)      # the clones still show the older cutouts
        early = [spec['sx'] for spec in active]
        for i in range(40):
            on.render_steady(live2, bg2, 11.1 + i * .033)
        late = [spec['sx'] for spec in active]
        for (x0, _), a, b in zip(before, early, late):
            self.assertLess(abs(a - x0), abs(b - x0))
            self.assertLess(b, x0 - 50)

    def test_frames_are_deterministic_typed_and_leave_inputs_alone(self):
        for kind in KINDS:
            for hidden in (True, False):
                with self.subTest(effect=kind.__name__, hidden=hidden):
                    live, background = self.live.copy(), self.background.copy()
                    a = kind(self.subject, hidden, 10)
                    b = kind(self.subject, hidden, 10)
                    if kind is ShadowCloneEffect and not hidden:
                        a, b = [ShadowCloneEffect(self.subject, False, 10, carry=ShadowCloneEffect(self.subject, True, 9)) for _ in range(2)]
                    for fraction in (.1, .3, .55, .8, .95):
                        now = 10 + fraction * a.duration
                        x, y = a.render(live, background, now), b.render(live, background, now)
                        np.testing.assert_array_equal(x, y)
                        self.assertEqual((x.shape, x.dtype), (self.live.shape, np.uint8))
                    np.testing.assert_array_equal(live, self.live)
                    np.testing.assert_array_equal(background, self.background)

    def test_pixels_outside_the_declared_region_are_background(self):
        for kind in KINDS:
            for hidden in (True, False):
                effect = kind(self.subject, hidden, 10)
                left, top, right, bottom = effect.region
                outside = np.ones(self.live.shape[:2], bool)
                outside[top:bottom, left:right] = False
                for fraction in np.linspace(.05, .95, 10):
                    with self.subTest(effect=kind.__name__, hidden=hidden, at=fraction):
                        frame = effect.render(self.live, self.background, 10 + fraction * effect.duration)
                        np.testing.assert_array_equal(frame[outside], self.background[outside])

    def test_small_person_leaves_most_of_the_frame_untouched(self):
        live, background, subject = scene(cx=250)
        for kind in KINDS:
            effect = kind(subject, True, 10)
            left, top, right, bottom = effect.region
            self.assertLess((right - left) * (bottom - top), live.shape[0] * live.shape[1] * .9)
            frame = effect.render(live, background, 10 + .3 * effect.duration)
            self.assertTrue(np.any(frame != background))

    def test_clones_stay_inside_the_frame_even_at_the_edge(self):
        for cx in (80, 640, 1200):
            live, background, subject = scene(cx=cx)
            effect = ShadowCloneEffect(subject, True, 10)
            for spec, person, alpha8, x, y in effect.layout(11):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + person.shape[1], live.shape[1])
            effect.render(live, background, 10 + .6)
            effect.render_steady(live, background, 12)

    def test_clones_are_smaller_than_the_original(self):
        effect = ShadowCloneEffect(self.subject, True, 10)
        self.assertEqual(effect.count, 2)
        self.assertTrue(all(spec['scale'] < 1 for spec in effect.specs))

    def test_log_leaves_the_frame_before_the_end_and_smoke_hides_the_person(self):
        effect = KawarimiEffect(self.subject, True, 10)
        late = effect.render(self.live, self.background, 10 + effect.duration - .05)
        self.assertLess(np.abs(late.astype(int) - self.background).max(), 4)
        early = effect.render(self.live, self.background, 10 + .12)
        core = self.subject.mask > .95
        self.assertGreater(float((early[core].astype(int).mean(axis=1) > 150).mean()), .8)

    def test_invalid_input_is_rejected(self):
        for kind in KINDS:
            with self.assertRaises(ValueError):
                kind(Silhouette(10, self.live, np.zeros(self.live.shape[:2], np.float32)), True, 10)
            effect = kind(self.subject, True, 10)
            with self.assertRaises(ValueError):
                effect.render(self.live[:10], self.background, 10.2)

    def test_smoke_has_volume_and_stays_bounded(self):
        puff = SmokePuff.disc((720, 1280), (640, 400), 60, 200, seed=1)
        frame = np.full((720, 1280, 3), 90, np.uint8)
        rect = puff.render_at(frame, .2)
        self.assertIsNotNone(rect)
        x0, y0, x1, y1 = puff.rect
        self.assertTrue(x0 <= rect[0] and y0 <= rect[1] and rect[2] <= x1 and rect[3] <= y1)
        self.assertLess((x1 - x0) * (y1 - y0), 1280 * 720 * .6)
        patch = frame[380:420, 600:680]
        self.assertGreater(float(patch.mean()), 150)
        self.assertGreater(float(frame[y0:y1, x0:x1].std()), 8)
        np.testing.assert_array_equal(frame[:y0], np.full_like(frame[:y0], 90))
        self.assertIsNone(puff.render_at(frame, 1.5))

    def test_render_cost_is_sane(self):
        for kind in KINDS:
            for hidden in (True, False):
                effect = kind(self.subject, hidden, 10)
                costs = []
                for fraction in np.linspace(.03, .97, 24):
                    start = perf_counter()
                    effect.render(self.live, self.background, 10 + fraction * effect.duration)
                    costs.append((perf_counter() - start) * 1000)
                with self.subTest(effect=kind.__name__, hidden=hidden):
                    self.assertLess(median(costs), 40)

    def test_waves_grow_two_four_eight_then_stop(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        self.assertEqual(on.count, 2)
        counts = [on.summon(None, 11 + i) for i in range(4)]
        self.assertEqual(counts, [4, 8, 0, 0])
        self.assertEqual(on.count, 8)
        frame = on.render_steady(self.live, self.background, 12.5)
        self.assertEqual(frame.shape, self.live.shape)

    def test_back_rows_are_smaller_darker_and_behind_the_earlier_ones(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        on.summon(None, 11)
        on.summon(None, 12)
        rows = {}
        for spec in on.specs:
            rows.setdefault(spec['row'], []).append(spec['scale'])
        self.assertLess(max(rows[1]), min(rows[0]))
        self.assertLess(max(rows[2]), min(rows[1]))
        order = [spec['row'] for spec in on.specs]
        self.assertEqual(order, sorted(order, reverse=True))      # farthest drawn first
        placed = on.layout(13)
        ys = {spec['row']: y + alpha8.shape[0] for spec, _, alpha8, _, y in placed}
        self.assertLess(ys[2], ys[0])                             # back rows stand higher

    def test_eight_clones_stay_inside_the_frame_and_never_cover_the_person(self):
        for cx in (80, 640, 1200):
            live, background, subject = scene(cx=cx)
            on = ShadowCloneEffect(subject, True, 10)
            on.summon(None, 11)
            on.summon(None, 12)
            for spec, person, alpha8, x, y in on.layout(14):
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + person.shape[1], live.shape[1])
            frame = on.render_steady(live, background, 14)
            core = cv2.erode((subject.mask > .95).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
            np.testing.assert_array_equal(frame[core], live[core])

    def test_close_up_back_rows_peek_out_above_the_shoulders(self):
        live, background, subject = scene(height=720)
        mask = np.zeros(live.shape[:2], np.float32)
        cv2.ellipse(mask, (640, 700), (560, 330), 0, 0, 360, 1, -1)      # body fills the frame
        cv2.circle(mask, (640, 250), 120, 1, -1)
        live = background.copy()
        live[mask > .5] = (200, 120, 60)
        on = ShadowCloneEffect(Silhouette(10, live, mask), True, 10)
        on.summon(None, 11)
        on.summon(None, 12)
        frame = on.render_steady(live, background, 14)
        outside = (mask < .05)
        changed = np.any(frame != live, axis=2) & outside
        self.assertGreater(int(changed[:480].sum()), 300)       # heads show above the shoulders

    def test_steady_state_with_eight_clones_is_cheap(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        on.summon(None, 11)
        on.summon(None, 12)
        costs = []
        for i in range(40):
            start = perf_counter()
            on.render_steady(self.live, self.background, 20 + i / 30)
            costs.append((perf_counter() - start) * 1000)
        self.assertLess(median(costs), 30)

    def test_steady_state_is_cheap(self):
        on = ShadowCloneEffect(self.subject, True, 10)
        costs = []
        for i in range(30):
            start = perf_counter()
            on.render_steady(self.live, self.background, 12 + i / 30)
            costs.append((perf_counter() - start) * 1000)
        self.assertLess(median(costs), 30)

    def test_creation_is_cheap(self):
        costs = []
        for _ in range(3):
            start = perf_counter()
            ShadowCloneEffect(self.subject, True, 10)
            KawarimiEffect(self.subject, True, 10)
            costs.append((perf_counter() - start) * 1000)
        self.assertLess(min(costs), 250)


if __name__ == '__main__':
    unittest.main()
