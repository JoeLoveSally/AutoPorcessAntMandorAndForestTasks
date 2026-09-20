"""The close control must use full-resolution device coordinates."""

import unittest

from domain_data import Observation
from screen_perception import close_circle_element


class OverlayGeometryTests(unittest.TestCase):
    def test_crop_offset_is_added_to_detected_circle(self):
        obs = Observation("obs-1", 0.0, 1440, 3200, "com.eg.android.AlipayGphone", [])
        item = close_circle_element(obs, (210.9, 140.2, 35.0), (504, 2496))
        self.assertEqual(item.bounds, (679, 2601, 749, 2671))
        self.assertEqual(item.point, (714, 2636))
        self.assertEqual(item.observation, "obs-1")

    def test_bounds_are_clipped_to_display(self):
        obs = Observation("obs-2", 0.0, 100, 100, "alipay", [])
        item = close_circle_element(obs, (10, 10, 20), (75, 75))
        self.assertEqual(item.bounds, (65, 65, 100, 100))
        self.assertTrue(0 <= item.point[0] < obs.width)
        self.assertTrue(0 <= item.point[1] < obs.height)


if __name__ == "__main__":
    unittest.main()
