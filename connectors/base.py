import logging
import time
from typing import Iterator

import requests

logger = logging.getLogger(__name__)


class RestConnector:
    """Shared paging + rate-limit handling for cursor-paginated REST APIs.

    Argyle and GoHighLevel both paginate with a cursor/next-token and both
    return 429 with a Retry-After style hint, so this is shared rather than
    duplicated per-client.
    """

    base_url: str = ""
    timeout: int = 30
    max_retries: int = 5

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        raise NotImplementedError

    def _auth(self):
        return None

    def request(self, method: str, path: str, **kwargs) -> dict:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        for attempt in range(1, self.max_retries + 1):
            response = self.session.request(
                method,
                url,
                headers=self._headers(),
                auth=self._auth(),
                timeout=self.timeout,
                **kwargs,
            )
            if response.status_code == 429 and attempt < self.max_retries:
                wait = float(response.headers.get("Retry-After", 2**attempt))
                logger.warning("Rate limited by %s, waiting %.1fs (attempt %d)", url, wait, attempt)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json() if response.content else {}
        raise RuntimeError(f"Exceeded {self.max_retries} retries calling {url}")

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
