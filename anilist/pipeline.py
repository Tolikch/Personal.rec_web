"""Pipeline orchestration for AniList collection."""

from __future__ import annotations

import argparse
import logging

from anilist.client import AniListClient
from anilist.collect_catalog import collect_catalog
from anilist.collect_users import collect_users_from_file, collect_enumerated_users
from anilist.mapping import build_mapping
from anilist.normalize import normalize_interactions
from anilist.storage import dedupe_csv, raw_path

logger = logging.getLogger("anilist.pipeline")


def run_catalog(client: AniListClient, resume: bool = True) -> dict:
    return collect_catalog(client, resume=resume)


def run_users(client: AniListClient, users_file: str) -> list:
    return collect_users_from_file(client, users_file)


def run_mapping() -> None:
    build_mapping()


def run_normalize() -> None:
    normalize_interactions()


def finalize() -> None:
    # dedupe catalog by anilist_id
    path = raw_path("anilist_anime.csv")
    removed = dedupe_csv(path, ["anilist_id"])
    logger.info("Deduped catalog, removed %s rows", removed)
    # dedupe interactions
    ipath = raw_path("anilist_user_anime.csv")
    removed2 = dedupe_csv(ipath, ["user_id", "anilist_id"])
    logger.info("Deduped interactions, removed %s rows", removed2)


def main() -> None:
    parser = argparse.ArgumentParser(description="AniList data collection for PersonaRec")
    parser.add_argument("--step", choices=["catalog", "users", "mapping", "normalize", "finalize", "all"], default="all")
    parser.add_argument("--users-file", help="Path to file with AniList usernames/ids")
    parser.add_argument("--enumerate-users", action="store_true", help="Enumerate public users via AniList API (can be slow)")
    parser.add_argument("--max-users", type=int, default=1000, help="Max users to enumerate")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume from checkpoint")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    client = AniListClient()

    if args.step in ("catalog", "all"):
        logger.info("=== Collecting catalog ===")
        print(collect_catalog(client, resume=not args.no_resume))

    if args.step in ("users", "all"):
        if args.enumerate_users:
            logger.info("=== Enumerating and collecting users ===")
            print(collect_enumerated_users(client, max_users=args.max_users))
        elif args.users_file:
            logger.info("=== Collecting users ===")
            print(collect_users_from_file(client, args.users_file))
        else:
            logger.info("No --users-file provided; skipping user collection.")

    if args.step in ("mapping", "all"):
        logger.info("=== Building ID mapping ===")
        build_mapping()

    if args.step in ("normalize", "all"):
        logger.info("=== Normalizing interactions ===")
        normalize_interactions()

    if args.step in ("finalize", "all"):
        logger.info("=== Finalizing ===")
        finalize()


if __name__ == "__main__":
    main()
