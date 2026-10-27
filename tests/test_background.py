import unittest
import numpy as np
from sumi.background import LiveBackground

class LiveBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.bg=np.full((100,160,3),40,np.uint8)
        self.mask=np.zeros((100,160),np.float32); self.mask[20:85,65:100]=1
        self.person=self.bg.copy(); self.person[self.mask>0]=220
        self.model=LiveBackground(); self.model.reset(self.bg)
    def test_no_observation_and_stale_mask_use_saved_background(self):
        np.testing.assert_array_equal(self.model.render(self.person,self.bg,0),self.bg)
        self.model.observe(self.person,self.mask,1)
        np.testing.assert_array_equal(self.model.render(self.person,self.bg,2),self.bg)
    def test_person_is_removed_and_not_learned(self):
        for t in (1,1.2,1.4): self.model.observe(self.person,self.mask,t)
        result=self.model.render(self.person,self.bg,1.41)
        np.testing.assert_array_equal(result[30:75,70:95],self.bg[30:75,70:95])
        np.testing.assert_array_equal(self.model.plate[30:75,70:95],self.bg[30:75,70:95])
    def test_visible_background_is_live(self):
        frame=self.person.copy(); frame[5:15,5:15]=120
        self.model.observe(frame,self.mask,1)
        result=self.model.render(frame,self.bg,1.05)
        np.testing.assert_array_equal(result[5:15,5:15],frame[5:15,5:15])
    def test_two_observations_required_before_learning_visible_pixels(self):
        frame=self.person.copy(); frame[5:15,5:15]=120
        self.model.observe(frame,self.mask,1)
        self.assertEqual(int(self.model.plate[8,8,0]),40)
        self.model.observe(frame,self.mask,1.2)
        self.assertEqual(int(self.model.plate[8,8,0]),120)
    def test_new_motion_is_guarded_until_segmented(self):
        self.model.observe(self.person,self.mask,1)
        moved=self.person.copy(); moved[5:15,5:15]=220
        result=self.model.render(moved,self.bg,1.1)
        self.assertEqual(int(result[8,8,0]),40)
    def test_revealed_area_is_learned_after_guard_expires(self):
        self.model.observe(self.person,self.mask,1)
        empty=self.bg.copy(); empty[30:75,70:95]=90
        zero=np.zeros_like(self.mask)
        for t in (1.2,1.8,2.0): self.model.observe(empty,zero,t)
        np.testing.assert_array_equal(self.model.plate[35:70,75:90],empty[35:70,75:90])
    def test_invalid_mask_does_not_replace_valid_sample(self):
        self.model.observe(self.person,self.mask,1)
        self.model.observe(self.person,np.full_like(self.mask,np.nan),1.2)
        self.assertEqual(self.model.last_sample,1)
    def test_recalibration_resets_history_and_learned_pixels(self):
        self.model.observe(self.person,self.mask,1)
        new=np.full_like(self.bg,75); self.model.reset(new)
        np.testing.assert_array_equal(self.model.render(self.person,new,2),new)
        self.assertEqual(len(self.model.history),0)

if __name__=='__main__': unittest.main()
