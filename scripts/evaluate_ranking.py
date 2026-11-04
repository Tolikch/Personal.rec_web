"""Evaluate ranking quality (Precision/Recall/NDCG@10)."""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from scripts import evaluate_recommender as ev
from services import content_similarity as cs
from services.hybrid_recommendation import load_profiles, recommend_for_user

ROOT = Path(__file__).resolve().parents[1]
RELEVANCE_THRESHOLD = 7


def precision_at_k(recommended, relevant_set, k=10):
    recs = recommended[:k]
    if not recs:
        return 0.0
    hits = sum(1 for r in recs if r in relevant_set)
    return hits / len(recs)


def recall_at_k(recommended, relevant_set, k=10):
    recs = recommended[:k]
    if not relevant_set:
        return None
    hits = sum(1 for r in recs if r in relevant_set)
    return hits / len(relevant_set)


def dcg_at_k(recommended, relevant_set, k=10):
    dcg = 0.0
    for i, item in enumerate(recommended[:k]):
        rel = 1.0 if item in relevant_set else 0.0
        if i == 0:
            dcg += rel
        else:
            dcg += rel / math.log2(i + 2)
    return dcg


def ndcg_at_k(recommended, relevant_set, k=10):
    if not relevant_set:
        return None
    dcg = dcg_at_k(recommended, relevant_set, k)
    ideal = sorted([1.0] * min(len(relevant_set), k) + [0.0] * max(0, k - len(relevant_set)), reverse=True)
    idcg = 0.0
    for i, rel in enumerate(ideal):
        if i == 0:
            idcg += rel
        else:
            idcg += rel / math.log2(i + 2)
    if idcg == 0:
        return None
    return dcg / idcg


def content_recommendations(user_id, profiles, catalog_items):
    profile = profiles.get(user_id, {})
    seeds = [aid for aid, r in profile.items() if r >= RELEVANCE_THRESHOLD]
    scores = defaultdict(float)
    seen = set(profile.keys())
    for seed in seeds:
        try:
            similars = cs.find_similar_items(seed, limit=20)
        except Exception:
            similars = None
        if not similars:
            continue
        for s in similars:
            iid = s["item_id"]
            if iid in seen:
                continue
            scores[iid] += s["match_percent"]
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [iid for iid, _ in ranked[:10]]


def cf_recommendations(user_id, profiles, anime, item_users):
    recs = recommend_for_user(user_id, profiles, anime, item_users, limit=10)
    if not recs:
        return []
    return [r["anime_id"] for r in recs]


def hybrid_recommendations(user_id, profiles, anime, item_users, catalog_items):
    cf = cf_recommendations(user_id, profiles, anime, item_users)
    content = content_recommendations(user_id, profiles, catalog_items)
    # Combine: CF first, then content not already present.
    combined = list(cf)
    seen = set(combined)
    for c in content:
        if c not in seen:
            combined.append(c)
            seen.add(c)
    return combined[:10]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    data_dir = Path(args.data_dir)
    ratings, anime = ev.load_data(data_dir)
    train, test = ev.split_ratings(ratings)
    profiles, anime_f, item_users, popular, active = ev.build_profiles(train, anime)

    # relevant test items per user
    relevant_by_user = defaultdict(set)
    for row in test.itertuples(index=False):
        if float(row.rating) >= RELEVANCE_THRESHOLD:
            relevant_by_user[int(row.user_id)].add(int(row.anime_id))

    strategies = {
        "Content-based": lambda u: content_recommendations(u, profiles, None),
        "Collaborative Filtering": lambda u: cf_recommendations(u, profiles, anime_f, item_users),
        "Hybrid": lambda u: hybrid_recommendations(u, profiles, anime_f, item_users, None),
    }

    results = {}
    for name, fn in strategies.items():
        precisions = []
        recalls = []
        ndcgs = []
        all_recs = []
        no_rec_users = 0
        train_seen_leaks = 0
        total_recs = 0
        users_tested = 0
        users_with_relevant = 0
        for uid in profiles:
            if uid not in relevant_by_user:
                continue
            users_tested += 1
            rel_set = relevant_by_user[uid]
            if rel_set:
                users_with_relevant += 1
            recs = fn(uid)
            if not recs:
                no_rec_users += 1
            # train-seen leak check
            train_seen = set(profiles.get(uid, {}).keys())
            train_seen_leaks += sum(1 for r in recs if r in train_seen)
            # duplicates
            # metrics
            precisions.append(precision_at_k(recs, rel_set, 10))
            r = recall_at_k(recs, rel_set, 10)
            if r is not None:
                recalls.append(r)
            n = ndcg_at_k(recs, rel_set, 10)
            if n is not None:
                ndcgs.append(n)
            all_recs.extend(recs)
            total_recs += len(recs)

        unique_recs = len(set(all_recs))
        catalog_size = len(anime_f)
        coverage = unique_recs / catalog_size if catalog_size else 0.0
        duplicates = total_recs - unique_recs
        results[name] = {
            "users_tested": users_tested,
            "users_with_relevant": users_with_relevant,
            "precision_at_10": (sum(precisions) / len(precisions)) if precisions else 0.0,
            "recall_at_10": (sum(recalls) / len(recalls)) if recalls else None,
            "ndcg_at_10": (sum(ndcgs) / len(ndcgs)) if ndcgs else None,
            "avg_recommendations_per_user": (total_recs / users_tested) if users_tested else 0.0,
            "users_without_recommendations": no_rec_users,
            "unique_recommended_items": unique_recs,
            "catalog_coverage": coverage,
            "duplicate_recommendations": duplicates,
            "train_seen_leaks": train_seen_leaks,
        }

    # groups: all kaggle
    report = {
        "relevance_threshold": RELEVANCE_THRESHOLD,
        "random_state": ev.RANDOM_STATE,
        "test_size": ev.TEST_SIZE,
        "strategies": results,
        "groups": {
            "kaggle": {"note": "All test ratings are Kaggle items."},
            "anilist_with_mal": {"mae": "N/A", "note": "No test ratings available."},
            "anilist_only": {"mae": "N/A", "note": "No test ratings available."},
        },
    }

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "ranking_evaluation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append("# Ranking Evaluation\n")
    md.append("| Strategy | Precision@10 | Recall@10 | NDCG@10 | Coverage |")
    md.append("|---|---:|---:|---:|---:|")
    for name, r in results.items():
        rec = "N/A" if r["recall_at_10"] is None else f"{r['recall_at_10']:.3f}"
        ndcg = "N/A" if r["ndcg_at_10"] is None else f"{r['ndcg_at_10']:.3f}"
        md.append(f"| {name} | {r['precision_at_10']:.3f} | {rec} | {ndcg} | {r['catalog_coverage']:.3f} |")
    (reports_dir / "ranking_evaluation.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
