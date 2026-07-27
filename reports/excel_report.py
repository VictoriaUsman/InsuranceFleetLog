"""Generates the monthly Excel + CSV report the insurer receives: one row
per car, columns for P0/P1/P2/total miles, plus a fleet-total row.
"""

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

COLUMNS = ["car_id", "vin", "P0", "P1", "P2", "total"]


def build_report_dataframe(car_rows: list[dict]) -> pd.DataFrame:
    """car_rows: one dict per car, e.g.
    {"car_id": 1, "vin": "...", "P0": 120.4, "P1": 30.0, "P2": 410.2, "total": 560.6}
    """
    df = pd.DataFrame(car_rows, columns=COLUMNS)
    totals = {
        "car_id": "FLEET TOTAL",
        "vin": "",
        "P0": round(df["P0"].sum(), 2),
        "P1": round(df["P1"].sum(), 2),
        "P2": round(df["P2"].sum(), 2),
        "total": round(df["total"].sum(), 2),
    }
    return pd.concat([df, pd.DataFrame([totals])], ignore_index=True)


def write_report(car_rows: list[dict], output_dir: str, month_label: str) -> tuple[Path, Path]:
    """month_label: e.g. "2026-06". Writes both an .xlsx and a .csv and
    returns their paths."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_report_dataframe(car_rows)

    xlsx_path = out_dir / f"mileage_report_{month_label}.xlsx"
    csv_path = out_dir / f"mileage_report_{month_label}.csv"

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=month_label, index=False)
        sheet = writer.sheets[month_label]
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column_cells in sheet.columns:
            width = max(len(str(cell.value)) for cell in column_cells) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = width

    return xlsx_path, csv_path
