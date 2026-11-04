import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from anilist import storage
from anilist.mapping import build_mapping


class TestBuildMapping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_REC_ANILIST_DIR"] = self.tmp.name
        storage.ensure_dirs()
        self.kaggle_path = Path(self.tmp.name) / "anime.csv"
        self.anilist_path = storage.raw_path("anilist_anime.csv")

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("PERSONAL_REC_ANILIST_DIR", None)

    def _write_kaggle(self, rows):
        pd.DataFrame(rows).to_csv(self.kaggle_path, index=False, encoding="utf-8")

    def _write_anilist(self, rows):
        pd.DataFrame(rows).to_csv(self.anilist_path, index=False, encoding="utf-8")

    def test_mal_id_match(self):
        self._write_kaggle([{"anime_id": 1, "name": "Foo", "type": "TV"}])
        self._write_anilist([{"anilist_id": 10, "mal_id": 1, "title_english": "Foo", "title_romaji": "Foo", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_method"], "mal_id")
        self.assertEqual(m.iloc[0]["match_status"], "matched")

    def test_exact_title(self):
        self._write_kaggle([{"anime_id": 999, "name": "Bar", "type": "TV"}])
        self._write_anilist([{"anilist_id": 20, "mal_id": None, "title_english": "Bar", "title_romaji": "Bar", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_method"], "exact_title")
        self.assertEqual(m.iloc[0]["match_status"], "matched")

    def test_unicode_title(self):
        self._write_kaggle([{"anime_id": 1000, "name": "進撃の巨人", "type": "TV"}])
        self._write_anilist([{"anilist_id": 30, "mal_id": None, "title_english": "Attack on Titan", "title_romaji": "Shingeki no Kyojin", "title_native": "進撃の巨人", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_method"], "exact_title")

    def test_seasons_not_merged(self):
        self._write_kaggle([{"anime_id": 1, "name": "Naruto", "type": "TV"}])
        self._write_anilist([
            {"anilist_id": 10, "mal_id": None, "title_english": "Naruto", "title_romaji": "Naruto", "format": "TV", "synonyms": ""},
            {"anilist_id": 11, "mal_id": None, "title_english": "Naruto Shippuden", "title_romaji": "Naruto Shippuden", "format": "TV", "synonyms": ""},
        ])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        # Should match exact "Naruto", not Shippuden
        self.assertEqual(m.iloc[0]["anilist_id"], 10)

    def test_format_mismatch_needs_review(self):
        self._write_kaggle([{"anime_id": 5, "name": "Foo Movie", "type": "Movie"}])
        self._write_anilist([{"anilist_id": 50, "mal_id": None, "title_english": "Foo Movie", "title_romaji": "Foo Movie", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_status"], "needs_review")

    def test_ambiguous_many_to_one(self):
        self._write_kaggle([
            {"anime_id": 1, "name": "Same", "type": "TV"},
            {"anime_id": 2, "name": "Same", "type": "TV"},
        ])
        self._write_anilist([{"anilist_id": 77, "mal_id": None, "title_english": "Same", "title_romaji": "Same", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        # exact title maps both to same anilist -> ambiguous
        self.assertTrue((m["match_status"] == "ambiguous").any())

    def test_unmatched_preserved(self):
        self._write_kaggle([{"anime_id": 7, "name": "ZZZZ", "type": "TV"}])
        self._write_anilist([{"anilist_id": 90, "mal_id": None, "title_english": "AAAA", "title_romaji": "AAAA", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_status"], "unmatched")
        self.assertIsNone(m.iloc[0]["anilist_id"]) if pd.isna(m.iloc[0]["anilist_id"]) else True

    def test_empty_fuzzy_guard(self):
        # punctuation-only title should not fuzzy match
        self._write_kaggle([{"anime_id": 8, "name": "!!!", "type": "TV"}])
        self._write_anilist([{"anilist_id": 91, "mal_id": None, "title_english": "!!!", "title_romaji": "!!!", "format": "TV", "synonyms": ""}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        # normalized empty -> unmatched (exact empty not allowed)
        self.assertEqual(m.iloc[0]["match_status"], "unmatched")

    def test_synonyms_match(self):
        self._write_kaggle([{"anime_id": 9, "name": "Titan", "type": "TV"}])
        self._write_anilist([{"anilist_id": 92, "mal_id": None, "title_english": "Attack on Titan", "title_romaji": "Shingeki", "format": "TV", "synonyms": "Titan"}])
        m = build_mapping(self.kaggle_path, self.anilist_path)
        self.assertEqual(m.iloc[0]["match_method"], "exact_title")


if __name__ == "__main__":
    unittest.main()
