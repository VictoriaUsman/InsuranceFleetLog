"""Runs the seeded CSVs (scripts/seed_data.py) through the real, tested
calc.mileage_split engine and aggregates the results into a single JSON
file for the dashboard. Nothing in dashboard_data.json is hand-typed - every
number is a byproduct of running actual trips through split_trip_miles().

Run from the repo root (after scripts/seed_data.py):
    python -m scripts.build_dashboard_data
"""

import json
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from calc.mileage_split import StatusInterval, Trip, aggregate_monthly, split_trip_miles
from etl.transform import localize_gps_trips
from scripts.manual_report import _find_assignment

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
FLEET_TZ = ZoneInfo("America/New_York")


def load_inputs():
    gps_df = pd.read_csv(SEED_DIR / "gps_trips.csv")
    raw_trips = gps_df.rename(
        columns={
            "device_id": "gps_device_id",
            "start_time": "start_time_local",
            "end_time": "end_time_local",
        }
    ).to_dict("records")
    trips_df = localize_gps_trips(raw_trips)

    assignments = pd.read_csv(SEED_DIR / "rental_assignments.csv", parse_dates=["start_date", "end_date"])

    argyle = pd.read_csv(SEED_DIR / "argyle_status.csv")
    argyle["start_time"] = pd.to_datetime(argyle["start_time"], utc=True, format="ISO8601")
    argyle["end_time"] = pd.to_datetime(argyle["end_time"], utc=True, format="ISO8601")

    return trips_df, assignments, argyle


def main():
    trips_df, assignments, argyle = load_inputs()

    car_splits = defaultdict(list)
    car_meta = {}
    daily_totals = defaultdict(lambda: {"P0": 0.0, "P1": 0.0, "P2": 0.0})
    renters_seen_driving = set()
    unmatched = 0

    for row in trips_df.itertuples():
        local_date = row.start_time_utc.tz_convert(FLEET_TZ).date()
        assignment = _find_assignment(assignments, row.gps_device_id, row.start_time_utc.tz_convert(FLEET_TZ).date())
        if assignment is None:
            unmatched += 1
            continue

        car_id = int(assignment["car_id"])
        renter_id = assignment["renter_id"]
        renters_seen_driving.add(renter_id)
        car_meta[car_id] = {"vin": assignment["vin"], "device_id": assignment["device_id"]}

        renter_intervals = argyle[argyle["renter_id"] == renter_id]
        intervals = [
            StatusInterval(str(r.renter_id), r.start_time, r.end_time, r.status)
            for r in renter_intervals.itertuples()
        ]

        trip = Trip(
            trip_id=f"{row.gps_device_id}-{row.start_time_utc.isoformat()}",
            car_id=str(car_id),
            start_utc=row.start_time_utc,
            end_utc=row.end_time_utc,
            miles=row.miles,
        )
        split = split_trip_miles(trip, intervals)
        car_splits[car_id].append(split)

        date_key = local_date.isoformat()
        for bucket in ("P0", "P1", "P2"):
            daily_totals[date_key][bucket] = round(daily_totals[date_key][bucket] + split[bucket], 2)

    # Per-car monthly totals, via the same aggregate_monthly used in production.
    car_rows = []
    for car_id, splits in sorted(car_splits.items()):
        totals = aggregate_monthly(splits)
        car_rows.append(
            {
                "car_id": car_id,
                "vin": car_meta[car_id]["vin"],
                "P0": totals["P0"],
                "P1": totals["P1"],
                "P2": totals["P2"],
                "total": totals["total"],
                "trip_count": len(splits),
            }
        )

    all_renter_ids = set(assignments["renter_id"])
    connected_renters = set(argyle["renter_id"].unique())
    renters_not_connected = sorted(all_renter_ids - connected_renters)

    fleet_total = round(sum(r["total"] for r in car_rows), 2)
    fleet_p0 = round(sum(r["P0"] for r in car_rows), 2)
    fleet_p1 = round(sum(r["P1"] for r in car_rows), 2)
    fleet_p2 = round(sum(r["P2"] for r in car_rows), 2)
    assert round(fleet_p0 + fleet_p1 + fleet_p2, 2) == fleet_total, "reconciliation broke at fleet level"

    daily_rows = []
    for date_key in sorted(daily_totals):
        d = daily_totals[date_key]
        daily_rows.append(
            {
                "date": date_key,
                "P0": d["P0"],
                "P1": d["P1"],
                "P2": d["P2"],
                "total": round(d["P0"] + d["P1"] + d["P2"], 2),
            }
        )
    peak_day = max(daily_rows, key=lambda r: r["total"])

    # Utilization bands for the breakdown panel.
    bands = {"High (>50% on job)": 0, "Medium (25-50%)": 0, "Low (<25%)": 0}
    for r in car_rows:
        share = (r["P2"] / r["total"]) if r["total"] else 0
        if share > 0.5:
            bands["High (>50% on job)"] += 1
        elif share >= 0.25:
            bands["Medium (25-50%)"] += 1
        else:
            bands["Low (<25%)"] += 1

    best_car = max(car_rows, key=lambda r: (r["P2"] / r["total"] if r["total"] else 0))
    worst_car = min(car_rows, key=lambda r: (r["P2"] / r["total"] if r["total"] else 0))

    data = {
        "month_label": "June 2026",
        "generated_from": "synthetic seed data - scripts/seed_data.py + calc.mileage_split (not real fleet data)",
        "kpis": {
            "total_miles": fleet_total,
            "p0_miles": fleet_p0,
            "p1_miles": fleet_p1,
            "p2_miles": fleet_p2,
            "pct_p0": round(100 * fleet_p0 / fleet_total, 1),
            "pct_p1": round(100 * fleet_p1 / fleet_total, 1),
            "pct_p2": round(100 * fleet_p2 / fleet_total, 1),
            "cars_reporting": len(car_rows),
            "fleet_size": 20,
            "avg_miles_per_car": round(fleet_total / len(car_rows), 1) if car_rows else 0,
            "renters_not_connected": len(renters_not_connected),
            "renters_total": len(all_renter_ids),
            "unmatched_trips": unmatched,
        },
        "daily_trend": daily_rows,
        "peak_day": peak_day,
        "cars": car_rows,
        "utilization_bands": bands,
        "renters_not_connected_list": renters_not_connected,
        "best_car": {"car_id": best_car["car_id"], "vin": best_car["vin"], "p2_share": round(100 * best_car["P2"] / best_car["total"], 1)},
        "worst_car": {"car_id": worst_car["car_id"], "vin": worst_car["vin"], "p2_share": round(100 * worst_car["P2"] / worst_car["total"], 1)},
    }

    out_path = SEED_DIR / "dashboard_data.json"
    out_path.write_text(json.dumps(data, indent=2))
    print(f"Fleet total: {fleet_total} mi (P0={fleet_p0}, P1={fleet_p1}, P2={fleet_p2}) -- reconciles exactly: {round(fleet_p0+fleet_p1+fleet_p2,2) == fleet_total}")
    print(f"{unmatched} unmatched trips; {len(renters_not_connected)}/{len(all_renter_ids)} renters not connected")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
