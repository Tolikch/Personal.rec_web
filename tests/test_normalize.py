import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from anilist.normalize import normalize_score


class TestNormalizeScore(unittest.TestCase):
    def test_point_10(self):
        self.assertEqual(normalize_score(7, "POINT_10"), 7.0)
        self.assertEqual(normalize_score(10, "POINT_10"), 10.0)

    def test_point_10_decimal(self):
        self.assertEqual(normalize_score(8.5, "POINT_10_DECIMAL"), 8.5)

    def test_point_100(self):
        self.assertEqual(normalize_score(85, "POINT_100"), 8.5)
        self.assertEqual(normalize_score(100, "POINT_100"), 10.0)

    def test_point_5(self):
        self.assertEqual(normalize_score(4, "POINT_5"), 8.0)
        self.assertEqual(normalize_score(5, "POINT_5"), 10.0)

    def test_point_3(self):
        self.assertEqual(normalize_score(2, "POINT_3"), round(2 / 3 * 10, 3))
        self.assertEqual(normalize_score(3, "POINT_3"), 10.0)

    def test_zero_score(self):
        self.assertIsNone(normalize_score(0, "POINT_10"))
        self.assertIsNone(normalize_score(0, "POINT_100"))

    def test_none(self):
        self.assertIsNone(normalize_score(None, "POINT_10"))

    def test_negative(self):
        self.assertIsNone(normalize_score(-1, "POINT_10"))

    def test_out_of_range(self):
        self.assertIsNone(normalize_score(11, "POINT_10"))
        self.assertIsNone(normalize_score(101, "POINT_100"))
        self.assertIsNone(normalize_score(6, "POINT_5"))
        self.assertIsNone(normalize_score(4, "POINT_3"))

    def test_unknown_format_defaults(self):
        self.assertEqual(normalize_score(5, "UNKNOWN"), 5.0)


if __name__ == "__main__":
    unittest.main()
