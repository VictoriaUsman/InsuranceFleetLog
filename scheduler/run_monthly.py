"""Cron/Task Scheduler entrypoint for the automated monthly run:
extract (GPS + Argyle + GHL) -> transform -> load -> calculate -> report.

NOT wired end-to-end yet: connectors/gohighlevel.py's get_rental_records()
and the Argyle field mapping in etl/transform.py are placeholders pending
real API access (see README "Current status"). Once those are filled in,
schedule this with cron / Windows Task Scheduler, e.g. monthly on the 1st:

    0 6 1 * * cd /path/to/InsuranceLog && python -m scheduler.run_monthly

Until then, use scripts/manual_report.py against local CSV exports.
"""

import argparse
import calendar
from datetime import date

from connectors.argyle import ArgyleClient
from connectors.gohighlevel import GoHighLevelClient
from db.connection import session_scope
from db.models import Car, MonthlyReport
from calc.mileage_split import StatusInterval, Trip, aggregate_monthly, split_trip_miles
from etl.extract import extract_argyle_activities, extract_ghl_rental_records
from etl.transform import normalize_argyle_activities
from reports.excel_report import write_report


def previous_month(today: date) -> str:
    year, month = today.year, today.month
    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    return f"{prev_year:04d}-{prev_month:02d}"


def run(month: str, output_dir: str = "reports/output"):
    year, mon = (int(part) for part in month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]
    month_start = date(year, mon, 1)
    month_end = date(year, mon, days_in_month)

    argyle_client = ArgyleClient()
    ghl_client = GoHighLevelClient()

    # 1. Extract + normalize Argyle status intervals for the window.
    raw_activities = extract_argyle_activities(argyle_client, since=month_start)
    status_df = normalize_argyle_activities(raw_activities)

    # 2. Extract rental assignments (car <-> renter <-> date range).
    #    Raises NotImplementedError until connectors/gohighlevel.py is
    #    pointed at the client's actual GHL object - see that module.
    rental_records = extract_ghl_rental_records(ghl_client)

    # 3. Pull trips for every active car and split each one.
    #    GPS extraction is vendor-specific and not wired up yet (see
    #    connectors/gps/) - this loop assumes trips are already loaded
    #    into the `trips` table by a prior GPS sync step.
    with session_scope() as session:
        cars = session.query(Car).filter(Car.active.is_(True)).all()

    car_rows = []
    for car in cars:
        # TODO: query trips for this car/month, resolve the renter(s) via
        # rental_records, gather that renter's status_df intervals, call
        # split_trip_miles per trip, then aggregate_monthly. Stubbed
        # pending the two TODOs above.
        pass

    xlsx_path, csv_path = write_report(car_rows, output_dir, month)

    with session_scope() as session:
        for row in car_rows:
            session.merge(
                MonthlyReport(
                    car_id=row["car_id"],
                    report_month=month_start,
                    p0_miles=row["P0"],
                    p1_miles=row["P1"],
                    p2_miles=row["P2"],
                    total_miles=row["total"],
                )
            )

    print(f"Wrote {xlsx_path}")
    print(f"Wrote {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Run the automated monthly mileage report.")
    parser.add_argument("--month", help="YYYY-MM, defaults to last month")
    parser.add_argument("--output-dir", default="reports/output")
    args = parser.parse_args()

    month = args.month or previous_month(date.today())
    run(month, args.output_dir)


if __name__ == "__main__":
    main()
