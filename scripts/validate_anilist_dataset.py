"""Validate AniList collected datasets and compatibility with PersonaRec."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from anilist.storage import processed_path, raw_path


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        raise SystemExit(1)


def main() -> None:
    catalog_path = raw_path("anilist_anime.csv")
    interactions_path = raw_path("anilist_user_anime.csv")
    mapping_path = processed_path("id_mapping.csv")
    clean_path = processed_path("anilist_interactions_clean.csv")

    print("=== Files ===")
    for p in (catalog_path, interactions_path, mapping_path, clean_path):
        print(p, p.is_file())

    if not catalog_path.is_file():
        print("Catalog not collected yet; skipping deep validation.")
        return

    catalog = pd.read_csv(catalog_path)
    print("Catalog shape:", catalog.shape)
    check("catalog has anilist_id", "anilist_id" in catalog.columns)
    check("catalog no duplicate anilist_id", catalog["anilist_id"].is_unique)
    check("catalog anilist_id not null", catalog["anilist_id"].notna().all())

    if interactions_path.is_file():
        interactions = pd.read_csv(interactions_path)
        print("Interactions shape:", interactions.shape)
        check("interactions has user_id", "user_id" in interactions.columns)
        check("interactions has anilist_id", "anilist_id" in interactions.columns)
        check("interactions no duplicate (user,anime)", not interactions.duplicated(["user_id", "anilist_id"]).any())

    if mapping_path.is_file():
        mapping = pd.read_csv(mapping_path)
        print("Mapping shape:", mapping.shape)
        check("mapping has kaggle_anime_id", "kaggle_anime_id" in mapping.columns)
        status_col = "match_status" if "match_status" in mapping.columns else "status"
        matched = (mapping[status_col].astype(str).str.startswith("matched")).sum() if status_col in mapping.columns else 0
        print("Matched Kaggle anime:", int(matched), "/", len(mapping))

    if clean_path.is_file():
        clean = pd.read_csv(clean_path)
        print("Clean interactions shape:", clean.shape)
        if "score_normalized" in clean.columns:
            valid = clean["score_normalized"].dropna()
            check("normalized scores in [0,10]", ((valid >= 0) & (valid <= 10)).all() if len(valid) else True)
            print("Valid scores:", int(valid.notna().sum()), "/", len(clean))

    # Compatibility: can we build Kaggle-like ratings from AniList interactions?
    if interactions_path.is_file() and mapping_path.is_file():
        interactions = pd.read_csv(interactions_path)
        mapping = pd.read_csv(mapping_path)
        merged = interactions.merge(mapping[["kaggle_anime_id", "anilist_id"]], on="anilist_id", how="inner")
        print("AniList interactions mappable to Kaggle anime:", len(merged))
        if "score_raw" in merged.columns:
            # show sample
            print(merged[["user_id", "kaggle_anime_id", "score_raw"]].head().to_string(index=False))

    print("Validation completed successfully.")


if __name__ == "__main__":
    main()
