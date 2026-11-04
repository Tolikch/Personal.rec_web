"""Collect AniList user anime lists."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from anilist.client import AniListClient
from anilist.storage import (
    load_checkpoint,
    raw_path,
    save_checkpoint,
    upsert_csv,
)

logger = logging.getLogger("anilist.users")

USER_COLUMNS = [
    "anilist_user_id",
    "username",
    "score_format",
    "collected_at",
]

INTERACTION_COLUMNS = [
    "user_id",
    "anilist_id",
    "mal_id",
    "score_raw",
    "status",
    "progress",
    "progress_volumes",
    "repeat",
    "private",
    "notes",
    "updated_at",
    "created_at",
    "collected_at",
]

USER_QUERY_BY_ID = """
query ($id: Int) {
  User(id: $id) {
    id
    name
    mediaListOptions { scoreFormat }
  }
}
"""

USER_QUERY_BY_NAME = """
query ($name: String) {
  User(name: $name) {
    id
    name
    mediaListOptions { scoreFormat }
  }
}
"""

LIST_QUERY = """
query ($userId: Int, $chunk: Int, $perChunk: Int) {
  MediaListCollection(userId: $userId, type: ANIME, chunk: $chunk, perChunk: $perChunk) {
    lists {
      entries {
        mediaId
        status
        score
        progress
        progressVolumes
        repeat
        private
        notes
        updatedAt
        createdAt
        media { id idMal }
      }
    }
  }
}
"""

PAGE_USERS_QUERY = """
query ($page: Int, $perPage: Int, $search: String, $sort: [UserSort]) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total currentPage lastPage hasNextPage }
    users(search: $search, sort: $sort) { id name }
  }
}
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_user(
    client: AniListClient,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    if user_id is not None:
        data = client.query(USER_QUERY_BY_ID, {"id": user_id})
    else:
        data = client.query(USER_QUERY_BY_NAME, {"name": username})
    user = data.get("User") or {}
    if not user:
        raise RuntimeError(f"User not found: id={user_id} name={username}")
    uid = user["id"]
    name = user["name"]
    score_format = (user.get("mediaListOptions") or {}).get("scoreFormat")

    upsert_csv(
        raw_path("anilist_users.csv"),
        [{
            "anilist_user_id": uid,
            "username": name,
            "score_format": score_format,
            "collected_at": _now(),
        }],
        USER_COLUMNS,
        key=["anilist_user_id"],
    )

    interactions: List[Dict[str, Any]] = []
    chunk = 1
    per_chunk = 500
    max_chunks = 100
    while chunk <= max_chunks:
        ldata = client.query(LIST_QUERY, {"userId": uid, "chunk": chunk, "perChunk": per_chunk})
        collection = ldata.get("MediaListCollection") or {}
        lists = collection.get("lists") or []
        entries_found = 0
        for lst in lists:
            for entry in (lst.get("entries") or []):
                media = entry.get("media") or {}
                interactions.append({
                    "user_id": uid,
                    "anilist_id": media.get("id") or entry.get("mediaId"),
                    "mal_id": media.get("idMal"),
                    "score_raw": entry.get("score"),
                    "status": entry.get("status"),
                    "progress": entry.get("progress"),
                    "progress_volumes": entry.get("progressVolumes"),
                    "repeat": entry.get("repeat"),
                    "private": entry.get("private"),
                    "notes": entry.get("notes"),
                    "updated_at": entry.get("updatedAt"),
                    "created_at": entry.get("createdAt"),
                    "collected_at": _now(),
                })
                entries_found += 1
        logger.info("User %s chunk %s: %s entries", uid, chunk, entries_found)
        if entries_found == 0 or entries_found < per_chunk:
            break
        chunk += 1

    # Deduplicate within user.
    seen = set()
    unique = []
    for row in interactions:
        key = (row["user_id"], row["anilist_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    interactions = unique

    upsert_csv(raw_path("anilist_user_anime.csv"), interactions, INTERACTION_COLUMNS, key=["user_id", "anilist_id"])
    return {"user_id": uid, "username": name, "entries": len(interactions), "score_format": score_format}


def _user_key(user_id: Optional[int], username: Optional[str]) -> str:
    if user_id is not None:
        return f"id:{user_id}"
    return f"name:{username}"


def collect_users_from_file(client: AniListClient, path: str) -> List[Dict[str, Any]]:
    checkpoint = load_checkpoint("users.json")
    completed = set(checkpoint.get("completed", []))
    stats = checkpoint.get("stats", {"success": 0, "failed": 0})
    results = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                left, right = line.split(":", 1)
                if left.isdigit():
                    uid, uname = int(left), right
                else:
                    uid, uname = None, line
            elif line.isdigit():
                uid, uname = int(line), None
            else:
                uid, uname = None, line
            key = _user_key(uid, uname)
            if key in completed:
                logger.info("Skipping already collected user %s", key)
                continue
            try:
                res = collect_user(client, user_id=uid, username=uname)
                results.append(res)
                completed.add(key)
                stats["success"] = stats.get("success", 0) + 1
            except Exception as exc:
                logger.warning("Failed user %s: %s", key, exc)
                stats["failed"] = stats.get("failed", 0) + 1
                if "errors" not in stats:
                    stats["errors"] = []
                stats["errors"].append({"user": key, "error": str(exc)})
            save_checkpoint("users.json", {"completed": sorted(completed), "stats": stats})
    return results


def enumerate_user_ids(
    client: AniListClient,
    max_users: int = 5000,
    max_depth: int = 2,
    chars: str = "abcdefghijklmnopqrstuvwxyz0123456789",
) -> List[Dict[str, Any]]:
    collected: dict[int, str] = {}

    def fetch_prefix(prefix: str, depth: int) -> None:
        if len(collected) >= max_users:
            return
        page = 1
        per_page = 50
        while len(collected) < max_users:
            search = prefix if prefix else None
            data = client.query(
                PAGE_USERS_QUERY,
                {"page": page, "perPage": per_page, "search": search, "sort": ["ID_DESC"]},
            )
            page_data = (data.get("Page") or {})
            users = page_data.get("users") or []
            total = (page_data.get("pageInfo") or {}).get("total", 0)
            for u in users:
                collected[u["id"]] = u["name"]
                if len(collected) >= max_users:
                    break
            info = page_data.get("pageInfo") or {}
            if not info.get("hasNextPage") or len(users) < per_page:
                break
            page += 1
        if total >= 5000 and depth < max_depth and len(prefix) < max_depth + 1:
            for ch in chars:
                if len(collected) >= max_users:
                    break
                fetch_prefix(prefix + ch, depth + 1)

    fetch_prefix("", 0)
    return [{"id": uid, "name": name} for uid, name in list(collected.items())[:max_users]]


def collect_enumerated_users(client: AniListClient, max_users: int = 5000) -> List[Dict[str, Any]]:
    users = enumerate_user_ids(client, max_users=max_users)
    checkpoint = load_checkpoint("users.json")
    completed = set(checkpoint.get("completed", []))
    stats = checkpoint.get("stats", {"success": 0, "failed": 0})
    results = []
    for u in users:
        key = f"id:{u['id']}"
        if key in completed:
            continue
        try:
            res = collect_user(client, user_id=u["id"], username=u["name"])
            results.append(res)
            completed.add(key)
            stats["success"] = stats.get("success", 0) + 1
        except Exception as exc:
            logger.warning("Failed user %s: %s", key, exc)
            stats["failed"] = stats.get("failed", 0) + 1
            stats.setdefault("errors", []).append({"user": key, "error": str(exc)})
        save_checkpoint("users.json", {"completed": sorted(completed), "stats": stats})
    return results