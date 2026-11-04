"""Unified anime catalog combining Kaggle and AniList data."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

from anilist.storage import raw_path


def _kaggle_path() -> Path:
    configured = os.environ.get("PERSONAL_REC_DATA_DIR")
    if configured:
        return Path(configured).expanduser() / "anime.csv"
    return Path(__file__).resolve().parents[1] / "data" / "raw" / "anime.csv"


@lru_cache(maxsize=1)
def load_unified_catalog() -> pd.DataFrame:
    kaggle_path = _kaggle_path()
    rows = []
    if kaggle_path.is_file():
        kaggle = pd.read_csv(kaggle_path)
        for _, r in kaggle.iterrows():
            rows.append({
                "item_id": int(r["anime_id"]),
                "mal_id": int(r["anime_id"]),
                "anilist_id": None,
                "source": "kaggle",
                "title": r.get("name"),
                "genres": r.get("genre"),
                "tags": None,
                "description": None,
                "format": r.get("type"),
                "season": None,
                "season_year": None,
                "synonyms": None,
                "score": r.get("rating"),
                "members": r.get("members"),
            })

    anilist_path = raw_path("anilist_anime.csv")
    if anilist_path.is_file():
        anilist = pd.read_csv(anilist_path)
        kaggle_mal_ids = {r["mal_id"] for r in rows if r["mal_id"] is not None}
        for _, r in anilist.iterrows():
            mal_id = r.get("mal_id")
            if pd.notna(mal_id) and int(mal_id) in kaggle_mal_ids:
                continue  # already in Kaggle
            anilist_id = int(r["anilist_id"])
            item_id = int(mal_id) if pd.notna(mal_id) else 1_000_000 + anilist_id
            rows.append({
                "item_id": item_id,
                "mal_id": int(mal_id) if pd.notna(mal_id) else None,
                "anilist_id": anilist_id,
                "source": "anilist",
                "title": r.get("title_english") or r.get("title_romaji") or r.get("title_native"),
                "genres": str(r.get("genres", "")).replace("|", ", ") if pd.notna(r.get("genres")) else None,
                "tags": r.get("tags"),
                "description": r.get("description"),
                "format": r.get("format"),
                "season": r.get("season"),
                "season_year": r.get("season_year"),
                "synonyms": r.get("synonyms"),
                "score": None,
                "members": r.get("popularity"),
            })

    return pd.DataFrame(rows).drop_duplicates("item_id")
