import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from anilist import storage
from anilist.collect_catalog import collect_catalog
from anilist.collect_users import collect_users_from_file, collect_user


class TestStorageUpsert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_REC_ANILIST_DIR"] = self.tmp.name
        storage.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("PERSONAL_REC_ANILIST_DIR", None)

    def test_upsert_no_duplicates(self):
        path = storage.raw_path("test.csv")
        cols = ["id", "val"]
        storage.upsert_csv(path, [{"id": 1, "val": "a"}], cols, key=["id"])
        storage.upsert_csv(path, [{"id": 1, "val": "b"}, {"id": 2, "val": "c"}], cols, key=["id"])
        df = __import__("pandas").read_csv(path)
        self.assertEqual(len(df), 2)
        self.assertEqual(df[df["id"] == 1]["val"].iloc[0], "b")


class TestCatalogCrashResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_REC_ANILIST_DIR"] = self.tmp.name
        storage.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("PERSONAL_REC_ANILIST_DIR", None)

    def _make_client(self, fail_after=None):
        client = MagicMock()
        counter = {"n": 0}

        def query(q, variables=None):
            ids = variables["ids"]
            # simulate crash after N batches
            counter["n"] += 1
            if fail_after is not None and counter["n"] > fail_after:
                raise RuntimeError("boom")
            rows = []
            for i in ids:
                if i % 2 == 0:  # only even ids exist
                    rows.append({"id": i, "idMal": i, "title": {"romaji": f"T{i}", "english": None, "native": None},
                                 "synonyms": [], "format": "TV", "genres": [], "tags": [],
                                 "averageScore": 80, "popularity": 10, "episodes": 12,
                                 "season": "WINTER", "seasonYear": 2020, "status": "FINISHED", "description": ""})
            return {"Page": {"media": rows}}

        client.query.side_effect = query
        return client

    def test_crash_and_resume(self):
        client = self._make_client(fail_after=2)
        try:
            collect_catalog(client, batch_size=50, max_id=200, resume=False, flush_every=1)
        except RuntimeError:
            pass
        # checkpoint should not have advanced beyond flushed point
        cp = storage.load_checkpoint("catalog.json")
        self.assertLessEqual(cp.get("next_id", 1), 151)

        # resume with working client
        client2 = self._make_client(fail_after=None)
        collect_catalog(client2, batch_size=50, max_id=200, resume=True, flush_every=1)
        import pandas as pd
        df = pd.read_csv(storage.raw_path("anilist_anime.csv"))
        # even ids from 2..200
        self.assertEqual(df["anilist_id"].is_unique, True)
        self.assertEqual(len(df), 100)


class TestUserCollection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_REC_ANILIST_DIR"] = self.tmp.name
        storage.ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("PERSONAL_REC_ANILIST_DIR", None)

    def test_user_error_does_not_stop(self):
        # Create users file
        users_file = Path(self.tmp.name) / "users.txt"
        users_file.write_text("baduser\n123:gooduser\n", encoding="utf-8")

        client = MagicMock()

        def query(q, variables=None):
            if "User(id" in q or "User(name" in q:
                if variables.get("name") == "baduser":
                    raise RuntimeError("user not found")
                return {"User": {"id": 123, "name": "gooduser", "mediaListOptions": {"scoreFormat": "POINT_10"}}}
            if "MediaListCollection" in q:
                return {"MediaListCollection": {"lists": [{"entries": [
                    {"mediaId": 1, "status": "COMPLETED", "score": 8, "progress": 12,
                     "progressVolumes": 0, "repeat": 0, "private": False, "notes": None,
                     "updatedAt": 1, "createdAt": 2, "media": {"id": 1, "idMal": 10}}
                ]}]}}
            return {}

        client.query.side_effect = query

        # Need anilist_users/anilist_user_anime maybe; run
        results = collect_users_from_file(client, str(users_file))
        self.assertEqual(len(results), 1)
        import pandas as pd
        interactions = pd.read_csv(storage.raw_path("anilist_user_anime.csv"))
        self.assertEqual(len(interactions), 1)
        cp = storage.load_checkpoint("users.json")
        # failed count
        self.assertEqual(cp["stats"].get("failed"), 1)
        self.assertEqual(cp["stats"].get("success"), 1)


if __name__ == "__main__":
    unittest.main()
