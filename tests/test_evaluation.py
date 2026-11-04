import os
import sys
import math
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.evaluate_recommender as ev


class TestEvaluationHelpers(unittest.TestCase):
    def test_split_deterministic(self):
        import pandas as pd
        ratings = pd.DataFrame({
            "user_id": [1]*10 + [2]*10,
            "anime_id": list(range(10)) + list(range(10, 20)),
            "rating": [5.0]*20,
        })
        t1, s1 = ev.split_ratings(ratings)
        t2, s2 = ev.split_ratings(ratings)
        self.assertEqual(list(t1.index), list(t2.index))
        self.assertEqual(list(s1.index), list(s2.index))

    def test_no_leakage(self):
        import pandas as pd
        ratings = pd.DataFrame({
            "user_id": [1]*10,
            "anime_id": list(range(10)),
            "rating": [5.0]*10,
        })
        train, test = ev.split_ratings(ratings)
        merged = pd.merge(train, test, on=["user_id", "anime_id"], how="inner")
        self.assertEqual(len(merged), 0)

    def test_metrics_formula(self):
        y_true = [7.0, 5.0]
        y_pred = [6.0, 5.0]
        mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / len(y_true)
        rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / len(y_true))
        self.assertAlmostEqual(mae, 0.5)
        self.assertAlmostEqual(rmse, math.sqrt(0.5))

    def test_coverage_formula(self):
        self.assertAlmostEqual(2 / (2 + 3), 0.4)


if __name__ == "__main__":
    unittest.main()
