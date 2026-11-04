"""Content-based similarity over the unified catalog."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

import pandas as pd

from services.unified_catalog import load_unified_catalog

TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")

FIELD_WEIGHTS = {
    "title": 1,
    "genres": 3,
    "tags": 2,
    "description": 1,
    "format": 1,
    "season": 1,
    "synonyms": 1,
}

FRANCHISE_STOPWORDS = {
    "a", "an", "and", "the", "of", "to", "in", "on", "no",
    "movie", "movies", "film", "films", "special", "ova", "ona",
    "season", "part", "episode", "episodes", "tv", "theater",
}


def _tokens(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return TOKEN_PATTERN.findall(str(value).lower())


def _franchise_terms(name) -> set[str]:
    terms = {t for t in _tokens(name) if len(t) >= 3 and t not in FRANCHISE_STOPWORDS and not t.isdigit()}
    return terms


def _row_tokens(row) -> list[str]:
    tokens = []
    tokens += _tokens(row.get("title")) * FIELD_WEIGHTS["title"]
    tokens += _tokens(str(row.get("genres") or "").replace(",", " ")) * FIELD_WEIGHTS["genres"]
    tokens += _tokens(str(row.get("tags") or "").replace(";", " ").replace(":", " ")) * FIELD_WEIGHTS["tags"]
    tokens += _tokens(row.get("description")) * FIELD_WEIGHTS["description"]
    tokens += _tokens(row.get("format")) * FIELD_WEIGHTS["format"]
    tokens += _tokens(row.get("season")) * FIELD_WEIGHTS["season"]
    tokens += _tokens(row.get("synonyms")) * FIELD_WEIGHTS["synonyms"]
    if row.get("season_year") is not None and not pd.isna(row.get("season_year")):
        tokens.append(f"year_{int(row['season_year'])}")
    return tokens


@lru_cache(maxsize=1)
def _index():
    catalog = load_unified_catalog()
    vectors = {}
    names = {}
    franchise = {}
    for _, row in catalog.iterrows():
        item_id = int(row["item_id"])
        toks = _row_tokens(row)
        counts = Counter(toks)
        # tf-idf-ish: simple log
        vector = {t: (1 + math.log(c)) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vector.values()))
        if norm:
            vector = {t: v / norm for t, v in vector.items()}
        vectors[item_id] = vector
        names[item_id] = str(row.get("title") or "")
        franchise[item_id] = _franchise_terms(row.get("title"))
    return catalog, vectors, names, franchise


def invalidate_cache():
    _index.cache_clear()


def _media_to_row(media: dict) -> dict:
    title = media.get("title") or {}
    if isinstance(title, dict):
        title_str = title.get("english") or title.get("romaji") or title.get("native")
    else:
        title_str = media.get("title")
    genres = media.get("genres") or []
    tags = media.get("tags") or []
    tag_tokens = []
    for t in tags:
        if isinstance(t, dict):
            tag_tokens.append(t.get("name"))
        else:
            tag_tokens.append(str(t))
    synonyms = media.get("synonyms") or []
    return {
        "item_id": media.get("id") or media.get("anilist_id"),
        "title": title_str,
        "genres": ", ".join(genres) if isinstance(genres, list) else genres,
        "tags": " ".join([t for t in tag_tokens if t]),
        "description": media.get("description"),
        "format": media.get("format"),
        "season": media.get("season"),
        "season_year": media.get("seasonYear") or media.get("season_year"),
        "synonyms": " ".join(synonyms) if isinstance(synonyms, list) else synonyms,
    }


def find_similar_items(seed, limit=12):
    """seed: item_id (int) or dict (AniList media). Returns list of dicts."""
    catalog, vectors, names, franchise = _index()
    # Build seed vector
    if isinstance(seed, dict):
        row = _media_to_row(seed)
        seed_id = row["item_id"]
        seed_name = row["title"]
        toks = _row_tokens(row)
        counts = Counter(toks)
        seed_vector = {t: (1 + math.log(c)) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in seed_vector.values()))
        if norm:
            seed_vector = {t: v / norm for t, v in seed_vector.items()}
    else:
        seed_id = int(seed)
        seed = None
        row = None
        seed_vector = vectors.get(seed_id)
        # find row for name
        seed_name = names.get(seed_id)
        if seed_id not in vectors:
            return None

    if not seed_vector:
        return None

    seed_franchise = _franchise_terms(seed_name) if seed_name else set()
    similarities = []
    for candidate_id, cand_vector in vectors.items():
        if candidate_id == seed_id or not cand_vector:
            continue
        # franchise filter
        if seed_franchise & franchise.get(candidate_id, set()):
            # allow? skip only if high title similarity (original logic)
            pass
        cand_name = names.get(candidate_id, "")
        # skip if same franchise terms (original behavior) for sequels
        if seed_franchise & franchise.get(candidate_id, set()):
            # skip sequels to avoid near-duplicate franchise matches
            if True:
                pass
        # We'll keep original: skip if franchise terms overlap
        if seed_franchise & franchise.get(candidate_id, set()):
            continue
        # title similarity guard
        from rapidfuzz import fuzz
        if fuzz.token_set_ratio(str(seed_name or "").lower(), str(cand_name or "").lower()) >= 85:
            continue
        similarity = sum(w * cand_vector.get(t, 0.0) for t, w in seed_vector.items())
        if similarity > 0:
            # find row in catalog for metadata
            crow = catalog[catalog["item_id"] == candidate_id].iloc[0]
            mal = crow.get("mal_id")
            ani = crow.get("anilist_id")
            similarities.append({
                "item_id": int(candidate_id),
                "mal_id": int(mal) if pd.notna(mal) else None,
                "anilist_id": int(ani) if pd.notna(ani) else None,
                "title": crow.get("title"),
                "source": crow.get("source"),
                "match_percent": round(similarity * 100),
                "genres": crow.get("genres"),
                "format": crow.get("format"),
                "year": crow.get("season_year"),
            })

    similarities.sort(key=lambda x: x["match_percent"], reverse=True)
    return similarities[:max(1, min(int(limit), 30))]
