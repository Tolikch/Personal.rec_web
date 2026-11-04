"""Score normalization for AniList interactions."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from anilist.storage import processed_path, raw_path

logger = logging.getLogger("anilist.normalize")

SCORE_FORMAT_FACTORS = {
    "POINT_10": (10.0, 10.0),
    "POINT_10_DECIMAL": (10.0, 10.0),
    "POINT_100": (100.0, 10.0),
    "POINT_5": (5.0, 10.0),
    "POINT_3": (3.0, 10.0),
}


def normalize_score(score, score_format: str) -> float | None:
    if pd.isna(score):
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    # AniList uses 0 to denote "no score".
    if value == 0:
        return None
    if value < 0:
        return None
    src_max, dst_max = SCORE_FORMAT_FACTORS.get(score_format or "POINT_10", (10.0, 10.0))
    if src_max == 0:
        return None
    # Reject values outside the source scale.
    if value > src_max:
        return None
    normalized = value / src_max * dst_max
    if normalized < 0:
        normalized = 0.0
    if normalized > dst_max:
        normalized = dst_max
    return round(normalized, 3)


def normalize_interactions() -> pd.DataFrame:
    interactions_path = raw_path("anilist_user_anime.csv")
    users_path = raw_path("anilist_users.csv")
    if not interactions_path.is_file():
        logger.warning("No interactions file found")
        return pd.DataFrame()

    interactions = pd.read_csv(interactions_path)
    if users_path.is_file():
        users = pd.read_csv(users_path)
        fmt_map = dict(zip(users["anilist_user_id"], users["score_format"]))
    else:
        fmt_map = {}

    def _fmt(uid):
        return fmt_map.get(uid, "POINT_10")

    interactions["score_format"] = interactions["user_id"].map(_fmt)
    interactions["score_normalized"] = interactions.apply(
        lambda r: normalize_score(r.get("score_raw"), r.get("score_format")), axis=1
    )

    # Clean: drop invalid scores but keep interactions with status
    # Mark invalid score rows
    interactions["has_valid_score"] = interactions["score_normalized"].notna()

    out = processed_path("anilist_interactions_clean.csv")
    interactions.to_csv(out, index=False, encoding="utf-8")
    logger.info("Normalized %s interactions, %s valid scores", len(interactions), interactions["has_valid_score"].sum())
    return interactions
