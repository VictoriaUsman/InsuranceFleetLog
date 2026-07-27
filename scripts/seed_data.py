"""Generates a synthetic month of fleet data (20 cars) so the pipeline and
dashboard can be demonstrated end-to-end before any real GPS/Argyle/GHL
access exists. Output is fake but internally consistent - it exercises the
same CSV formats scripts/manual_report.py expects.

Run from the repo root:
    python -m scripts.seed_data
"""

import csv
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FLEET_TZ = ZoneInfo("America/New_York")
MONTH_START = date(2026, 6, 1)
MONTH_END = date(2026, 6, 30)
NUM_CARS = 20
OUT_DIR = Path(__file__).resolve().parent.parent / "seed"

random.seed(42)


def local_to_utc(naive_dt: datetime) -> datetime:
    return naive_dt.replace(tzinfo=FLEET_TZ).astimezone(timezone.utc)


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def build_fleet():
    """cars[i] = {car_id, vin, device_id}; assignments = list of dicts
    covering the whole month, with 3 cars getting a mid-month renter swap."""
    cars = [
        {"car_id": i + 1, "vin": f"1FLEET{i+1:04d}FL{2026}", "device_id": f"GPS-{i+1:03d}"}
        for i in range(NUM_CARS)
    ]

    assignments = []
    renter_id_counter = 1
    swap_car_ids = {3, 9, 15}  # a few cars change hands mid-month

    for car in cars:
        if car["car_id"] in swap_car_ids:
            swap_day = 15
            assignments.append(
                {
                    "device_id": car["device_id"],
                    "car_id": car["car_id"],
                    "vin": car["vin"],
                    "renter_id": f"R{renter_id_counter}",
                    "start_date": MONTH_START.isoformat(),
                    "end_date": date(2026, 6, swap_day).isoformat(),
                }
            )
            renter_id_counter += 1
            assignments.append(
                {
                    "device_id": car["device_id"],
                    "car_id": car["car_id"],
                    "vin": car["vin"],
                    "renter_id": f"R{renter_id_counter}",
                    "start_date": date(2026, 6, swap_day + 1).isoformat(),
                    "end_date": "",
                }
            )
            renter_id_counter += 1
        else:
            assignments.append(
                {
                    "device_id": car["device_id"],
                    "car_id": car["car_id"],
                    "vin": car["vin"],
                    "renter_id": f"R{renter_id_counter}",
                    "start_date": MONTH_START.isoformat(),
                    "end_date": "",
                }
            )
            renter_id_counter += 1

    return cars, assignments


PEAK_HOURS = [7, 8, 9, 11, 12, 17, 18, 19, 20, 21]


def renter_for_day(assignments, device_id, day):
    for a in assignments:
        if a["device_id"] != device_id:
            continue
        start = date.fromisoformat(a["start_date"])
        end = date.fromisoformat(a["end_date"]) if a["end_date"] else MONTH_END
        if start <= day <= end:
            return a["renter_id"]
    return None


def build_trips_and_status(cars, assignments, disconnected_renters):
    gps_rows = []
    argyle_rows = []

    all_renter_ids = sorted({a["renter_id"] for a in assignments})

    for car in cars:
        # each car drives 3-6 days a week, 1-4 trips per driving day
        for day in daterange(MONTH_START, MONTH_END):
            if random.random() < 0.28:  # ~2 rest days/week
                continue
            renter_id = renter_for_day(assignments, car["device_id"], day)
            if renter_id is None:
                continue

            num_trips = random.choices([1, 2, 3, 4], weights=[2, 4, 3, 1])[0]
            connected = renter_id not in disconnected_renters

            for _ in range(num_trips):
                hour = random.choice(PEAK_HOURS) if random.random() < 0.75 else random.randint(5, 23)
                minute = random.randint(0, 59)
                start_local = datetime(day.year, day.month, day.day, hour, minute)
                duration_min = random.randint(8, 70)
                end_local = start_local + timedelta(minutes=duration_min)

                avg_speed_mph = random.uniform(18, 34)
                miles = round((duration_min / 60) * avg_speed_mph * random.uniform(0.9, 1.1), 1)

                gps_rows.append(
                    {
                        "device_id": car["device_id"],
                        "start_time": start_local.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_time": end_local.strftime("%Y-%m-%d %H:%M:%S"),
                        "miles": miles,
                    }
                )

                if connected and random.random() < 0.8:
                    start_utc = local_to_utc(start_local)
                    end_utc = local_to_utc(end_local)
                    argyle_rows.extend(_status_segments(renter_id, start_utc, end_utc))

    return gps_rows, argyle_rows


def _status_segments(renter_id, start_utc, end_utc):
    """Splits one trip's UTC window into 1-2 app-status segments."""
    total_seconds = (end_utc - start_utc).total_seconds()
    if random.random() < 0.4 or total_seconds < 600:
        status = random.choices(["on_available", "on_job"], weights=[3, 5])[0]
        return [
            {
                "renter_id": renter_id,
                "start_time": start_utc.isoformat().replace("+00:00", "Z"),
                "end_time": end_utc.isoformat().replace("+00:00", "Z"),
                "status": status,
            }
        ]

    split_point = start_utc + timedelta(seconds=total_seconds * random.uniform(0.3, 0.7))
    first_status, second_status = random.sample(["on_available", "on_job"], 2)
    return [
        {
            "renter_id": renter_id,
            "start_time": start_utc.isoformat().replace("+00:00", "Z"),
            "end_time": split_point.isoformat().replace("+00:00", "Z"),
            "status": first_status,
        },
        {
            "renter_id": renter_id,
            "start_time": split_point.isoformat().replace("+00:00", "Z"),
            "end_time": end_utc.isoformat().replace("+00:00", "Z"),
            "status": second_status,
        },
    ]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cars, assignments = build_fleet()

    all_renter_ids = sorted({a["renter_id"] for a in assignments})
    disconnected_renters = set(random.sample(all_renter_ids, 4))

    gps_rows, argyle_rows = build_trips_and_status(cars, assignments, disconnected_renters)

    write_csv(OUT_DIR / "gps_trips.csv", gps_rows, ["device_id", "start_time", "end_time", "miles"])
    write_csv(
        OUT_DIR / "rental_assignments.csv",
        assignments,
        ["device_id", "car_id", "vin", "renter_id", "start_date", "end_date"],
    )
    write_csv(OUT_DIR / "argyle_status.csv", argyle_rows, ["renter_id", "start_time", "end_time", "status"])

    print(f"{len(cars)} cars, {len(assignments)} assignments, {len(gps_rows)} trips, {len(argyle_rows)} status intervals")
    print(f"Disconnected renters (no Argyle data all month): {sorted(disconnected_renters)}")
    print(f"Wrote CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
