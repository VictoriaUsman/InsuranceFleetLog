from abc import ABC, abstractmethod
from datetime import date
from typing import Iterator, TypedDict


class RawTrip(TypedDict):
    gps_device_id: str
    start_time_local: str  # ISO string, Florida local time, naive
    end_time_local: str
    miles: float


class GpsConnector(ABC):
    """Vendor-agnostic interface. Once the tracker vendor is confirmed,
    implement one concrete subclass per vendor (API-based) alongside, or
    instead of, CsvGpsConnector."""

    @abstractmethod
    def fetch_trips(self, start: date, end: date) -> Iterator[RawTrip]:
        ...
