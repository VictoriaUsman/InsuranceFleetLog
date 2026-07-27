import logging
import random
import time
from typing import Iterator

import requests

logger = logging.getLogger(__name__)

# 429 (rate limited) and the common transient 5xx codes get retried;
# everything else (401, 404, ...) is a real error and should fail immediately.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RestConnector:
    """Shared paging + rate-limit handling for cursor-paginated REST APIs.

    Argyle and GoHighLevel both paginate with a cursor/next-token and both
    return 429 with a Retry-After style hint, so this is shared rather than
    duplicated per-client.
    """

    base_url: str = ""
    timeout: int = 30
    max_retries: int = 5
    backoff_base: float = 1.0      # seconds, doubled each attempt
    backoff_max: float = 60.0      # seconds, cap regardless of attempt count

    # Proactive self-throttle: minimum seconds between outgoing requests,
    # independent of whether the server ever returns 429. 0 = disabled.
    # Set this once a client's documented rate limit is confirmed (see
    # connectors/argyle.py / gohighlevel.py - not verified yet, so left at 0).
    min_request_interval: float = 0.0

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._last_request_at: float | None = None

    def _headers(self) -> dict:
        raise NotImplementedError

    def _auth(self):
        return None

    def _throttle(self) -> None:
        if self.min_request_interval <= 0 or self._last_request_at is None:
            return
        remaining = self.min_request_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                return min(float(retry_after), self.backoff_max)
            except ValueError:
                pass
        # Full-jitter exponential backoff, so a fleet of concurrent runs
        # doesn't retry in lockstep against an already-struggling API.
        capped = min(self.backoff_base * (2**attempt), self.backoff_max)
        return random.uniform(0, capped)

    def request(self, method: str, path: str, **kwargs) -> dict:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        last_network_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=self._headers(),
                    auth=self._auth(),
                    timeout=self.timeout,
                    **kwargs,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_network_error = exc
                self._last_request_at = time.monotonic()
                if attempt == self.max_retries:
                    raise
                wait = self._backoff_seconds(attempt, None)
                logger.warning(
                    "Network error calling %s (%s), retrying in %.1fs (attempt %d/%d)",
                    url, exc, wait, attempt, self.max_retries,
                )
                time.sleep(wait)
                continue

            self._last_request_at = time.monotonic()

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                wait = self._backoff_seconds(attempt, response.headers.get("Retry-After"))
                logger.warning(
                    "Got %d from %s, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, url, wait, attempt, self.max_retries,
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json() if response.content else {}

        raise RuntimeError(f"Exceeded {self.max_retries} retries calling {url}") from last_network_error

    def paginate(
        self,
        path: str,
        params: dict | None = None,
        page_param: str = "cursor",
        results_key: str = "results",
        next_key: str = "next",
    ) -> Iterator[dict]:
        """Follows `next_key` until exhausted.

        Handles both styles seen across these APIs: a bare cursor token
        (merged into `params[page_param]`) and a full next-page URL
        (Argyle returns a complete URL, DRF-style) - in the latter case
        the URL already carries its own query string, so params are dropped.
        """
        params = dict(params or {})
        next_path = path
        while True:
            data = self.request("GET", next_path, params=params if next_path == path else None)
            items = data.get(results_key, [])
            yield from items

            next_value = data.get(next_key)
            if not next_value:
                break
            if str(next_value).startswith("http"):
                next_path = next_value
            else:
                params[page_param] = next_value
