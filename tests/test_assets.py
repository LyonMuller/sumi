from pathlib import Path
import unittest

from PIL import Image

from sumi.gesture_guides import GUIDES, illustration_size
from tools.package_release import ROOT,release_files


class AssetTests(unittest.TestCase):
    def test_windows_icon_has_all_sizes_and_is_packaged(self):
        included=set(release_files())
        for name in ('app-icon.png','app-icon.ico'):
            self.assertIn(ROOT/'assets'/'brand'/name,included)
        with Image.open(ROOT/'assets'/'brand'/'app-icon.ico') as icon:
            self.assertEqual(icon.format,'ICO')
            expected={(size,size) for size in (16,24,32,48,64,128,256)}
            self.assertEqual(icon.ico.sizes(),expected)
            for size in expected:
                frame=icon.ico.getimage(size)
                self.assertEqual(frame.size,size)
                frame.load()
                bounds=frame.getchannel('A').point(lambda alpha:255 if alpha>=32 else 0).getbbox()
                self.assertIsNotNone(bounds)
                left,top,right,bottom=bounds
                self.assertGreaterEqual(bottom-top,size[1]*.80)
                self.assertGreaterEqual(right-left,size[0]*.55)

    def test_each_gesture_has_a_valid_transparent_png_in_the_source_package(self):
        included=set(release_files())
        for name in {guide.image for guide in GUIDES.values()}:
            with self.subTest(image=name):
                path=ROOT/'assets'/'gestures'/name
                self.assertIn(path,included)
                with Image.open(path) as image:
                    self.assertEqual(image.format,'PNG')
                    self.assertLessEqual(max(image.size),2048)
                    self.assertIn('A',image.getbands())
                    minimum,maximum=image.getchannel('A').getextrema()
                    self.assertEqual(minimum,0)
                    self.assertGreater(maximum,0)
                    image.load()

    def test_energy_wave_illustration_is_listed_packaged_and_bundled(self):
        self.assertEqual(GUIDES['kamehameha'].image,'onda.png')
        path=ROOT/'assets'/'gestures'/'onda.png'
        self.assertTrue(path.is_file())
        self.assertIn(path,set(release_files()))
        specs=[spec.read_text(encoding='utf-8') for spec in (ROOT/'packaging').glob('*.spec')]
        self.assertTrue(specs)
        self.assertTrue(all("'onda.png'" in spec for spec in specs))

    def test_horizontal_tutorial_keeps_its_proportions_at_both_display_sizes(self):
        size=(1536,1024)
        ratio=size[0]/size[1]
        for limit in (64,280):
            width,height=illustration_size(size,limit)
            self.assertEqual(max(width,height),limit)
            self.assertAlmostEqual(width/height,ratio,delta=.03)
            self.assertNotEqual(width,height)

    def test_square_illustrations_stay_square(self):
        with Image.open(ROOT/'assets'/'gestures'/'digital.png') as image:
            self.assertEqual(illustration_size(image.size,280),(280,280))

    def test_readme_cover_exists_and_is_packaged(self):
        cover=ROOT/'assets'/'brand'/'readme-cover.png'
        self.assertIn(cover,release_files())
        self.assertIn('assets/brand/readme-cover.png',(ROOT/'README.md').read_text(encoding='utf-8'))
        with Image.open(cover) as image:
            self.assertEqual(image.format,'PNG')
            self.assertGreater(image.width,image.height)
            image.verify()
