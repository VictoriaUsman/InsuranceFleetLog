from datetime import datetime, timedelta, timezone

import pytest

from calc.mileage_split import StatusInterval, Trip, aggregate_monthly, resolve_overlaps, split_trip_miles

UTC = timezone.utc


def _trip(start_hour: int, minutes: int, miles: float) -> Trip:
    start = datetime(2026, 6, 15, start_hour, 0, tzinfo=UTC)
    return Trip(
        trip_id="t1",
        car_id="car-1",
        start_utc=start,
        end_utc=start + timedelta(minutes=minutes),
        miles=miles,
    )


def _interval(start: datetime, minutes: int, status: str, renter="r1") -> StatusInterval:
    return StatusInterval(renter, start, start + timedelta(minutes=minutes), status)


def test_no_intervals_means_all_personal():
    trip = _trip(9, 60, 42.37)
    result = split_trip_miles(trip, [])
    assert result == {"P0": 42.37, "P1": 0.0, "P2": 0.0}
    assert sum(result.values()) == pytest.approx(trip.miles)


def test_fully_covered_by_one_status():
    trip = _trip(9, 60, 42.37)
    intervals = [_interval(trip.start_utc, 60, "on_job")]
    result = split_trip_miles(trip, intervals)
    assert result == {"P0": 0.0, "P1": 0.0, "P2": 42.37}


def test_split_across_two_statuses_reconciles_exactly():
    trip = _trip(9, 60, 33.33)
    intervals = [
        _interval(trip.start_utc, 30, "on_available"),
        _interval(trip.start_utc + timedelta(minutes=30), 30, "on_job"),
    ]
    result = split_trip_miles(trip, intervals)
    assert result["P1"] == pytest.approx(16.665, abs=0.01)
    assert result["P2"] == pytest.approx(16.665, abs=0.01)
    assert result["P0"] == 0.0
    # the hard requirement: exact, not approximate
    assert round(sum(result.values()), 2) == round(trip.miles, 2)


def test_partial_coverage_leaves_remainder_as_p0():
    trip = _trip(9, 60, 20.0)
    intervals = [_interval(trip.start_utc, 15, "on_job")]  # only first quarter covered
    result = split_trip_miles(trip, intervals)
    assert result["P2"] == pytest.approx(5.0)
    assert result["P0"] == pytest.approx(15.0)
    assert sum(result.values()) == pytest.approx(trip.miles)


def test_overlapping_intervals_resolve_by_priority():
    start = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    intervals = [
        _interval(start, 60, "on_available"),
        _interval(start + timedelta(minutes=20), 20, "on_job"),  # overlaps middle third
    ]
    resolved = resolve_overlaps(intervals)
    statuses_in_order = [iv.status for iv in resolved]
    assert "on_job" in statuses_in_order
    # the on_job segment must win for its whole window, not be split with on_available
    job_segment = next(iv for iv in resolved if iv.status == "on_job")
    assert job_segment.start_utc == start + timedelta(minutes=20)
    assert job_segment.end_utc == start + timedelta(minutes=40)


def test_odd_mileage_still_reconciles_exactly_across_many_trips():
    trips_and_intervals = [
        (_trip(6, 47, 13.7), [_interval(datetime(2026, 6, 15, 6, tzinfo=UTC), 47, "on_available")]),
        (_trip(9, 23, 5.03), [_interval(datetime(2026, 6, 15, 9, tzinfo=UTC), 23, "on_job")]),
        (_trip(12, 90, 61.11), []),
        (_trip(18, 33, 9.99), [_interval(datetime(2026, 6, 15, 18, 10, tzinfo=UTC), 10, "on_job")]),
    ]
    splits = [split_trip_miles(trip, intervals) for trip, intervals in trips_and_intervals]

    for (trip, _), split in zip(trips_and_intervals, splits):
        assert round(sum(split.values()), 2) == round(trip.miles, 2)

    totals = aggregate_monthly(splits)
    expected_total = round(sum(trip.miles for trip, _ in trips_and_intervals), 2)
    assert totals["total"] == expected_total
    assert round(totals["P0"] + totals["P1"] + totals["P2"], 2) == expected_total


def test_zero_duration_trip_defaults_to_p0():
    start = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    trip = Trip("t", "car-1", start, start, miles=0.5)
    result = split_trip_miles(trip, [_interval(start, 10, "on_job")])
    assert result == {"P0": 0.5, "P1": 0.0, "P2": 0.0}
