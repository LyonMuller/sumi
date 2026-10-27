"""Geometry and timing of the energy wave: cupped hands at the side charge it, an open push fires it."""
import math
import unittest
from dataclasses import replace

from sumi.gesture import Face, Point
from sumi.gesture_guides import GUIDES
from sumi.recognition import (Ball, GestureRecognizer, charge_pose, finger_curl, palm_centre, push_pose, wave_ball,
                                      WAVE_CHARGE_SECONDS, WAVE_MIN_CHARGE)

FACE = Face(100, 100, 100, 160)          # centre x = 150, chin y = 260
MODE = 'kamehameha'


def hand21(wrist, degrees=90, palm=70, bend=38.0):
    """One hand with the fingers pointing at `degrees` (90 = up), each joint bent by `bend` degrees."""
    a = math.radians(degrees)
    u = (math.cos(a), -math.sin(a))
    v = (-u[1], u[0])
    points = [Point(*wrist) for _ in range(21)]
    seg = palm*.42
    for base, side, reach in ((5, -.30, 1.0), (9, 0.0, 1.0), (13, .27, .95), (17, .52, .88)):
        x, y = wrist[0]+u[0]*palm*reach+v[0]*palm*side, wrist[1]+u[1]*palm*reach+v[1]*palm*side
        angle = 0.0
        for joint in range(4):
            points[base+joint] = Point(x, y)
            c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            x, y = x+(u[0]*c-u[1]*s)*seg, y+(u[0]*s+u[1]*c)*seg
            angle += bend
    for joint, (along, across) in enumerate(((.3, -.35), (.5, -.6), (.75, -.75), (.95, -.8)), start=1):
        points[joint] = Point(wrist[0]+u[0]*palm*along+v[0]*palm*across, wrist[1]+u[1]*palm*along+v[1]*palm*across)
    return points


def cupped(x=330, y=420, degrees=90, palm=70, bend=38.0, gap=24):
    """Two cupped hands with their wrists `gap` apart."""
    return [hand21((x-gap/2, y), degrees, palm, bend), hand21((x+gap/2, y), degrees, palm, bend)]


def pushed(x=150, y=420, degrees=90, palm=70, gap=24):
    return cupped(x, y, degrees, palm, 0.0, gap)


def flat(hands, factor):
    return [[Point(p.x*factor, p.y*factor) for p in hand] for hand in hands]


class PoseTests(unittest.TestCase):
    def test_fixtures_have_the_curl_they_claim(self):
        self.assertAlmostEqual(finger_curl(hand21((0, 0), bend=0)), 1.0, places=2)
        self.assertLess(finger_curl(hand21((0, 0), bend=38)), .9)
        self.assertGreater(finger_curl(hand21((0, 0), bend=38)), .8)
        self.assertLess(finger_curl(hand21((0, 0), bend=80)), .6)

    def test_cupped_hands_beside_the_body_charge_on_either_side_and_in_any_direction(self):
        for x in (330, -30, 380, -80):                   # right and left of the face
            for degrees in (90, 45, 0, 270, 315):
                with self.subTest(x=x, degrees=degrees):
                    self.assertTrue(charge_pose(cupped(x, degrees=degrees), FACE))

    def test_charge_works_in_front_of_the_chest_and_up_to_the_mouth(self):
        for x in (150, 190, 110):
            for y in (330, 420, 700):
                with self.subTest(x=x, y=y):
                    self.assertTrue(charge_pose(cupped(x, y), FACE))
        self.assertTrue(charge_pose(cupped(x=150, y=300, degrees=60), FACE))

    def test_charge_tolerates_loose_curl_and_misaligned_hands(self):
        self.assertTrue(charge_pose(cupped(bend=22), FACE))
        self.assertTrue(charge_pose(cupped(bend=70), FACE))
        self.assertTrue(charge_pose([hand21((318, 420), 90), hand21((342, 420), 40)], FACE))   # 50 degrees apart
        self.assertTrue(charge_pose(cupped(gap=90), FACE))

    def test_charge_is_scale_invariant(self):
        big = Face(200, 200, 200, 320)
        self.assertTrue(charge_pose(flat(cupped(), 2), big))

    def test_relaxed_and_tighter_curls_both_count(self):
        for bend in (30, 38, 50, 65):
            with self.subTest(bend=bend):
                self.assertTrue(charge_pose(cupped(bend=bend), FACE), finger_curl(cupped(bend=bend)[0]))

    def test_charge_rejects_what_is_not_the_pose(self):
        near_misses = {
            'one hand': [cupped()[0]],
            'three hands': cupped() + [cupped()[0]],
            'flat open palms': cupped(bend=0),
            'fists': cupped(bend=95),
            'hands apart': cupped(gap=260),
            'at the mouth': cupped(x=150, y=240),
            'at face height': cupped(y=150),
            'above the head': cupped(y=-200),
            'far to the side': cupped(x=900),
            'hands pointing away from each other': [hand21((318, 420), 90), hand21((342, 420), 270)],
            'tiny hands': cupped(palm=8),
            'huge hands': cupped(palm=400),
            'one big, one small': [hand21((318, 420), 90, 70), hand21((342, 420), 90, 30)],
        }
        for name, hands in near_misses.items():
            with self.subTest(name):
                self.assertFalse(charge_pose(hands, FACE))

    def test_charge_rejects_garbage_input(self):
        self.assertFalse(charge_pose(cupped(), Face(100, 100, 10, 10)))
        self.assertFalse(charge_pose(cupped(), Face(math.nan, 100, 100, 160)))
        broken = cupped()
        broken[0][5] = Point(math.nan, 0)
        self.assertFalse(charge_pose(broken, FACE))
        self.assertFalse(charge_pose([], FACE))

    def test_push_needs_open_hands_together(self):
        self.assertTrue(push_pose(pushed(), FACE))
        self.assertTrue(push_pose(pushed(x=330), FACE))              # still at the side is fine
        self.assertTrue(push_pose(pushed(degrees=0), FACE))
        self.assertFalse(push_pose(cupped(bend=70, x=150), FACE))     # curled
        self.assertFalse(push_pose(pushed(gap=300), FACE))
        self.assertFalse(push_pose([pushed()[0]], FACE))
        self.assertFalse(push_pose(pushed(x=900), FACE))
        self.assertFalse(push_pose(pushed(y=-300), FACE))

    def test_ball_sits_between_the_palms_and_scales_with_them(self):
        hands = cupped(x=330, y=420, palm=70)
        ball = wave_ball(hands, FACE)
        self.assertIsInstance(ball, Ball)
        centres = [palm_centre(hand) for hand in hands]
        self.assertAlmostEqual(ball.x, (centres[0][0]+centres[1][0])/2, places=3)
        self.assertAlmostEqual(ball.y, (centres[0][1]+centres[1][1])/2, places=3)
        self.assertGreater(ball.x, hands[0][0].x)
        self.assertLess(ball.x, hands[1][0].x+60)
        self.assertLess(ball.y, 420)                                  # palms are above the wrists
        self.assertAlmostEqual(ball.size, 70, delta=1)
        self.assertIsNone(wave_ball(cupped(gap=400), FACE))


class SequenceTests(unittest.TestCase):
    DT = 1/30

    def armed(self):
        recognizer = GestureRecognizer()
        for i in range(12):
            recognizer.update([], FACE, 10+i*self.DT, MODE)
        return recognizer, 10+12*self.DT

    def run_frames(self, recognizer, hands, start, seconds):
        results, t = [], start
        for _ in range(round(seconds/self.DT)):
            results.append(recognizer.update(hands, FACE, t, MODE))
            t += self.DT
        return results, t

    def charged(self, seconds=WAVE_CHARGE_SECONDS+.1, **kwargs):
        recognizer, t = self.armed()
        results, t = self.run_frames(recognizer, cupped(**kwargs), t, seconds)
        return recognizer, results, t

    def test_the_guide_is_a_motion_gesture_with_a_three_step_illustrated_tutorial(self):
        guide = GUIDES[MODE]
        self.assertEqual(guide.kind, 'wave')
        self.assertTrue(guide.motion)
        self.assertEqual(len(guide.steps), 3)
        self.assertEqual(guide.image, 'onda.png')

    def test_charge_builds_over_about_a_second_and_a_half(self):
        _, results, _ = self.charged()
        self.assertTrue(all(r.charging and not r.matched for r in results))
        self.assertLess(results[0].charge, .1)
        self.assertAlmostEqual(results[round(.6/self.DT)].charge, .5, delta=.1)
        self.assertEqual(results[-1].charge, 1.0)
        self.assertEqual(results[-1].progress, results[-1].charge)
        charges = [r.charge for r in results]
        self.assertEqual(charges, sorted(charges))
        self.assertIsNotNone(results[-1].ball)

    def test_opening_the_hands_after_the_charge_fires_exactly_once_and_reports_the_muzzle(self):
        recognizer, _, t = self.charged()
        results, _ = self.run_frames(recognizer, pushed(x=330, palm=100), t, .5)
        fired = [r for r in results if r.matched]
        self.assertEqual(len(fired), 1)
        self.assertIs(results[0], fired[0])
        self.assertEqual(fired[0].charge, 1.0)
        self.assertAlmostEqual(fired[0].ball.x, wave_ball(pushed(x=330, palm=100), FACE).x, places=3)
        self.assertFalse(any(r.charging for r in results[1:]))

    def test_opening_in_place_without_moving_fires_in_front_of_the_chest(self):
        recognizer, _, t = self.charged(x=150)
        results, _ = self.run_frames(recognizer, pushed(x=150), t, .3)
        self.assertEqual(sum(r.matched for r in results), 1)

    def test_opening_a_single_hand_fires(self):
        recognizer, _, t = self.charged()
        results, _ = self.run_frames(recognizer, [pushed(x=330)[0]], t, .3)
        self.assertEqual(sum(r.matched for r in results), 1)

    def test_the_hands_may_open_apart_from_each_other(self):
        recognizer, _, t = self.charged()
        spread = [hand21((250, 420), 90, 70, 0.0), hand21((410, 420), 90, 70, 0.0)]
        results, _ = self.run_frames(recognizer, spread, t, .3)
        self.assertEqual(sum(r.matched for r in results), 1)

    def test_opening_up_to_a_second_after_the_last_charged_frame_still_fires(self):
        recognizer, _, t = self.charged()
        _, t = self.run_frames(recognizer, [], t, .7)
        results, _ = self.run_frames(recognizer, pushed(x=150), t, .2)
        self.assertEqual(sum(r.matched for r in results), 1)

    def test_losing_the_hands_after_a_full_charge_while_they_grow_fires(self):
        recognizer, _, t = self.charged()
        grow = []
        for palm in (74, 80, 88, 98):                                  # moving to the camera, still cupped
            grow.append(recognizer.update(cupped(palm=palm), FACE, t, MODE))
            t += self.DT
        self.assertFalse(any(r.matched for r in grow))
        lost, _ = self.run_frames(recognizer, [], t, .3)
        self.assertEqual(sum(r.matched for r in lost), 1)
        self.assertTrue(lost[0].matched)
        self.assertGreater(lost[0].charge, .99)
        self.assertIsNotNone(lost[0].ball)

    def test_losing_the_hands_without_growth_or_before_a_full_charge_is_quiet(self):
        recognizer, _, t = self.charged()
        lost, _ = self.run_frames(recognizer, [], t, 1.2)
        self.assertFalse(any(r.matched for r in lost))
        recognizer, _, t = self.charged(seconds=.6)
        for palm in (74, 80, 88, 98):
            recognizer.update(cupped(palm=palm), FACE, t, MODE)
            t += self.DT
        lost, _ = self.run_frames(recognizer, [], t, 1.2)
        self.assertFalse(any(r.matched for r in lost))

    def test_lowering_curled_hands_out_of_the_frame_cancels_quietly(self):
        recognizer, _, t = self.charged()
        results, t = self.run_frames(recognizer, [], t, 1.5)
        self.assertFalse(any(r.matched for r in results))
        self.assertFalse(results[-1].charging)
        late, _ = self.run_frames(recognizer, pushed(x=150), t, .3)
        self.assertFalse(any(r.matched for r in late))

    def test_curled_hands_staying_below_the_mouth_never_fire_by_themselves(self):
        recognizer, _, t = self.charged()
        results, _ = self.run_frames(recognizer, cupped(y=560), t, 1.5)
        self.assertFalse(any(r.matched for r in results))
        self.assertTrue(all(r.charging for r in results))

    def test_dropping_the_hands_without_a_push_fizzles_and_never_fires(self):
        recognizer, _, t = self.charged()
        results, t = self.run_frames(recognizer, [], t, 1.5)
        self.assertFalse(any(r.matched for r in results))
        self.assertTrue(results[0].charging)                           # a flicker keeps the ball for a moment ...
        self.assertTrue(results[round(.3/self.DT)].charging)
        self.assertFalse(results[round(.7/self.DT)].charging)           # ... then it fizzles
        self.assertEqual(results[-1].charge, 0.0)
        late, _ = self.run_frames(recognizer, pushed(x=150), t, .3)
        self.assertFalse(any(r.matched for r in late))

    def test_an_opening_that_comes_too_late_does_not_fire(self):
        recognizer, _, t = self.charged()
        _, t = self.run_frames(recognizer, [], t, 1.2)
        results, _ = self.run_frames(recognizer, pushed(x=150), t, .4)
        self.assertFalse(any(r.matched for r in results))

    def test_a_push_with_almost_no_charge_does_not_fire(self):
        recognizer, _, t = self.charged(seconds=WAVE_MIN_CHARGE*WAVE_CHARGE_SECONDS-.15)
        results, _ = self.run_frames(recognizer, pushed(x=150), t, .3)
        self.assertFalse(any(r.matched for r in results))

    def test_a_short_flicker_of_the_pose_keeps_the_charge(self):
        recognizer, _, t = self.charged(seconds=.6)
        flicker, t = self.run_frames(recognizer, [], t, .3)
        self.assertTrue(all(r.charging for r in flicker))
        results, _ = self.run_frames(recognizer, cupped(), t, .5)
        self.assertEqual(results[-1].charge, 1.0)                      # charging resumed from the first frame
        self.assertGreater(results[0].charge, .5)

    def test_charge_survives_losing_one_hand_while_the_other_stays_below_the_mouth(self):
        recognizer, _, t = self.charged(seconds=.6)
        one, t = self.run_frames(recognizer, [cupped()[0]], t, 1.0)
        self.assertTrue(all(r.charging and not r.matched for r in one))
        self.assertEqual(one[-1].charge, 1.0)                          # kept growing on one hand
        self.assertIsNotNone(one[-1].ball)
        flicker = [cupped(), [cupped()[1]], cupped(), [cupped()[0]], cupped()]
        for hands in flicker:
            r = recognizer.update(hands, FACE, t, MODE)
            t += self.DT
            self.assertTrue(r.charging)
        fired, _ = self.run_frames(recognizer, pushed(x=330), t, .3)
        self.assertEqual(sum(r.matched for r in fired), 1)

    def test_one_hand_alone_cannot_start_a_charge_and_the_hint_says_so(self):
        recognizer, t = self.armed()
        results, _ = self.run_frames(recognizer, [cupped()[0]], t, 1.0)
        self.assertFalse(any(r.charging for r in results))
        self.assertIn('uma mão', results[-1].hint)

    def test_hints_guide_the_gesture(self):
        recognizer, t = self.armed()
        self.assertIn('em concha', recognizer.update(cupped(gap=300), FACE, t, MODE).hint)
        recognizer, t = self.armed()
        results, t = self.run_frames(recognizer, cupped(), t, .3)
        self.assertIn('Carregando', results[-1].hint)
        results, _ = self.run_frames(recognizer, cupped(), t, 1.2)
        self.assertIn('Carga completa', results[-1].hint)
        self.assertIn('Abra as mãos', results[-1].hint)

    def test_a_slow_frame_does_not_kill_the_charge(self):
        recognizer, _, t = self.charged(seconds=.6)
        r = recognizer.update(cupped(), FACE, t+.45, MODE)
        self.assertTrue(r.charging)
        self.assertGreater(r.charge, .5)

    def test_a_cupped_pair_that_wanders_slowly_is_not_a_shot(self):
        recognizer, results, t = self.charged(seconds=.5)
        drift = []
        for step in range(40):                                         # 1.3 s sliding slowly towards the centre
            drift.append(recognizer.update(cupped(x=330-step*2.2, palm=70+step*.15), FACE, t, MODE))
            t += self.DT
        self.assertFalse(any(r.matched for r in drift))

    def test_hands_up_at_face_height_do_nothing(self):
        recognizer, t = self.armed()
        results, t = self.run_frames(recognizer, cupped(y=150), t, 2.0)
        self.assertFalse(any(r.matched or r.charging for r in results))

    def test_after_a_shot_the_hands_must_be_lowered_before_charging_again(self):
        recognizer, _, t = self.charged()
        results, t = self.run_frames(recognizer, pushed(x=150), t, .5)
        self.assertEqual(sum(r.matched for r in results), 1)
        again, t = self.run_frames(recognizer, cupped(), t, 1.5)       # immediately charging again: ignored
        self.assertFalse(any(r.charging or r.matched for r in again))
        _, t = self.run_frames(recognizer, [], t, .5)                  # released
        retry, t = self.run_frames(recognizer, cupped(), t, 1.4)
        self.assertTrue(all(r.charging for r in retry))
        fired, _ = self.run_frames(recognizer, pushed(x=150), t, .3)
        self.assertEqual(sum(r.matched for r in fired), 1)

    def test_a_pose_held_since_start_up_needs_a_release_first(self):
        recognizer = GestureRecognizer()
        results, t = self.run_frames(recognizer, cupped(), 10, 2.0)
        self.assertFalse(any(r.charging for r in results))
        _, t = self.run_frames(recognizer, [], t, .5)
        results, _ = self.run_frames(recognizer, cupped(), t, .3)
        self.assertTrue(all(r.charging for r in results))

    def test_stale_data_and_a_lost_face_drop_the_charge(self):
        recognizer, _, t = self.charged()
        stale = recognizer.update(pushed(x=150), FACE, t+1.0, MODE)     # a stalled camera does not complete a shot
        self.assertFalse(stale.matched)
        recognizer, _, t = self.charged()
        lost = recognizer.update(cupped(), None, t, MODE)
        self.assertFalse(lost.charging)
        after = recognizer.update(pushed(x=150), FACE, t+self.DT, MODE)
        self.assertFalse(after.matched)

    def test_switching_to_another_effect_clears_the_charge(self):
        recognizer, _, t = self.charged()
        recognizer.update(cupped(), FACE, t, 'portal')
        result = recognizer.update(pushed(x=150), FACE, t+self.DT, MODE)
        self.assertFalse(result.matched)

    def test_other_gestures_are_untouched_by_the_new_fields(self):
        recognizer = GestureRecognizer()
        result = recognizer.update(cupped(), FACE, 1.0, 'portal')
        self.assertFalse(result.charging)
        self.assertEqual(result.charge, 0.0)
        self.assertIsNone(result.ball)

    def test_mirrored_scene_behaves_the_same(self):
        mirror = lambda hands: [[replace(p, x=300-p.x) for p in hand] for hand in hands]
        recognizer, t = self.armed()
        results, t = self.run_frames(recognizer, mirror(cupped(x=330)), t, 1.3)
        self.assertEqual(results[-1].charge, 1.0)
        fired, _ = self.run_frames(recognizer, mirror(pushed(x=150)), t, .3)
        self.assertEqual(sum(r.matched for r in fired), 1)


if __name__ == '__main__':
    unittest.main()
