import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from anilist.mapping import _normalize_title


class TestNormalizeTitle(unittest.TestCase):
    def test_japanese(self):
        s = _normalize_title("進撃の巨人")
        self.assertNotEqual(s, "")
        self.assertIn("進撃", s)

    def test_mixed(self):
        s = _normalize_title("Attack on Titan: 進撃の巨人")
        self.assertIn("attack", s)
        self.assertIn("進撃", s)

    def test_english(self):
        s = _normalize_title("Fullmetal Alchemist: Brotherhood")
        self.assertEqual(s, "fullmetal alchemist brotherhood")

    def test_punctuation(self):
        s = _normalize_title("Re:Zero - Starting Life in Another World")
        self.assertNotIn(":", s)
        self.assertNotIn("-", s)

    def test_distinct_japanese(self):
        a = _normalize_title("ナルト")
        b = _normalize_title(" bleach ")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, "")
        self.assertNotEqual(b, "")

    def test_empty_for_punctuation_only(self):
        self.assertEqual(_normalize_title("!!!"), "")


if __name__ == "__main__":
    unittest.main()
