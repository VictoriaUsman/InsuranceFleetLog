"""Idempotent upserts so re-running extract/load for a date range (e.g. after
a late GPS sync) never creates duplicate trips or status intervals.
"""

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.connection import session_scope
from db.models import AppStatusInterval, Trip


def load_trips(car_id: int, trips_df: pd.DataFrame) -> int:
    if trips_df.empty:
        return 0
    rows = [
        {
            "car_id": car_id,
            "start_time_utc": row.start_time_utc,
            "end_time_utc": row.end_time_utc,
            "miles": row.miles,
            "source": "gps",
        }
        for row in trips_df.itertuples()
    ]
    with session_scope() as session:
        stmt = pg_insert(Trip).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["car_id", "start_time_utc", "end_time_utc"]
        )
        result = session.execute(stmt)
        return result.rowcount


def load_status_intervals(renter_id: int, intervals_df: pd.DataFrame) -> int:
    if intervals_df.empty:
        return 0
    rows = [
        {
            "renter_id": renter_id,
            "start_time_utc": row.start_time_utc,
            "end_time_utc": row.end_time_utc,
            "status": row.status,
            "source": "argyle",
        }
        for row in intervals_df.itertuples()
    ]
    with session_scope() as session:
        session.bulk_insert_mappings(AppStatusInterval, rows)
        return len(rows)
