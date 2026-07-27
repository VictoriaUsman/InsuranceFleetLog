"""Timezone and shape normalization. Everything downstream of this module
works in UTC only - GPS is the one source that arrives in Florida local
time and must be converted here, once, before it touches the database.
"""

from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import settings

FLEET_TZ = ZoneInfo(settings.fleet_timezone)


def localize_gps_trips(raw_trips: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(raw_trips))
    if df.empty:
        return df
    df["start_time_utc"] = df["start_time_local"].apply(_local_to_utc)
    df["end_time_utc"] = df["end_time_local"].apply(_local_to_utc)
    return df[["gps_device_id", "start_time_utc", "end_time_utc", "miles"]]


def _local_to_utc(naive_value) -> pd.Timestamp:
    """DST edge cases (documented default, revisit against the real spec):
    - fall-back (1am-2am happens twice): ambiguous=False assumes standard
      time (the second occurrence). Low-volume overnight hour, but flag any
      trip that starts/ends in that window if this ever needs to be exact.
    - spring-forward (2am-3am doesn't exist): shift_forward. Should never
      occur in real GPS data, only bad input.
    """
    ts = pd.Timestamp(naive_value)
    localized = ts.tz_localize(FLEET_TZ, ambiguous=False, nonexistent="shift_forward")
    return localized.tz_convert("UTC")


def normalize_argyle_activities(raw_activities: Iterable[dict]) -> pd.DataFrame:
    """Argyle timestamps are already UTC - no tz conversion needed.

    NOTE: field names (`user_id`, `start_time`, `end_time`, `status`) are
    placeholders - confirm against the real Argyle payload shape once
    credentials/spec are available (see connectors/argyle.py).
    """
    df = pd.DataFrame(list(raw_activities))
    if df.empty:
        return df
    df["start_time_utc"] = pd.to_datetime(df["start_time"], utc=True)
    df["end_time_utc"] = pd.to_datetime(df["end_time"], utc=True)
    return df[["user_id", "start_time_utc", "end_time_utc", "status"]].rename(
        columns={"user_id": "argyle_user_id"}
    )
