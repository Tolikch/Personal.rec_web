import os
import sys
import math
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.evaluate_ranking as rk


class TestRankingMetrics(unittest.TestCase):
    def test_precision(self):
        self.assertAlmostEqual(rk.precision_at_k([1, 2, 3], {1, 3}, 10), 2/3)

    def test_recall(self):
        self.assertAlmostEqual(rk.recall_at_k([1, 2], {1, 3, 4}, 10), 1/3)

    def test_ndcg(self):
        # one relevant at position 2
        val = rk.ndcg_at_k([2, 1], {1}, 10)
        self.assertIsNotNone(val)
        self.assertLessEqual(val, 1.0)

    def test_empty(self):
        self.assertEqual(rk.precision_at_k([], {1}, 10), 0.0)
        self.assertIsNone(rk.recall_at_k([], set(), 10))
        self.assertIsNone(rk.ndcg_at_k([], set(), 10))

    def test_relevance_threshold(self):
        self.assertEqual(rk.RELEVANCE_THRESHOLD, 7)


if __name__ == "__main__":
    unittest.main()
