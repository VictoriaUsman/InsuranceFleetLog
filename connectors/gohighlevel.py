"""GoHighLevel (GHL) API client.

GHL's v2 API uses a Bearer token plus a required `Version` header, and
paginates via a `startAfterId`/`startAfter` cursor pair.

NOTE: GHL has no built-in "car rental" object. Which renter had which car on
which dates is presumably tracked either as Opportunities in a pipeline, a
Custom Object, or custom fields on the Contact - we don't yet know which, so
`get_rental_records` is a placeholder that should be pointed at whichever of
`get_opportunities` / `get_custom_objects` matches the client's actual setup
once we can see their GHL account.
"""

from typing import Iterator

from config.settings import settings
from connectors.base import RestConnector

GHL_API_VERSION = "2021-07-28"


class GoHighLevelClient(RestConnector):
    base_url = "https://services.leadconnectorhq.com"

    def __init__(self, api_key: str | None = None, location_id: str | None = None):
        super().__init__()
        self.api_key = api_key or settings.ghl_api_key
        self.location_id = location_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Version": GHL_API_VERSION,
            "Accept": "application/json",
        }

    def get_contacts(self) -> Iterator[dict]:
        params = {"locationId": self.location_id} if self.location_id else {}
        yield from self.paginate(
            "/contacts/", params=params, page_param="startAfterId", results_key="contacts"
        )

    def get_opportunities(self, pipeline_id: str | None = None) -> Iterator[dict]:
        params = {"location_id": self.location_id}
        if pipeline_id:
            params["pipeline_id"] = pipeline_id
        yield from self.paginate(
            "/opportunities/search", params=params, page_param="startAfterId", results_key="opportunities"
        )

    def get_custom_objects(self, object_key: str) -> Iterator[dict]:
        params = {"locationId": self.location_id}
        yield from self.paginate(
            f"/objects/{object_key}/records",
            params=params,
            page_param="startAfterId",
            results_key="records",
        )

    def get_rental_records(self) -> Iterator[dict]:
        """Placeholder - see module docstring. Wire this to whichever GHL
        object actually holds car/renter/date-range data once known."""
        raise NotImplementedError(
            "Confirm whether rental assignments live in Opportunities, a "
            "Custom Object, or Contact custom fields, then implement here."
        )
