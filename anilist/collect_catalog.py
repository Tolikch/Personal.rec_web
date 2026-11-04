"""Collect AniList anime catalog."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from anilist.client import AniListClient
from anilist.storage import (
    load_checkpoint,
    raw_path,
    save_checkpoint,
    upsert_csv,
)

logger = logging.getLogger("anilist.catalog")

CATALOG_COLUMNS = [
    "anilist_id",
    "mal_id",
    "title_romaji",
    "title_english",
    "title_native",
    "synonyms",
    "format",
    "genres",
    "tags",
    "average_score",
    "popularity",
    "episodes",
    "season",
    "season_year",
    "status",
    "description",
    "collected_at",
]

CATALOG_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      idMal
      title { romaji english native }
      synonyms
      format
      genres
      tags { name rank }
      averageScore
      popularity
      episodes
      season
      seasonYear
      status
      description
    }
  }
}
"""

MAX_ID_QUERY = """
query {
  Page(perPage: 1) {
    media(type: ANIME, sort: ID_DESC) { id }
  }
}
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flatten(media: Dict[str, Any]) -> Dict[str, Any]:
    title = media.get("title") or {}
    tags = media.get("tags") or []
    tag_str = ";".join(
        f"{t.get('name')}:{t.get('rank')}" for t in tags if t.get("name")
    )
    return {
        "anilist_id": media.get("id"),
        "mal_id": media.get("idMal"),
        "title_romaji": title.get("romaji"),
        "title_english": title.get("english"),
        "title_native": title.get("native"),
        "synonyms": "|".join(media.get("synonyms") or []),
        "format": media.get("format"),
        "genres": "|".join(media.get("genres") or []),
        "tags": tag_str,
        "average_score": media.get("averageScore"),
        "popularity": media.get("popularity"),
        "episodes": media.get("episodes"),
        "season": media.get("season"),
        "season_year": media.get("seasonYear"),
        "status": media.get("status"),
        "description": (media.get("description") or "").replace("\n", " "),
        "collected_at": _now(),
    }


def collect_catalog(
    client: AniListClient,
    batch_size: int = 50,
    max_id: int | None = None,
    resume: bool = True,
    flush_every: int = 10,
) -> Dict[str, Any]:
    checkpoint = load_checkpoint("catalog.json") if resume else {}
    start_id = int(checkpoint.get("next_id", 1))
    path = raw_path("anilist_anime.csv")

    if max_id is None:
        data = client.query(MAX_ID_QUERY)
        media = (data.get("Page", {}) or {}).get("media", []) or []
        max_id = max((m.get("id") or 0) for m in media) if media else 0
        logger.info("Discovered max AniList ID: %s", max_id)

    total_rows = 0
    batch_rows: List[Dict[str, Any]] = []
    current = start_id
    batches_since_flush = 0
    while current <= max_id:
        end = min(current + batch_size - 1, max_id)
        ids = list(range(current, end + 1))
        data = client.query(CATALOG_QUERY, {"ids": ids})
        media_list = (data.get("Page", {}) or {}).get("media", []) or []
        for media in media_list:
            batch_rows.append(_flatten(media))
        total_rows += len(media_list)
        batches_since_flush += 1

        # Flush to disk and advance checkpoint only after successful write.
        if batches_since_flush >= flush_every or end >= max_id:
            upsert_csv(path, batch_rows, CATALOG_COLUMNS, key=["anilist_id"])
            batch_rows = []
            batches_since_flush = 0
            save_checkpoint("catalog.json", {"next_id": end + 1, "max_id": max_id})
            logger.info("Flushed through ID %s", end)

        logger.info("Processed IDs %s-%s, got %s anime (total %s)", current, end, len(media_list), total_rows)
        current = end + 1

    if batch_rows:
        upsert_csv(path, batch_rows, CATALOG_COLUMNS, key=["anilist_id"])
        save_checkpoint("catalog.json", {"next_id": max_id + 1, "max_id": max_id})

    save_checkpoint("catalog.json", {"next_id": max_id + 1, "max_id": max_id, "done": True})
    return {"max_id": max_id, "collected": total_rows, "path": str(path)}
