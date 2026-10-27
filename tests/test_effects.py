import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import cv2
import numpy as np
from sumi.effects import Silhouette,TeleportEffect,AnimeTeleportEffect
from sumi.preferences import load_preferences,save_preferences


def subject():
    mask=np.zeros((180,320),np.float32)
    cv2.circle(mask,(160,48),22,1,-1)
    cv2.ellipse(mask,(160,125),(40,65),0,0,360,1,-1)
    image=np.full((180,320,3),40,np.uint8)
    image[mask>0]=(80,140,210)
    return Silhouette(10,image,mask)

class EffectTests(unittest.TestCase):
    effect_type=TeleportEffect
    def setUp(self):
        self.subject=subject()
        self.background=np.full_like(self.subject.frame,40)
        self.live=self.subject.frame.copy()
    def test_disappearance_starts_live_and_finishes_exact_background(self):
        effect=self.effect_type(self.subject,True,10)
        np.testing.assert_array_equal(effect.render(self.live,self.background,10),self.live)
        np.testing.assert_array_equal(effect.render(self.live,self.background,10.48),self.background)
    def test_return_starts_background_and_finishes_current_live(self):
        effect=self.effect_type(self.subject,False,10)
        np.testing.assert_array_equal(effect.render(self.live,self.background,10),self.background)
        current=self.live.copy(); current[0,0]=255
        np.testing.assert_array_equal(effect.render(current,self.background,10.49),current)
    def test_animation_changes_subject_but_preserves_outside_region(self):
        effect=self.effect_type(self.subject,True,10)
        frame=effect.render(self.live,self.background,10.2)
        self.assertTrue(np.any(frame!=self.live))
        self.assertTrue(np.any(frame!=self.background))
        left,top,right,bottom=effect.box
        protected=np.ones(self.background.shape[:2],bool)
        protected[top:bottom,left:right]=False
        np.testing.assert_array_equal(frame[protected],self.background[protected])
        self.assertEqual(frame.dtype,np.uint8)
    def test_rejects_missing_subject_and_nonfinite_mask(self):
        for mask in (np.zeros_like(self.subject.mask),np.full_like(self.subject.mask,np.nan)):
            with self.assertRaises(ValueError): self.effect_type(Silhouette(10,self.live,mask),True,10)
    def test_elapsed_time_controls_animation_not_render_call_count(self):
        first=self.effect_type(self.subject,True,10)
        second=self.effect_type(self.subject,True,10)
        for t in (10.02,10.08,10.1): first.render(self.live,self.background,t)
        np.testing.assert_array_equal(first.render(self.live,self.background,10.3),second.render(self.live,self.background,10.3))
    def test_input_buffers_are_not_mutated(self):
        original=self.live.copy(); background=self.background.copy(); mask=self.subject.mask.copy()
        effect=self.effect_type(self.subject,True,10)
        effect.render(self.live,self.background,10.2)
        np.testing.assert_array_equal(self.live,original)
        np.testing.assert_array_equal(self.background,background)
        np.testing.assert_array_equal(self.subject.mask,mask)
    def test_shape_change_rejected(self):
        effect=self.effect_type(self.subject,True,10)
        with self.assertRaises(ValueError): effect.render(np.zeros((10,10,3),np.uint8),self.background,10.2)

class AnimeEffectTests(EffectTests):
    effect_type=AnimeTeleportEffect

class PreferenceTests(unittest.TestCase):
    def test_round_trip_and_missing_or_corrupt_file(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.json'
            self.assertEqual(load_preferences(path),{})
            save_preferences({'effect':'Goku','camera_path':'camera1'},path)
            self.assertEqual(load_preferences(path)['effect'],'Goku')
            path.write_text('{broken')
            self.assertEqual(load_preferences(path),{})
    def test_invalid_values_are_not_passed_to_ui(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.json'
            path.write_text('{"hold": 999,"effect":"Goku"}')
            self.assertEqual(load_preferences(path),{'effect':'Goku'})

if __name__=='__main__': unittest.main()
