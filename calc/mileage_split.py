"""Core P0/P1/P2 calculation.

P0 = miles with the app off (personal use)
P1 = miles with the app on but not on a job
P2 = miles while on a job

The hard constraint the insurer checks first: P0 + P1 + P2 must equal the
GPS total exactly, per trip and therefore per car per month. This module
allocates each trip's miles proportionally by time-overlap with the
renter's app-status timeline, then forces exact reconciliation at the
rounding precision the report is published at (see `residual correction`
below) so floating-point drift never breaks that identity.

This is a first-pass implementation of the method described in the job
brief, built without the client's written spec/prototype or a known-answer
test case (neither was available at scaffold time). Treat the overlap
precedence rule and the "uncovered time defaults to P0" assumption below as
things to validate against the real spec, not as settled behavior.
"""

from dataclasses import dataclass
from datetime import datetime

REPORT_PRECISION = 2  # matches NUMERIC(8,2) miles columns in the schema

# When a renter has more than one status recorded for the same instant
# (e.g. Argyle logs "on_available" and "on_job" from two overlapping
# events), on_job wins, then on_available, then off. Confirm this
# precedence against the real spec - it is a "difficult case" the job
# brief calls out explicitly.
STATUS_PRIORITY = ("on_job", "on_available", "off")
STATUS_TO_BUCKET = {"off": "P0", "on_available": "P1", "on_job": "P2"}


@dataclass(frozen=True)
class Trip:
    trip_id: str
    car_id: str
    start_utc: datetime
    end_utc: datetime
    miles: float


@dataclass(frozen=True)
class StatusInterval:
    renter_id: str
    start_utc: datetime
    end_utc: datetime
    status: str  # "off" | "on_available" | "on_job"


def resolve_overlaps(intervals: list[StatusInterval]) -> list[StatusInterval]:
    """Collapses possibly-overlapping intervals into a non-overlapping
    timeline, resolving simultaneous statuses via STATUS_PRIORITY so a
    trip's miles are never counted into more than one bucket."""
    if not intervals:
        return []

    priority_rank = {status: i for i, status in enumerate(STATUS_PRIORITY)}
    boundaries = sorted({iv.start_utc for iv in intervals} | {iv.end_utc for iv in intervals})

    resolved = []
    for seg_start, seg_end in zip(boundaries, boundaries[1:]):
        if seg_end <= seg_start:
            continue
        active = [iv for iv in intervals if iv.start_utc <= seg_start and iv.end_utc >= seg_end]
        if not active:
            continue
        winner = min(active, key=lambda iv: priority_rank.get(iv.status, len(STATUS_PRIORITY)))
        resolved.append(StatusInterval(winner.renter_id, seg_start, seg_end, winner.status))
    return resolved


def split_trip_miles(trip: Trip, intervals: list[StatusInterval]) -> dict[str, float]:
    """Allocates one trip's miles across P0/P1/P2, proportional to how much
    of the trip's duration overlaps each status. Assumes constant speed
    across the trip (no odometer breadcrumbs to do better without GPS
    ping-level detail - revisit if the GPS source provides that).

    Any part of the trip not covered by a known status interval is treated
    as P0: no app connection recorded == presumed personal use. This also
    matches the "renters who haven't connected their app" tracking the
    client wants surfaced weekly.
    """
    duration = (trip.end_utc - trip.start_utc).total_seconds()
    if duration <= 0:
        return {"P0": round(trip.miles, REPORT_PRECISION), "P1": 0.0, "P2": 0.0}

    resolved = resolve_overlaps(intervals)

    buckets = {"P0": 0.0, "P1": 0.0, "P2": 0.0}
    covered_seconds = 0.0
    for interval in resolved:
        overlap_start = max(trip.start_utc, interval.start_utc)
        overlap_end = min(trip.end_utc, interval.end_utc)
        overlap_seconds = (overlap_end - overlap_start).total_seconds()
        if overlap_seconds <= 0:
            continue
        bucket = STATUS_TO_BUCKET.get(interval.status, "P0")
        buckets[bucket] += trip.miles * (overlap_seconds / duration)
        covered_seconds += overlap_seconds

    uncovered_seconds = max(duration - covered_seconds, 0.0)
    buckets["P0"] += trip.miles * (uncovered_seconds / duration)

    return _reconcile_exact(buckets, trip.miles)


def _reconcile_exact(buckets: dict[str, float], total_miles: float) -> dict[str, float]:
    """Rounds each bucket to report precision, then nudges the largest
    bucket by whatever residual rounding introduced, so the three buckets
    always sum to exactly `total_miles` at that precision - not just close.
    """
    rounded = {k: round(v, REPORT_PRECISION) for k, v in buckets.items()}
    total_miles = round(total_miles, REPORT_PRECISION)
    residual = round(total_miles - sum(rounded.values()), REPORT_PRECISION)
    if residual != 0:
        largest_bucket = max(rounded, key=rounded.get)
        rounded[largest_bucket] = round(rounded[largest_bucket] + residual, REPORT_PRECISION)
    return rounded


def aggregate_monthly(trip_splits: list[dict[str, float]]) -> dict[str, float]:
    """Sums a car's per-trip splits for one month. Since every trip already
    reconciles exactly, the monthly total does too - no further correction
    needed here.
    """
    totals = {"P0": 0.0, "P1": 0.0, "P2": 0.0}
    for split in trip_splits:
        for bucket in totals:
            totals[bucket] = round(totals[bucket] + split[bucket], REPORT_PRECISION)
    totals["total"] = round(sum(totals[b] for b in ("P0", "P1", "P2")), REPORT_PRECISION)
    return totals
