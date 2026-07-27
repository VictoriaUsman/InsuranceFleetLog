"""Produces the monthly P0/P1/P2 report from local CSV exports - no
database, no live API access needed. This is the "get a report out this
week" path; the scheduled pipeline (scheduler/run_monthly.py) replaces the
three CSVs here with live connector pulls once credentials exist.

Run from the repo root:
    python -m scripts.manual_report --gps-csv gps.csv --assignments-csv assignments.csv \\
        --argyle-csv argyle.csv --month 2026-06

Expected CSV columns:
    gps-csv:         device_id, start_time, end_time, miles
                     (start/end are Florida local time, naive)
    assignments-csv: device_id, car_id, vin, renter_id, start_date, end_date
                     (end_date blank if the assignment is still active)
    argyle-csv:      renter_id, start_time, end_time, status
                     (status: off | on_available | on_job, times in UTC;
                     omit --argyle-csv entirely to treat all miles as P0)
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from calc.mileage_split import StatusInterval, Trip, aggregate_monthly, split_trip_miles
from etl.transform import localize_gps_trips
from reports.excel_report import write_report


def _parse_month(month_str: str) -> tuple[date, date]:
    year, month = (int(part) for part in month_str.split("-"))
    start = date(year, month, 1)
    next_month_year = year + (1 if month == 12 else 0)
    next_month = 1 if month == 12 else month + 1
    end = date(next_month_year, next_month, 1)
    return start, end


def _load_assignments(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["start_date", "end_date"])


def _load_argyle_intervals(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["renter_id", "start_time", "end_time", "status"])
    df = pd.read_csv(path)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True, format="ISO8601")
    df["end_time"] = pd.to_datetime(df["end_time"], utc=True, format="ISO8601")
    return df


def _find_assignment(assignments: pd.DataFrame, device_id: str, trip_date: date):
    trip_ts = pd.Timestamp(trip_date)
    matches = assignments[
        (assignments["device_id"] == device_id)
        & (assignments["start_date"] <= trip_ts)
        & (assignments["end_date"].isna() | (assignments["end_date"] >= trip_ts))
    ]
    return None if matches.empty else matches.iloc[0]


def build_report(gps_csv: str, assignments_csv: str, argyle_csv: str | None, month: str, output_dir: str):
    start_date, end_date = _parse_month(month)

    gps_df = pd.read_csv(gps_csv)
    raw_trips = gps_df.rename(
        columns={
            "device_id": "gps_device_id",
            "start_time": "start_time_local",
            "end_time": "end_time_local",
        }
    ).to_dict("records")
    trips_df = localize_gps_trips(raw_trips)
    if trips_df.empty:
        raise SystemExit("No GPS trips found in input file.")

    in_month = (trips_df["start_time_utc"].dt.date >= start_date) & (
        trips_df["start_time_utc"].dt.date < end_date
    )
    trips_df = trips_df.loc[in_month]
    if trips_df.empty:
        raise SystemExit(f"No GPS trips fall within {month}.")

    assignments = _load_assignments(assignments_csv)
    argyle = _load_argyle_intervals(argyle_csv)

    per_car_splits: dict = {}
    per_car_vin: dict = {}
    unmatched_trips = 0

    for row in trips_df.itertuples():
        assignment = _find_assignment(assignments, row.gps_device_id, row.start_time_utc.date())
        if assignment is None:
            unmatched_trips += 1
            continue

        car_id = assignment["car_id"]
        per_car_vin[car_id] = assignment.get("vin", "")

        renter_intervals = argyle[argyle["renter_id"] == assignment["renter_id"]]
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
        per_car_splits.setdefault(car_id, []).append(split)

    if unmatched_trips:
        print(f"WARNING: {unmatched_trips} trip(s) had no matching rental assignment and were excluded.")

    car_rows = []
    for car_id, splits in per_car_splits.items():
        totals = aggregate_monthly(splits)
        car_rows.append(
            {
                "car_id": car_id,
                "vin": per_car_vin.get(car_id, ""),
                "P0": totals["P0"],
                "P1": totals["P1"],
                "P2": totals["P2"],
                "total": totals["total"],
            }
        )

    xlsx_path, csv_path = write_report(car_rows, output_dir, month)
    print(f"Wrote {xlsx_path}")
    print(f"Wrote {csv_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gps-csv", required=True)
    parser.add_argument("--assignments-csv", required=True)
    parser.add_argument("--argyle-csv", default=None)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output-dir", default="reports/output")
    args = parser.parse_args()

    build_report(args.gps_csv, args.assignments_csv, args.argyle_csv, args.month, args.output_dir)


if __name__ == "__main__":
    main()
