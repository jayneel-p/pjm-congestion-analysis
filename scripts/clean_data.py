"""Write minimally cleaned source tables to data/processed; see clean_data.md."""

import argparse
from pathlib import Path

import pandas as pd
from audit_data import DATASETS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
PROCESSED = ROOT / "data/processed"


def clean_hourly(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        dtype={"pnode_id": "string"},
        keep_default_na=False,
        na_values=[""],
        float_precision="round_trip",
    )
    for column in frame.select_dtypes(include=["object", "str", "string"]):
        frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)
    frame["opr_date"] = pd.to_datetime(frame.opr_date, format="%Y-%m-%d")
    if "opr_timestamp" in frame:
        frame["opr_timestamp"] = pd.to_datetime(frame.opr_timestamp, format="%Y-%m-%d %H:%M:%S")
        assert frame.opr_timestamp.equals(
            frame.opr_date + pd.to_timedelta(frame.opr_hour, unit="h")
        )
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, keys in DATASETS.items():
        frame = clean_hourly(RAW / filename)
        assert frame[keys].notna().all().all()
        assert not frame.duplicated(keys).any()
        frame = frame.sort_values(keys, kind="stable").reset_index(drop=True)
        frame.to_csv(args.output_dir / filename, index=False)
        print(f"{filename}: {len(frame):,} rows, {len(frame.columns)} columns")


if __name__ == "__main__":
    main()
