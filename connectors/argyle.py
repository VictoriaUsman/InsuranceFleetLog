"""Argyle API client.

Argyle authenticates with HTTP Basic Auth (API token as username, API secret
as password) and paginates DRF-style, returning a full `next` URL in each
page rather than a bare cursor.

NOTE: endpoint paths and field names below follow Argyle's documented v2
conventions but have not been verified against a live account yet (no API
credentials/spec available at scaffold time - see README). Confirm against
https://docs.argyle.com once credentials arrive, before trusting field names
in `transform`.
"""

import hashlib
import hmac
from datetime import datetime
from typing import Iterator

from requests.auth import HTTPBasicAuth

from config.settings import settings
from connectors.base import RestConnector


class ArgyleClient(RestConnector):
    base_url = settings.argyle_base_url

    def __init__(self, api_token: str | None = None, api_secret: str | None = None):
        super().__init__()
        self.api_token = api_token or settings.argyle_api_token
        self.api_secret = api_secret or settings.argyle_api_secret

    def _headers(self) -> dict:
        return {"Accept": "application/json"}

    def _auth(self):
        return HTTPBasicAuth(self.api_token, self.api_secret)

    def get_activities(self, since: datetime | None = None) -> Iterator[dict]:
        """Driving-activity records: app-on/app-off and on-job status per user."""
        params = {"updated_after": since.isoformat()} if since else {}
        yield from self.paginate("/v2/activities", params=params)

    def get_profiles(self) -> Iterator[dict]:
        """Renter identity records - used to map argyle_user_id -> renter."""
        yield from self.paginate("/v2/profiles")

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature_header: str, webhook_secret: str) -> bool:
        expected = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)
