"""Spirit bomb gesture: both hands raised above the head charge it, bringing the arms down throws it."""
import unittest

from sumi.gesture_guides import GUIDES
from sumi.recognition import GestureRecognizer, SPIRIT_CHARGE_SECONDS, SPIRIT_MIN_CHARGE, spirit_pose
from tests.test_wave_gesture import FACE, cupped, hand21

MODE = 'genkidama'
DT = 1/30


def raised(spread=180, y=70, palm=70):
    """Both arms up: open hands above the head, one each side of its centre (x = 150)."""
    return [hand21((150-spread/2, y), 90, palm, 4.0), hand21((150+spread/2, y), 90, palm, 4.0)]


def lowered():
    """Arms brought down in front of the chest, hands open."""
    return [hand21((90, 420), 90, 70, 4.0), hand21((210, 420), 90, 70, 4.0)]


class SpiritPoseTests(unittest.TestCase):
    def test_both_open_hands_above_the_head_are_the_pose(self):
        for spread in (60, 180, 320):
            with self.subTest(spread=spread):
                self.assertTrue(spirit_pose(raised(spread), FACE))

    def test_hands_at_the_chest_or_a_single_raised_hand_are_not(self):
        self.assertFalse(spirit_pose(lowered(), FACE))
        self.assertFalse(spirit_pose(cupped(), FACE))
        self.assertFalse(spirit_pose(raised()[:1], FACE))

    def test_fists_above_the_head_are_not_the_pose(self):
        fists = [hand21((60, 70), 90, 70, 85.0), hand21((240, 70), 90, 70, 85.0)]
        self.assertFalse(spirit_pose(fists, FACE))

    def test_the_guide_is_an_illustrated_motion_gesture(self):
        guide = GUIDES[MODE]
        self.assertEqual(guide.kind, 'spirit')
        self.assertTrue(guide.motion)
        self.assertEqual(len(guide.steps), 3)
        self.assertEqual(guide.image, 'esfera.png')


class SpiritRecognizerTests(unittest.TestCase):
    def armed(self):
        recognizer = GestureRecognizer()
        for i in range(12):
            recognizer.update([], FACE, 10+i*DT, MODE)
        return recognizer, 10+12*DT

    def frames(self, recognizer, hands, start, seconds):
        results, t = [], start
        for _ in range(round(seconds/DT)):
            results.append(recognizer.update(hands, FACE, t, MODE))
            t += DT
        return results, t

    def charged(self, seconds=SPIRIT_CHARGE_SECONDS+.1):
        recognizer, t = self.armed()
        results, t = self.frames(recognizer, raised(), t, seconds)
        return recognizer, results, t

    def test_charge_grows_while_the_arms_are_up_and_the_ball_sits_above_the_hands(self):
        _, results, _ = self.charged()
        self.assertTrue(all(r.charging and not r.matched for r in results))
        charges = [r.charge for r in results]
        self.assertEqual(charges, sorted(charges))
        self.assertEqual(charges[-1], 1.0)
        ball = results[-1].ball
        self.assertIsNotNone(ball)
        self.assertAlmostEqual(ball.x, 150, delta=12)
        self.assertLess(ball.y, FACE.y)
        self.assertGreater(ball.size, 0)

    def test_bringing_the_arms_down_throws_once(self):
        recognizer, _, t = self.charged()
        results, _ = self.frames(recognizer, lowered(), t, .5)
        fired = [r for r in results if r.matched]
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].charge, 1.0)
        self.assertIsNotNone(fired[0].ball)
        self.assertFalse(any(r.charging for r in results[1:]))

    def test_arms_leaving_the_frame_after_a_full_charge_also_throw(self):
        recognizer, _, t = self.charged()
        results, _ = self.frames(recognizer, [], t, .6)
        self.assertEqual(sum(r.matched for r in results), 1)

    def test_a_short_charge_only_fizzles(self):
        recognizer, t = self.armed()
        _, t = self.frames(recognizer, raised(), t, SPIRIT_MIN_CHARGE*SPIRIT_CHARGE_SECONDS*.5)
        results, _ = self.frames(recognizer, lowered(), t, 1.5)
        self.assertFalse(any(r.matched for r in results))
        self.assertFalse(results[-1].charging)

    def test_a_brief_tracking_loss_keeps_the_ball(self):
        recognizer, _, t = self.charged(1.0)
        results, t = self.frames(recognizer, [], t, .15)
        self.assertTrue(all(r.charging and not r.matched for r in results))
        results, _ = self.frames(recognizer, raised(), t, .2)
        self.assertTrue(all(r.charging for r in results))

    def test_after_a_throw_the_arms_must_rest_before_charging_again(self):
        recognizer, _, t = self.charged()
        _, t = self.frames(recognizer, lowered(), t, .2)
        results, _ = self.frames(recognizer, raised(), t, .3)
        self.assertFalse(any(r.charging for r in results))

    def test_starting_with_the_arms_already_up_needs_a_rest_first(self):
        recognizer = GestureRecognizer()
        results, _ = self.frames(recognizer, raised(), 10, .5)
        self.assertFalse(any(r.charging for r in results))


if __name__ == '__main__':
    unittest.main()
