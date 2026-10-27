import math
import unittest
from dataclasses import replace
import numpy as np
from sumi.gesture import Face, HoldGate, Point, goku_pose
from sumi.scene import Scene


def hand() -> list[Point]:
    points = [Point(150, 200) for _ in range(21)]
    points[0] = Point(150, 250)
    for base, x in ((5, 145), (9, 155)):
        for offset, y in enumerate((195, 165, 135, 110)):
            points[base + offset] = Point(x, y)
    for base, x in ((13, 165), (17, 175)):
        for offset, y in enumerate((200, 175, 190, 215)):
            points[base + offset] = Point(x, y)
    return points

class GestureTests(unittest.TestCase):
    face = Face(100, 100, 100, 160)
    def test_pose_and_mirror(self):
        self.assertTrue(goku_pose(hand(), self.face))
        self.assertTrue(goku_pose([Point(300-p.x, p.y) for p in hand()], self.face))
    def test_scale_invariance(self):
        self.assertTrue(goku_pose([Point(p.x*2, p.y*2) for p in hand()], Face(200,200,200,320)))
    def test_no_face_or_invalid_points(self):
        for points, face in ((hand(), None), ([], self.face), ([Point(0,0)]*21, self.face),
                             ([Point(math.nan,0)]*21,self.face)):
            self.assertFalse(goku_pose(points,face))
    def test_spread_fingers_rejected(self):
        points=hand(); points[8]=Point(115,110); points[12]=Point(185,110)
        self.assertFalse(goku_pose(points,self.face))
    def test_wrong_position_rejected(self):
        self.assertFalse(goku_pose([replace(p,y=p.y+90) for p in hand()],self.face))
    def test_folded_index_rejected(self):
        points=hand(); points[8]=Point(145,200)
        self.assertFalse(goku_pose(points,self.face))
    def test_open_palm_rejected(self):
        points=hand()
        for base,x in ((13,165),(17,175)):
            for offset,y in enumerate((195,165,135,110)):
                points[base+offset]=Point(x,y)
        self.assertFalse(goku_pose(points,self.face))

class GateTests(unittest.TestCase):
    def released(self):
        gate=HoldGate()
        for i in range(6): gate.update(False,i/10)
        return gate
    def test_startup_held_pose_never_triggers(self):
        gate=HoldGate()
        self.assertFalse(any(gate.update(True,i/10) for i in range(40)))
    def test_hold_once_and_release_to_rearm(self):
        gate=self.released()
        self.assertEqual(sum(gate.update(True,i/10) for i in range(6,40)),1)
        for i in range(40,46): gate.update(False,i/10)
        self.assertEqual(sum(gate.update(True,i/10) for i in range(46,70)),1)
    def test_break_resets_countdown(self):
        gate=self.released()
        for i in range(6,13): self.assertFalse(gate.update(True,i/10))
        gate.update(False,1.3)
        for i in range(14,23): self.assertFalse(gate.update(True,i/10))
    def test_stalled_inference_cannot_complete_hold(self):
        gate=self.released(); gate.update(True,0.6)
        self.assertFalse(gate.update(True,2))
        self.assertFalse(gate.update(True,2.1))
    def test_repeated_or_backward_timestamp_disarms(self):
        for stamp in (0.6,0.2):
            gate=self.released(); gate.update(True,0.6)
            self.assertFalse(gate.update(True,stamp)); self.assertFalse(gate.armed)

class SceneTests(unittest.TestCase):
    def setUp(self):
        self.scene=Scene(); self.empty=np.full((12,16,3),30,np.uint8)
        self.live=np.full_like(self.empty,180)
    def calibrated(self):
        self.scene.propose([self.empty.copy() for _ in range(6)]); self.scene.confirm()
    def test_requires_background_and_confirmation(self):
        with self.assertRaises(ValueError): self.scene.toggle()
        self.scene.propose([self.empty.copy() for _ in range(6)])
        with self.assertRaises(ValueError): self.scene.toggle()
    def test_instant_exact_background_and_manual_restore(self):
        self.calibrated(); self.scene.toggle()
        np.testing.assert_array_equal(self.scene.render(self.live),self.empty)
        self.scene.restore()
        np.testing.assert_array_equal(self.scene.render(self.live),self.live)
    def test_return_by_second_toggle(self):
        self.calibrated(); self.scene.toggle(); self.scene.toggle()
        np.testing.assert_array_equal(self.scene.render(self.live),self.live)
    def test_motion_and_insufficient_samples_rejected(self):
        with self.assertRaises(ValueError): self.scene.propose([self.empty])
        with self.assertRaises(ValueError): self.scene.propose([self.empty]*5+[self.live])
    def test_resolution_change_invalidates_background(self):
        self.calibrated(); self.scene.toggle()
        with self.assertRaises(ValueError): self.scene.render(np.zeros((8,8,3),np.uint8))
        self.assertIsNone(self.scene.background); self.assertFalse(self.scene.hidden)
    def test_render_does_not_expose_mutable_background(self):
        self.calibrated(); self.scene.toggle(); result=self.scene.render(self.live); result[:]=0
        np.testing.assert_array_equal(self.scene.render(self.live),self.empty)

if __name__=='__main__': unittest.main()
