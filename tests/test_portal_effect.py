import time
import unittest

import cv2
import numpy as np

from sumi.effects import Silhouette
from sumi.effects_portal import PortalEffect


def make_scene(width=1280, height=720, cx=520):
    mask = np.zeros((height, width), np.float32)
    cv2.circle(mask, (cx, height // 3), height // 9, 1, -1)
    cv2.ellipse(mask, (cx, int(height * 0.78)), (height // 4, height // 3), 0, 0, 360, 1, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 1.5)
    background = np.full((height, width, 3), (170, 180, 175), np.uint8)
    background[:, ::7] = (150, 160, 158)
    live = background.copy()
    live[mask > 0.5] = (190, 110, 60)
    return live, background, Silhouette(10.0, live, mask)


class PortalEffectTests(unittest.TestCase):
    def setUp(self):
        self.live, self.background, self.subject = make_scene()

    def test_endpoints_are_exact_in_both_directions(self):
        for hidden in (True, False):
            with self.subTest(hidden=hidden):
                effect = PortalEffect(self.subject, hidden, 10.0)
                first = effect.render(self.live, self.background, 10.0)
                last = effect.render(self.live, self.background, 10.0 + effect.duration + 0.01)
                np.testing.assert_array_equal(first, self.live if hidden else self.background)
                np.testing.assert_array_equal(last, self.background if hidden else self.live)
                self.assertTrue(effect.finished(10.0 + effect.duration + 0.01))

    def test_shape_dtype_and_inputs_untouched(self):
        live, background = self.live.copy(), self.background.copy()
        effect = PortalEffect(self.subject, True, 10.0)
        for fraction in (0.1, 0.3, 0.55, 0.75, 0.85, 0.95):
            frame = effect.render(self.live, self.background, 10.0 + fraction * effect.duration)
            self.assertEqual(frame.shape, self.live.shape)
            self.assertEqual(frame.dtype, np.uint8)
        np.testing.assert_array_equal(self.live, live)
        np.testing.assert_array_equal(self.background, background)

    def test_deterministic(self):
        for hidden in (True, False):
            now = 10.0 + 0.5 * PortalEffect.duration
            a = PortalEffect(self.subject, hidden, 10.0)
            b = PortalEffect(self.subject, hidden, 10.0)
            a.render(self.live, self.background, 10.2)
            np.testing.assert_array_equal(a.render(self.live, self.background, now),
                                          b.render(self.live, self.background, now))

    def test_effect_changes_the_frame_and_stays_inside_its_roi(self):
        for hidden in (True, False):
            effect = PortalEffect(self.subject, hidden, 10.0)
            left, top, right, bottom = effect.box
            protected = np.ones(self.background.shape[:2], bool)
            protected[top:bottom, left:right] = False
            for fraction in (0.12, 0.4, 0.62, 0.8, 0.9):
                frame = effect.render(self.live, self.background, 10.0 + fraction * effect.duration)
                np.testing.assert_array_equal(frame[protected], self.background[protected])
                self.assertTrue(np.any(frame != self.background))

    def test_person_is_not_resampled_at_low_resolution(self):
        # Right after the effect starts the person must still be pixel-sharp.
        effect = PortalEffect(self.subject, True, 10.0)
        frame = effect.render(self.live, self.background, 10.0 + 0.05 * effect.duration)
        body = self.subject.mask > 0.99
        body[:, 600:] = False  # keep away from the portal
        np.testing.assert_allclose(frame[body].astype(int), self.live[body].astype(int), atol=4)

    def test_small_and_odd_frame_sizes(self):
        live, background, subject = make_scene(322, 181, cx=120)
        for hidden in (True, False):
            effect = PortalEffect(subject, hidden, 10.0)
            for fraction in (0.1, 0.5, 0.8, 0.95):
                frame = effect.render(live, background, 10.0 + fraction * effect.duration)
                self.assertEqual(frame.shape, live.shape)

    def test_portal_on_the_left_when_person_is_on_the_right(self):
        live, background, subject = make_scene(cx=950)
        effect = PortalEffect(subject, True, 10.0)
        self.assertLess(effect.c[0], 950)
        frame = effect.render(live, background, 10.0 + 0.4 * effect.duration)
        self.assertTrue(np.any(frame != background))

    def test_render_cost_smoke(self):
        start = time.perf_counter()
        effect = PortalEffect(self.subject, True, 10.0)
        init = time.perf_counter() - start
        costs = []
        for index in range(1, 34):
            start = time.perf_counter()
            effect.render(self.live, self.background, 10.0 + index / 30)
            costs.append(time.perf_counter() - start)
        self.assertLess(float(np.median(costs)), 0.040)
        self.assertLess(init, 0.250)


if __name__ == '__main__':
    unittest.main()
