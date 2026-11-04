"""AniList GraphQL client with adaptive rate limiting and retries."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import requests

API_URL = "https://graphql.anilist.co"

logger = logging.getLogger("anilist.client")


class AniListClient:
    def __init__(
        self,
        request_delay: float = 1.5,
        max_retries: int = 5,
        timeout: int = 30,
    ) -> None:
        self.base_delay = float(os.environ.get("ANILIST_REQUEST_DELAY", request_delay))
        self.request_delay = self.base_delay
        self.max_retries = int(os.environ.get("ANILIST_MAX_RETRIES", max_retries))
        self.timeout = int(os.environ.get("ANILIST_TIMEOUT", timeout))
        self._last_request_at = 0.0
        self._rate_limit = None
        self._rate_remaining = None
        self._rate_reset = None
        self.session = requests.Session()

    def _throttle(self) -> None:
        now = time.monotonic()
        # If we know remaining is low, wait until reset.
        if self._rate_remaining is not None and self._rate_remaining <= 2 and self._rate_reset:
            wait = self._rate_reset - time.time()
            if wait > 0:
                logger.info("Rate limit nearly exhausted; sleeping %.1fs", wait)
                time.sleep(wait)
        elapsed = now - self._last_request_at
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_at = time.monotonic()

    def _update_rate_info(self, response: requests.Response) -> None:
        limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if limit is not None:
            self._rate_limit = int(limit)
        if remaining is not None:
            self._rate_remaining = int(remaining)
        if reset is not None:
            self._rate_reset = int(reset)
        # Adapt delay to spread requests across the minute.
        if self._rate_limit and self._rate_limit > 0:
            # Aim for ~80% of the limit to stay safe.
            target_per_minute = max(1.0, self._rate_limit * 0.8)
            self.request_delay = max(self.base_delay, 60.0 / target_per_minute)

    def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        variables = variables or {}
        attempt = 0
        while True:
            self._throttle()
            try:
                response = self.session.post(
                    API_URL,
                    json={"query": query, "variables": variables},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                wait = min(60.0, 2 ** attempt)
                logger.warning("HTTP error %s, retry in %.1fs", exc, wait)
                time.sleep(wait)
                continue

            self._update_rate_info(response)

            if response.status_code == 429:
                attempt += 1
                if attempt > self.max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait = float(retry_after)
                elif self._rate_reset:
                    wait = max(1.0, self._rate_reset - time.time())
                else:
                    wait = min(120.0, 5 * (2 ** attempt))
                logger.warning("Rate limited (429), retry in %.1fs", wait)
                time.sleep(wait)
                continue

            if 500 <= response.status_code < 600:
                attempt += 1
                if attempt > self.max_retries:
                    response.raise_for_status()
                wait = min(120.0, 2 ** attempt)
                logger.warning("Server error %s, retry in %.1fs", response.status_code, wait)
                time.sleep(wait)
                continue

            response.raise_for_status()
            payload = response.json()

            errors = payload.get("errors")
            if errors:
                message = " ".join(str(e.get("message", e)) for e in errors)
                if "Too Many Requests" in message or "rate limit" in message.lower():
                    attempt += 1
                    if attempt > self.max_retries:
                        raise RuntimeError(f"AniList GraphQL error: {message}")
                    wait = min(120.0, 5 * (2 ** attempt))
                    if self._rate_reset:
                        wait = max(wait, self._rate_reset - time.time())
                    logger.warning("GraphQL rate limit, retry in %.1fs", wait)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"AniList GraphQL error: {message}")

            return payload.get("data") or {}
