from datetime import date, datetime
from typing import Optional

from connectors.argyle import ArgyleClient
from connectors.gohighlevel import GoHighLevelClient
from connectors.gps.base_gps import GpsConnector


def extract_gps_trips(gps_connector: GpsConnector, start: date, end: date) -> list[dict]:
    return list(gps_connector.fetch_trips(start, end))


def extract_argyle_activities(client: ArgyleClient, since: Optional[datetime] = None) -> list[dict]:
    return list(client.get_activities(since=since))


def extract_ghl_rental_records(client: GoHighLevelClient) -> list[dict]:
    return list(client.get_rental_records())
