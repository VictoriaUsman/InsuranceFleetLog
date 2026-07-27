"""Fallback GPS connector for vendors with no usable API - reads a manual
CSV export instead. Works for this week's manual report regardless of which
tracker vendor is confirmed; swap in a real API-based connector later if one
turns out to be available.

Expected columns (rename via `column_map` if the export differs):
    device_id, start_time, end_time, miles
"""

from datetime import date
from typing import Iterator

import pandas as pd

from connectors.gps.base_gps import GpsConnector, RawTrip

DEFAULT_COLUMN_MAP = {
    "device_id": "gps_device_id",
    "start_time": "start_time_local",
    "end_time": "end_time_local",
    "miles": "miles",
}


class CsvGpsConnector(GpsConnector):
    def __init__(self, csv_path: str, column_map: dict | None = None):
        self.csv_path = csv_path
        self.column_map = column_map or DEFAULT_COLUMN_MAP

    def fetch_trips(self, start: date, end: date) -> Iterator[RawTrip]:
        df = pd.read_csv(self.csv_path)
        df = df.rename(columns=self.column_map)
        df["start_time_local"] = pd.to_datetime(df["start_time_local"])
        df["end_time_local"] = pd.to_datetime(df["end_time_local"])

        mask = (df["start_time_local"].dt.date >= start) & (df["start_time_local"].dt.date <= end)
        for _, row in df.loc[mask].iterrows():
            yield RawTrip(
                gps_device_id=str(row["gps_device_id"]),
                start_time_local=row["start_time_local"].isoformat(),
                end_time_local=row["end_time_local"].isoformat(),
                miles=float(row["miles"]),
            )
