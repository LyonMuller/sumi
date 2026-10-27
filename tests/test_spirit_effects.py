"""Spirit bomb: the giant ball above the hands, the throw at the camera, and the live frame coming back."""
import queue
import unittest

import numpy as np

from sumi.effect_catalog import DESCRIPTIONS, EFFECTS, LABELS
from sumi.effects_spirit import SpiritBombEffect, SpiritCharge
from tests.test_wave_engine import WaveEngineTests

H, W = 180, 320


def frame():
    live = np.full((H, W, 3), 70, np.uint8)
    live[60:, 120:200] = (40, 90, 160)
    return live


class SpiritEffectTests(unittest.TestCase):
    def test_wired_as_a_charged_action_with_a_portuguese_label(self):
        self.assertIs(EFFECTS['genkidama'], SpiritBombEffect)
        self.assertTrue(SpiritBombEffect.action)
        self.assertEqual(LABELS['Esfera de energia'], 'genkidama')
        self.assertIn('braços', DESCRIPTIONS['genkidama'])

    def test_the_throw_grows_to_fill_the_frame_bursts_white_and_ends_on_the_live_frame(self):
        live = frame()
        fx = SpiritBombEffect(None, True, 10.0, ball=(160., 30., 40.), charge=1.0, shape=(H, W))
        self.assertFalse(fx.hidden_target)
        radii = [fx.flight(t)[2] for t in (0, .2, .4, fx.IMPACT)]
        self.assertEqual(radii, sorted(radii))
        self.assertGreater(radii[-1], max(H, W) / 2)
        burst = fx.render(live, None, 10.0 + fx.IMPACT)
        self.assertGreater(burst.mean(), 200)
        for t in (.05, .3, .7, 1.2, 1.9):
            out = fx.render(live, None, 10.0 + t)
            self.assertEqual(out.shape, live.shape)
        self.assertTrue(np.array_equal(fx.render(live, None, 10.0 + fx.duration), live))
        self.assertTrue(np.array_equal(fx.render(live, None, 9.0), live))

    def test_without_hands_the_ball_starts_above_the_head(self):
        fx = SpiritBombEffect(None, True, 0.0, shape=(H, W))
        self.assertLess(fx.my, H * .3)

    def test_the_charge_draws_a_ball_and_fizzles_when_dropped(self):
        live = frame()
        fx = SpiritCharge()
        for i in range(30):
            fx.update(1 + i / 30, (160., 30., 40.), min(1.0, i / 20), True)
            out = fx.render(live, 1 + i / 30)
        self.assertGreater(np.abs(out.astype(int) - live).sum(), 0)
        self.assertGreater(out[30, 160].mean(), live[30, 160].mean() + 60)
        fx.update(2.1, None, 0.0, False)
        fx.update(3.0, None, 0.0, False)
        self.assertTrue(np.array_equal(fx.render(live, 3.0), live))


class SpiritEngineTests(WaveEngineTests):
    def test_raising_the_arms_charges_and_lowering_throws_with_its_own_sounds(self):
        ball, fire = (160., 30., 40.), (160., 30., 40.)
        def hands(call):
            if 5 <= call < 70:
                return True, min(1.0, (call - 5) / 50), ball, False
            if call == 70:
                return False, 1.0, fire, True
            return None
        engine, live, sent, states, _ = self.run_engine({}, frames=220, hands=hands, effect='genkidama')
        self.assertFalse(any(state[0] for state in states))
        self.assertTrue(any('Reunindo energia' in state[3] for state in states))
        firing = [i for i, state in enumerate(states) if state[1] == 'teleporting']
        self.assertGreater(len(firing), 40)
        self.assertTrue(any(states[i][3] == 'Esfera lançada!' for i in firing))
        np.testing.assert_array_equal(sent[-1], live)
        events = []
        while True:
            try: events.append(engine.sounds.get_nowait())
            except queue.Empty: break
        self.assertIn(('loop', 'genkidama-charge'), events)
        self.assertIn(('play', 'genkidama-fire'), events)
        self.assertIn(('stop', 'genkidama-charge'), events)
        self.assertNotIn(('loop', 'kamehameha-charge'), events)

    # The inherited energy-wave tests already run in their own module.
    for name in [n for n in dir(WaveEngineTests) if n.startswith('test_')]:
        locals()[name] = None
    del name


if __name__ == '__main__':
    unittest.main()
