"""Inspect the supplied CSV files without interpreting missing hours or changing data."""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "pjm_constraints_2024_2026.csv": ["opr_date", "opr_hour", "flowgate"],
    "pjm_fuel_gen_2024_2026.csv": ["opr_date", "opr_hour", "fuel_type"],
    "pjm_hourly_lmps_2024_2026.csv": ["opr_date", "hour_ending", "pnode_id"],
    "PJM_hourly_solar_actuals_2024_2026.csv": ["opr_timestamp", "area"],
    "PJM_hourly_wind_actuals_2024_2026.csv": ["opr_timestamp", "area"],
    "PJM_load_2024_2026.csv": ["opr_date", "opr_hour", "region_zone", "load_type"],
}


def profile(frame: pd.DataFrame, keys: list[str]) -> dict:
    """Return schema and coverage facts; proposed keys still require domain review."""
    result = {
        "rows": len(frame),
        "columns": frame.columns.tolist(),
        "key_columns": keys,
        "duplicate_key_rows": int(frame.duplicated(keys, keep=False).sum()),
        "null_counts": {column: int(n) for column, n in frame.isna().sum().items() if n},
    }
    if "opr_date" in frame:
        result["date_range"] = [str(frame.opr_date.min()), str(frame.opr_date.max())]
        result["observed_dates"] = int(frame.opr_date.nunique())
    for column in ["opr_hour", "hour_ending"]:
        if column in frame:
            result[column] = sorted(int(value) for value in frame[column].dropna().unique())
    for column in ["flowgate", "fuel_type", "pnode_name", "region_zone", "area"]:
        if column in frame:
            result[f"{column}_row_counts"] = {
                str(value): int(count)
                for value, count in frame[column].value_counts().sort_index().items()
            }
    if "avg_shadow_price" in frame:
        values = frame.avg_shadow_price
        result["shadow_price_sign_counts"] = {
            "negative": int((values < 0).sum()),
            "zero": int((values == 0).sum()),
            "positive": int((values > 0).sum()),
        }
    if "solar_value" in frame:
        result["negative_solar_rows"] = int((frame.solar_value < 0).sum())
    if "total_lmp_rt" in frame:
        difference = (
            frame.total_lmp_rt
            - frame.system_energy_price_rt
            - frame.congestion_price_rt
            - frame.marginal_loss_price_rt
        )
        result["max_abs_lmp_component_difference"] = float(difference.abs().max())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "results/base_case/data_audit.json")
    args = parser.parse_args()
    if not args.data_dir.is_dir():
        parser.error(f"Data directory not found: {args.data_dir}. See README.md for input setup.")
    missing = sorted(filename for filename in DATASETS if not (args.data_dir / filename).is_file())
    if missing:
        parser.error(f"Data directory is missing expected CSVs: {', '.join(missing)}")

    report = {
        "data_directory": str(args.data_dir.resolve()),
        "interpretation": "Raw-file audit; missing-hour and timezone semantics remain unconfirmed.",
        "datasets": {},
    }
    for filename, keys in DATASETS.items():
        frame = pd.read_csv(
            args.data_dir / filename,
            low_memory=False,
        )
        report["datasets"][filename] = profile(frame, keys)
        print(f"{filename}: {len(frame):,} rows, {len(frame.columns)} columns")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Audit written to {args.output}")


if __name__ == "__main__":
    main()
