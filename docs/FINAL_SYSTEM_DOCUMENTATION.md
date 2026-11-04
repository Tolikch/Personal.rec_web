# PersonaRec — Final System Documentation

## Architecture
Flask app with Kaggle-based CF and unified content-based similarity over Kaggle + AniList catalog.

## Data flow
Kaggle CSV → unified_catalog → content_similarity. AniList raw CSV (optional) → unified catalog. CF uses Kaggle rating.csv.

## ID schema
- Kaggle anime_id = MAL ID
- AniList id = AniList ID
- Unified item_id = MAL ID or 1_000_000 + AniList ID for AniList-only items.

## Algorithms
- Content-based: weighted TF-IDF over genres/tags/description/format/season/synonyms.
- CF: existing user-based cosine (baseline stand 0.3).
- Hybrid: content-based fallback when no ratings.

## API
- /api/anime?q=
- /api/similar?mal_id=&anime_id=
- /api/recommendations?user_id=&limit=

## Commands
Prepare data:
```
python scripts\run_anilist_collect.py --step catalog
python scripts\run_anilist_collect.py --step mapping
python scripts\run_anilist_collect.py --step normalize
```
Run site:
```
python app.py
```
Tests:
```
python -m unittest discover -s tests
```

## Limitations
- CF requires Kaggle rating.csv.
- AniList interactions optional.
- No mass AniList collection run.
