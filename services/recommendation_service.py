"""Genre similarity algorithm adapted from Personal.Rec/main.py."""

from collections import Counter, defaultdict
from functools import lru_cache
import math
from pathlib import Path
import re

import pandas as pd
from rapidfuzz import fuzz


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "anime.csv"
TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")
FRANCHISE_STOPWORDS = {
    "a", "an", "and", "the", "of", "to", "in", "on", "no",
    "movie", "movies", "film", "films", "special", "ova", "ona",
    "season", "part", "episode", "episodes", "tv", "theater",
}


def _tokens(value):
    return TOKEN_PATTERN.findall(str(value or "").lower())


def _normalize_name(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-zа-я0-9\s]", " ", value)
    return " ".join(value.split())


def _franchise_terms(value):
    """Return distinctive title words used to keep one franchise together."""
    return {
        token for token in _tokens(_normalize_name(value))
        if len(token) >= 3 and token not in FRANCHISE_STOPWORDS
        and not token.isdigit()
    }


@lru_cache(maxsize=1)
def _genre_vectors():
    if not DATA_PATH.is_file():
        raise FileNotFoundError(f"Не найден каталог аниме: {DATA_PATH}")

    anime = pd.read_csv(DATA_PATH, usecols=["anime_id", "name", "genre"])
    anime["name"] = anime["name"].fillna("")
    anime["genre"] = anime["genre"].fillna("")
    anime = anime.drop_duplicates("anime_id")

    tokenized = [_tokens(genres) for genres in anime["genre"]]
    document_count = len(tokenized)
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    vectors = {}
    for row, tokens in zip(anime.itertuples(index=False), tokenized):
        counts = Counter(tokens)
        vector = {
            token: (1 + math.log(count))
            * (math.log((1 + document_count) / (1 + document_frequency[token])) + 1)
            for token, count in counts.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if norm:
            vector = {token: value / norm for token, value in vector.items()}
        vectors[int(row.anime_id)] = {
            "name": str(row.name),
            "genres": str(row.genre),
            "vector": vector,
        }
    return vectors


def find_similar_anime(anime_id, limit=12):
    """Rank titles by cosine similarity of TF-IDF genre vectors."""
    vectors = _genre_vectors()
    anime_id = int(anime_id)
    seed = vectors.get(anime_id)
    if seed is None:
        return None

    similarities = []
    seed_franchise_terms = _franchise_terms(seed["name"])
    for candidate_id, candidate in vectors.items():
        if candidate_id == anime_id or not candidate["vector"]:
            continue
        # Genre-only similarity otherwise ranks sequels and franchise films
        # as near-perfect matches (e.g. Naruto Shippuuden -> Naruto movies).
        if seed_franchise_terms & _franchise_terms(candidate["name"]):
            continue
        if fuzz.token_set_ratio(
            _normalize_name(seed["name"]),
            _normalize_name(candidate["name"]),
        ) >= 85:
            continue
        similarity = sum(
            weight * candidate["vector"].get(token, 0.0)
            for token, weight in seed["vector"].items()
        )
        if similarity > 0:
            similarities.append({
                "mal_id": candidate_id,
                "title": candidate["name"],
                "genres": candidate["genres"],
                "match_percent": round(similarity * 100),
            })

    similarities.sort(key=lambda item: item["match_percent"], reverse=True)
    return similarities[:max(1, min(int(limit), 30))]
