"""Identifier mapping between Kaggle (MAL) and AniList."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

from anilist.storage import processed_path, report_path

logger = logging.getLogger("anilist.mapping")

MAPPING_COLUMNS = [
    "kaggle_anime_id",
    "anilist_id",
    "kaggle_title",
    "anilist_title",
    "matched_title",
    "match_method",
    "match_score",
    "match_status",
    "confidence",
]


def _normalize_title(value: str) -> str:
    import re
    import unicodedata
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.lower()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _normalize_format(value) -> str:
    return str(value or "").strip().upper()


def _build_anilist_index(anilist: pd.DataFrame) -> list[dict]:
    index = []
    for _, row in anilist.iterrows():
        aid = int(row["anilist_id"])
        fmt = _normalize_format(row.get("format"))
        titles = []
        for col in ("title_english", "title_romaji", "title_native"):
            if pd.notna(row.get(col)):
                titles.append((str(row.get(col)), col))
        # synonyms stored as pipe-separated in catalog
        syns = row.get("synonyms")
        if pd.notna(syns):
            for s in str(syns).split("|"):
                if s.strip():
                    titles.append((s.strip(), "synonym"))
        for title, source in titles:
            norm = _normalize_title(title)
            if norm:
                index.append({
                    "anilist_id": aid,
                    "title": title,
                    "norm": norm,
                    "source": source,
                    "format": fmt,
                })
    return index


def build_mapping(
    kaggle_anime_path: Optional[Path] = None,
    anilist_catalog_path: Optional[Path] = None,
    fuzzy_threshold: int = 95,
    review_threshold: int = 85,
) -> pd.DataFrame:
    if kaggle_anime_path is None:
        kaggle_anime_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "anime.csv"
    if anilist_catalog_path is None:
        from anilist.storage import raw_path
        anilist_catalog_path = raw_path("anilist_anime.csv")

    kaggle = pd.read_csv(kaggle_anime_path)
    anilist = pd.read_csv(anilist_catalog_path) if anilist_catalog_path.is_file() else pd.DataFrame()

    index = _build_anilist_index(anilist) if not anilist.empty else []

    # anilist format by id
    format_by_id = {}
    if not anilist.empty:
        for _, r in anilist.iterrows():
            format_by_id[int(r["anilist_id"])] = _normalize_format(r.get("format"))

    rows = []

    for _, krow in kaggle.iterrows():
        kaggle_id = int(krow["anime_id"])
        kaggle_title = krow.get("name")
        kaggle_format = _normalize_format(krow.get("type"))
        k_norm = _normalize_title(kaggle_title)

        anilist_id = None
        anilist_title = None
        matched_title = None
        method = "none"
        score = 0.0
        status = "unmatched"

        # Level 1: MAL ID
        if not anilist.empty and "mal_id" in anilist.columns:
            mal_matches = anilist[anilist["mal_id"] == kaggle_id]
            if not mal_matches.empty:
                # If multiple, mark ambiguous
                if len(mal_matches) > 1:
                    anilist_id = int(mal_matches.iloc[0]["anilist_id"])
                    anilist_title = mal_matches.iloc[0].get("title_english") or mal_matches.iloc[0].get("title_romaji")
                    method = "mal_id"
                    score = 100.0
                    status = "ambiguous"
                else:
                    r0 = mal_matches.iloc[0]
                    anilist_id = int(r0["anilist_id"])
                    anilist_title = r0.get("title_english") or r0.get("title_romaji")
                    method = "mal_id"
                    score = 100.0
                    status = "matched"
                    matched_title = anilist_title

        # Level 2: exact normalized title
        if status == "unmatched" and k_norm and index:
            exact_candidates = [c for c in index if c["norm"] == k_norm]
            distinct_ids = {c["anilist_id"] for c in exact_candidates}
            if len(distinct_ids) == 1:
                c0 = exact_candidates[0]
                # format check
                if kaggle_format and c0["format"] and kaggle_format != c0["format"]:
                    status = "needs_review"
                else:
                    status = "matched"
                anilist_id = c0["anilist_id"]
                anilist_title = c0["title"]
                matched_title = c0["title"]
                method = "exact_title"
                score = 100.0
            elif len(distinct_ids) > 1:
                status = "ambiguous"

        # Level 3: fuzzy
        if status == "unmatched" and k_norm and index:
            # candidate scores
            cand_scores = []
            for c in index:
                an = c["norm"]
                if not an:
                    continue
                r_score = fuzz.ratio(k_norm, an)
                ts_score = fuzz.token_set_ratio(k_norm, an)
                combined = max(r_score, ts_score)
                # penalize subset overmatch: if token_set >> ratio, likely different season
                subset_penalty = 0
                if ts_score - r_score > 15:
                    subset_penalty = 10
                final_score = combined - subset_penalty
                # format mismatch penalty
                if kaggle_format and c["format"] and kaggle_format != c["format"]:
                    final_score -= 15
                cand_scores.append((final_score, c))
            if cand_scores:
                cand_scores.sort(key=lambda x: x[0], reverse=True)
                best_score, best_c = cand_scores[0]
                second_score = cand_scores[1][0] if len(cand_scores) > 1 else 0
                if best_score >= fuzzy_threshold and (best_score - second_score) >= 2:
                    # format mismatch -> needs_review
                    if kaggle_format and best_c["format"] and kaggle_format != best_c["format"]:
                        status = "needs_review"
                    else:
                        status = "matched"
                    anilist_id = best_c["anilist_id"]
                    anilist_title = best_c["title"]
                    matched_title = best_c["title"]
                    method = "title_fuzzy"
                    score = float(best_score)
                elif best_score >= review_threshold:
                    status = "needs_review"
                    anilist_id = best_c["anilist_id"]
                    anilist_title = best_c["title"]
                    matched_title = best_c["title"]
                    method = "title_fuzzy"
                    score = float(best_score)
                else:
                    status = "unmatched"

        # If matched/needs_review but multiple kaggle map same anilist, mark ambiguous later.
        rows.append({
            "kaggle_anime_id": kaggle_id,
            "anilist_id": anilist_id,
            "kaggle_title": kaggle_title,
            "anilist_title": anilist_title,
            "matched_title": matched_title,
            "match_method": method,
            "match_score": round(score, 2),
            "match_status": status,
            "confidence": round(score / 100.0, 3) if score else 0.0,
        })

    mapping = pd.DataFrame(rows, columns=MAPPING_COLUMNS)

    # Many-to-one conflict detection
    if not mapping.empty:
        matched = mapping[mapping["anilist_id"].notna()]
        counts = matched.groupby("anilist_id").size()
        conflict_ids = set(counts[counts > 1].index.tolist())
        if conflict_ids:
            mask = mapping["anilist_id"].isin(conflict_ids) & mapping["match_status"].isin(["matched", "needs_review"])
            # MAL ID exact duplicates may be legitimate? Keep matched if method mal_id and same? Still flag ambiguous for fuzzy/exact.
            mapping.loc[mask & (mapping["match_method"] != "mal_id"), "match_status"] = "ambiguous"
            logger.warning("Ambiguous AniList IDs mapped to multiple Kaggle items: %s", len(conflict_ids))

    # Save mapping
    out = processed_path("id_mapping.csv")
    mapping.to_csv(out, index=False, encoding="utf-8")
    logger.info("Mapping: %s", mapping["match_status"].value_counts().to_dict())

    # Generate report
    _generate_report(mapping, anilist, kaggle)
    return mapping


def _generate_report(mapping: pd.DataFrame, anilist: pd.DataFrame, kaggle: pd.DataFrame) -> None:
    path = report_path("mapping_report.md")
    total_kaggle = len(kaggle)
    total_anilist = len(anilist) if not anilist.empty else 0
    counts = mapping["match_status"].value_counts().to_dict()
    method_counts = mapping["match_method"].value_counts().to_dict()
    matched = int((mapping["match_status"] == "matched").sum())
    ambiguous = int((mapping["match_status"] == "ambiguous").sum())
    needs_review = int((mapping["match_status"] == "needs_review").sum())
    unmatched = int((mapping["match_status"] == "unmatched").sum())

    # score distribution
    scores = mapping.loc[mapping["match_score"] > 0, "match_score"]
    score_bins = {}
    if not scores.empty:
        for b in (95, 90, 85, 80, 70, 0):
            pass
    # simple buckets
    buckets = {"95-100": 0, "90-94": 0, "85-89": 0, "80-84": 0, "<80": 0}
    for s in scores:
        if s >= 95:
            buckets["95-100"] += 1
        elif s >= 90:
            buckets["90-94"] += 1
        elif s >= 85:
            buckets["85-89"] += 1
        elif s >= 80:
            buckets["80-84"] += 1
        else:
            buckets["<80"] += 1

    conflicts = mapping[mapping["match_status"] == "ambiguous"]

    lines = []
    lines.append("# AniList-Kaggle Mapping Report\n")
    lines.append(f"- Kaggle anime: {total_kaggle}")
    lines.append(f"- AniList anime: {total_anilist}")
    lines.append(f"- Matched: {matched} ({matched/total_kaggle*100:.1f}%)")
    lines.append(f"- Ambiguous: {ambiguous} ({ambiguous/total_kaggle*100:.1f}%)")
    lines.append(f"- Needs review: {needs_review} ({needs_review/total_kaggle*100:.1f}%)")
    lines.append(f"- Unmatched: {unmatched} ({unmatched/total_kaggle*100:.1f}%)")
    lines.append("\n## Match method distribution\n")
    for k, v in method_counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Status distribution\n")
    for k, v in counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Score distribution (matched/review)\n")
    for k, v in buckets.items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Conflicts (ambiguous)\n")
    lines.append(f"Total ambiguous: {len(conflicts)}")
    if not conflicts.empty:
        lines.append("\nExamples:")
        for _, r in conflicts.head(10).iterrows():
            lines.append(f"- Kaggle {r['kaggle_anime_id']} '{r['kaggle_title']}' -> AniList {r['anilist_id']} '{r['anilist_title']}' ({r['match_method']}, {r['match_score']})")
    # needs review examples
    nr = mapping[mapping["match_status"] == "needs_review"]
    lines.append("\n## Needs review examples\n")
    for _, r in nr.head(10).iterrows():
        lines.append(f"- Kaggle {r['kaggle_anime_id']} '{r['kaggle_title']}' -> AniList {r['anilist_id']} '{r['anilist_title']}' ({r['match_method']}, {r['match_score']})")
    # unmatched examples
    un = mapping[mapping["match_status"] == "unmatched"]
    lines.append("\n## Unmatched examples\n")
    for _, r in un.head(10).iterrows():
        lines.append(f"- Kaggle {r['kaggle_anime_id']} '{r['kaggle_title']}'")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Mapping report written to %s", path)
