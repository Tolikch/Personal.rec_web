"""Hybrid recommendations backed by the Personal.Rec ratings dataset."""

from collections import defaultdict
from functools import lru_cache
import os
from pathlib import Path

import pandas as pd

from recommendations.similarity import cosine_similarity


MIN_USER_RATINGS = 50
MIN_ANIME_RATINGS = 30
MIN_SIMILARITY = 0.3
NEIGHBOR_LIMIT = 50
SHRINKAGE_LAMBDA = 10.0
SMOOTHING = 5.0
DEFAULT_LIMIT = 10


def _data_dir():
    configured = os.environ.get("PERSONAL_REC_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "data" / "raw"


@lru_cache(maxsize=1)
def load_profiles():
    """Load the source project's ratings and anime CSVs once per process."""
    data_dir = _data_dir()
    ratings_path = data_dir / "rating.csv"
    anime_path = data_dir / "anime.csv"

    if not ratings_path.is_file() or not anime_path.is_file():
        raise FileNotFoundError(
            "Не найдены rating.csv и anime.csv. "
            "Укажи каталог с файлами через PERSONAL_REC_DATA_DIR."
        )

    ratings = pd.read_csv(
        ratings_path,
        usecols=["user_id", "anime_id", "rating"],
    )
    ratings = ratings[ratings["rating"] != -1].copy()
    anime = pd.read_csv(anime_path, usecols=["anime_id", "name", "genre"])

    active_users = ratings.groupby("user_id").size()
    active_users = active_users[active_users >= MIN_USER_RATINGS].index
    popular_anime = ratings.groupby("anime_id").size()
    popular_anime = popular_anime[popular_anime >= MIN_ANIME_RATINGS].index
    ratings = ratings[
        ratings["user_id"].isin(active_users)
        & ratings["anime_id"].isin(popular_anime)
    ]

    profiles = defaultdict(dict)
    for row in ratings.itertuples(index=False):
        profiles[int(row.user_id)][int(row.anime_id)] = float(row.rating)

    anime = anime[anime["anime_id"].isin(popular_anime)]
    anime = anime.drop_duplicates("anime_id").set_index("anime_id")
    profiles = dict(profiles)
    item_users = defaultdict(set)
    for profile_user_id, profile in profiles.items():
        for anime_id in profile:
            item_users[anime_id].add(profile_user_id)
    return profiles, anime, item_users


def recommend_for_user(user_id, profiles, anime, item_users, limit=DEFAULT_LIMIT):
    """Return neighbor-based predictions for a filtered source-dataset profile."""
    user_id = int(user_id)
    target = profiles.get(user_id)
    if not target:
        return None

    target_mean = sum(target.values()) / len(target)
    candidates = set()
    neighbors = []

    candidate_users = set()
    for anime_id in target:
        candidate_users.update(item_users.get(anime_id, ()))
    candidate_users.discard(user_id)

    for other_id in candidate_users:
        profile = profiles[other_id]
        common = set(target).intersection(profile)
        if len(common) < 3:
            continue
        similarity = cosine_similarity(target, profile, common=common)
        if similarity < MIN_SIMILARITY:
            continue
        adjusted = similarity * len(common) / (
            len(common) + SHRINKAGE_LAMBDA
        )
        neighbors.append((other_id, adjusted))

    neighbors.sort(key=lambda item: item[1], reverse=True)
    neighbors = neighbors[:NEIGHBOR_LIMIT]
    if not neighbors:
        return []

    scores = defaultdict(float)
    weights = defaultdict(float)
    supporters = defaultdict(int)
    for other_id, similarity in neighbors:
        profile = profiles[other_id]
        other_mean = sum(profile.values()) / len(profile)
        for anime_id, rating in profile.items():
            if anime_id in target:
                continue
            candidates.add(anime_id)
            scores[anime_id] += similarity * (rating - other_mean)
            weights[anime_id] += similarity
            supporters[anime_id] += 1

    recommendations = []
    for anime_id in candidates:
        if weights[anime_id] <= 0:
            continue
        prediction = target_mean + scores[anime_id] / (
            weights[anime_id] + SMOOTHING
        )
        prediction = max(1.0, min(10.0, prediction))
        confidence_adjusted = prediction * supporters[anime_id] / (
            supporters[anime_id] + SMOOTHING
        )
        item = anime.loc[anime_id] if anime_id in anime.index else None
        if item is None:
            continue
        recommendations.append({
            "anime_id": int(anime_id),
            "name": str(item["name"]),
            "genre": str(item["genre"]) if pd.notna(item["genre"]) else "",
            "predicted_rating": round(prediction, 2),
            "supporters": int(supporters[anime_id]),
            "ranking_score": confidence_adjusted,
            "prediction_source": "collaborative",
        })

    recommendations.sort(
        key=lambda item: (item["ranking_score"], item["supporters"]),
        reverse=True,
    )
    for item in recommendations:
        item.pop("ranking_score")
    return recommendations[:max(1, min(int(limit), 50))]
