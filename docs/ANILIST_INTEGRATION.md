# AniList Integration for PersonaRec

## Architecture

The AniList integration is isolated in the `anilist/` package and does not modify
the existing Kaggle data, Flask application logic, or the `stand 0.3` recommendation
model.

Components:

- `anilist/client.py` — GraphQL client with throttling, retries, exponential backoff.
- `anilist/collect_catalog.py` — collects anime catalog by AniList ID ranges.
- `anilist/collect_users.py` — collects public user anime lists.
- `anilist/mapping.py` — maps Kaggle anime IDs (MAL IDs) to AniList IDs.
- `anilist/normalize.py` — normalizes AniList scores to a 0–10 scale.
- `anilist/storage.py` — CSV storage, checkpoints, deduplication.
- `anilist/pipeline.py` — orchestration and CLI.

## AniList API capabilities and limits

- Endpoint: `https://graphql.anilist.co`
- Catalog (Media) is publicly available without authentication.
- User lists (MediaListCollection) are available only for public profiles.
- AniList does not provide an endpoint to enumerate all users.
- Page depth is limited to 5000 entries per query path.
- Rate limit is approximately 90 requests per minute.

## Tables

### `data/anilist/raw/anilist_anime.csv`

- `anilist_id`, `mal_id`, `title_romaji`, `title_english`, `title_native`,
  `synonyms`, `format`, `genres`, `tags`, `average_score`, `popularity`,
  `episodes`, `season`, `season_year`, `status`, `description`, `collected_at`

### `data/anilist/raw/anilist_users.csv`

- `anilist_user_id`, `username`, `score_format`, `collected_at`

### `data/anilist/raw/anilist_user_anime.csv`

- `user_id`, `anilist_id`, `mal_id`, `score_raw`, `status`, `progress`,
  `progress_volumes`, `repeat`, `private`, `notes`, `updated_at`,
  `created_at`, `collected_at`

### `data/anilist/processed/id_mapping.csv`

- `kaggle_anime_id`, `anilist_id`, `title_kaggle`, `title_anilist`,
  `method`, `confidence`, `status`

### `data/anilist/processed/anilist_interactions_clean.csv`

- All interaction columns plus `score_format` and `score_normalized`.

## Storage format

CSV (UTF-8) for pandas compatibility. Checkpoints are JSON in
`data/anilist/checkpoints/`.

## ID matching rules

1. Primary: `Kaggle anime_id == AniList idMal`.
2. Fallback: fuzzy title matching with confidence threshold 0.95.
3. Low-confidence matches are marked `matched_low_confidence`.
4. Unmatched items are reported separately.

## Score normalization

AniList scores use per-user scales (`POINT_10`, `POINT_100`, `POINT_5`,
`POINT_3`, `POINT_10_DECIMAL`). Raw score is preserved in `score_raw`;
`score_normalized` converts to a 0–10 scale. Kaggle ratings remain unchanged.

## Authentication

No token is required for public catalog and public user lists. Optional
`ANILIST_ACCESS_TOKEN` may be added to `.env` for future authenticated
endpoints. Never commit secrets.

## Dependencies

See `requirements.txt` (requests, pandas, rapidfuzz). No new heavy dependencies.

## Running collection

```powershell
python scripts\run_anilist_collect.py --step catalog
python scripts\run_anilist_collect.py --step users --users-file data\anilist\users.txt
python scripts\run_anilist_collect.py --step mapping
python scripts\run_anilist_collect.py --step normalize
python scripts\run_anilist_collect.py --step finalize
```

## Resuming interrupted collection

Catalog collection stores `checkpoints/catalog.json` with `next_id`. Re-running
`--step catalog` continues from the last checkpoint. User collection is
append-based and deduplicated. `--no-resume` restarts catalog from ID 1.

## Data quality checks

Run:

```powershell
python scripts\validate_anilist_dataset.py
```

Checks: file presence, columns, duplicates, mapping integrity, score ranges,
and compatibility with existing ML input structure.

## Catalog collection strategy

Two approaches were considered:

1. `Page.media(type: ANIME)` pagination — simple, but limited to 5000 entries
   per sort path, so it cannot cover the full catalog.
2. ID-range `id_in` batching (implemented) — covers every ID up to the current
   maximum, robust but uses more requests (including empty ranges).

The implementation uses approach 2 for correctness.

## Rate limiting

The client reads `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
`X-RateLimit-Reset`, and `Retry-After`, adapts the request delay, and retries
on 429/5xx/GraphQL rate-limit errors with exponential backoff.

## Known limitations

- Full enumeration of all AniList users is possible via `Page.users` with prefix
  search, but it is slow and should be used with explicit limits (`--enumerate-users`,
  `--max-users`). For most experiments a provided users file is recommended.
- Private user lists are unavailable.
- Catalog collection is bounded by API page depth; ID-range chunking is used
  to cover all IDs up to the current maximum.
- AniList scores are per-user scale and must be normalized before ML use.
- No automatic model retraining is performed.
```

## Next steps

- Collect a larger user sample for future Collaborative Filtering experiments.
- Evaluate overlap between AniList interactions and Kaggle items.
- Consider a separate experiment comparing stand 0.3 with AniList-augmented
  data without changing the baseline.
