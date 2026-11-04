"""Storage helpers for AniList collected data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def anilist_data_dir() -> Path:
    configured = os.environ.get("PERSONAL_REC_ANILIST_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "data" / "anilist"


def ensure_dirs() -> None:
    base = anilist_data_dir()
    for sub in ("raw", "processed", "checkpoints", "reports"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def raw_path(name: str) -> Path:
    ensure_dirs()
    return anilist_data_dir() / "raw" / name


def processed_path(name: str) -> Path:
    ensure_dirs()
    return anilist_data_dir() / "processed" / name


def checkpoint_path(name: str) -> Path:
    ensure_dirs()
    return anilist_data_dir() / "checkpoints" / name


def report_path(name: str) -> Path:
    ensure_dirs()
    return anilist_data_dir() / "reports" / name


def load_checkpoint(name: str) -> Dict[str, Any]:
    path = checkpoint_path(name)
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_checkpoint(name: str, payload: Dict[str, Any]) -> None:
    path = checkpoint_path(name)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def load_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def upsert_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str], key: List[str]) -> None:
    """Insert or update rows by key (last wins), avoiding duplicates."""
    if not rows:
        return
    df = pd.DataFrame(rows, columns=columns)
    if path.is_file():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df
    combined = combined.drop_duplicates(subset=key, keep="last")
    combined.to_csv(path, index=False, encoding="utf-8")


def append_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    # Backwards-compatible append; prefer upsert_csv for idempotent collection.
    if not rows:
        return
    df = pd.DataFrame(rows, columns=columns)
    if path.is_file():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df
    combined.to_csv(path, index=False, encoding="utf-8")


def dedupe_csv(path: Path, subset: List[str]) -> None:
    if not path.is_file():
        return
    df = pd.read_csv(path)
    before = len(df)
    df = df.drop_duplicates(subset=subset, keep="first")
    df.to_csv(path, index=False, encoding="utf-8")
    return before - len(df)
