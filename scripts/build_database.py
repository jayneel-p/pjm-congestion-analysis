"""Build the small source database offline; see build_database.md."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/base_case"
SOURCES = [
    ("constraints", "pjm_constraints_2024_2026.csv", ["flowgate"], "D01", 0),
    ("load", "PJM_load_2024_2026.csv", ["region_zone", "load_type"], "D02", 1),
    ("solar", "PJM_hourly_solar_actuals_2024_2026.csv", ["area"], "D03", 0),
    ("wind", "PJM_hourly_wind_actuals_2024_2026.csv", ["area"], "D04", 0),
    ("fuel_generation", "pjm_fuel_gen_2024_2026.csv", ["fuel_type"], "D05", 0),
    ("lmps", "pjm_hourly_lmps_2024_2026.csv", ["pnode_id"], "D06", 1),
]
PRICES = [
    ("pjm_settled_hourly_lmps", "pjm_settled_hourly_lmps.csv", ["A28"], 0.000003),
    ("pjm_multi_node_hourly_lmps", "pjm_multi_node_hourly_lmps.csv", ["A29", "A32"], 0.020001),
]
FORECAST_PATH = ROOT / "data/raw/forecast_final/rto_2024-01-01_portal.csv"
FORECAST_KEYS = ["evaluated_at_utc", "forecast_hour_beginning_utc", "forecast_area"]


def read_table(path):
    columns = pd.read_csv(path, nrows=0).columns
    identifiers = [c for c in columns if c.endswith(("_id", "_code"))]
    # The frozen multi-node source stores numeric pnode IDs; preserve its existing schema.
    if path.name == "pjm_multi_node_hourly_lmps.csv":
        identifiers.remove("pnode_id")
    return pd.read_csv(
        path,
        dtype=dict.fromkeys(identifiers, "string"),
        keep_default_na=False,
        na_values=[""],
        float_precision="round_trip",
        low_memory=False,
    )


def write_table(connection, name, frame, keys):
    assert frame[keys].notna().all().all(), name
    assert not frame.duplicated(keys).any(), name
    frame.to_sql(name, connection, if_exists="fail", index=False, chunksize=20000)
    columns = ", ".join(f'"{key}"' for key in keys)
    connection.execute(f'CREATE UNIQUE INDEX "{name}_key" ON "{name}" ({columns})')
    saved = pd.read_sql_query(f'SELECT * FROM "{name}"', connection)
    pd.testing.assert_frame_equal(frame.isna(), saved.isna())
    pd.testing.assert_frame_equal(frame, saved.astype(frame.dtypes), check_exact=True)


def compare_existing(connection, name, frame, keys):
    order = ", ".join(f'"{key}"' for key in keys)
    columns = ", ".join(f'"{column}"' for column in frame)
    saved = pd.read_sql_query(f'SELECT {columns} FROM "{name}" ORDER BY {order}', connection)
    expected = frame.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(expected.isna(), saved.isna())
    pd.testing.assert_frame_equal(expected, saved.astype(frame.dtypes), check_exact=True)


def check_price_snapshot(frame, tolerance):
    utc = pd.to_datetime(frame.timestamp_utc, utc=True)
    eastern = pd.to_datetime(frame.timestamp_ept)
    assert utc.dt.tz_convert("America/New_York").dt.tz_localize(None).equals(eastern)
    expected = pd.date_range(
        "2024-01-01", "2026-09-01", freq="h", tz="America/New_York", inclusive="left"
    ).tz_convert("UTC")
    for _, group in frame.groupby("pnode_id"):
        observed = pd.DatetimeIndex(pd.to_datetime(group.timestamp_utc, utc=True))
        assert observed.difference(expected).empty and expected.difference(observed).empty
    errors = {}
    for market in ["da", "rt"]:
        columns = [
            f"{part}_{market}"
            for part in ["system_energy_price", "congestion_price", "marginal_loss_price"]
        ]
        residual = frame[f"total_lmp_{market}"] - frame[columns].sum(axis=1, min_count=3)
        errors[market] = float(residual.abs().max())
        assert errors[market] < tolerance
    return {"physical_hours_per_node": len(expected), "component_max_error": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT / "rebuilt.sqlite")
    parser.add_argument("--compare-with", type=Path)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".building.sqlite")
    temporary.unlink(missing_ok=True)
    catalogue, audits = [], {}
    inputs = [
        (name, ROOT / "data/processed" / filename, ["timestamp_source", *entities], [ref], offset)
        for name, filename, entities, ref, offset in SOURCES
    ]
    inputs.append(
        (
            "hourly_analysis",
            OUT / "hourly_panel.csv",
            ["timestamp", "flowgate"],
            ["D01", "D02", "D03", "D04", "D05", "D06"],
            None,
        )
    )
    inputs.extend(
        (name, ROOT / "data/processed" / filename, ["timestamp_utc", "pnode_id"], refs, None)
        for name, filename, refs, _ in PRICES
    )
    bulk = ROOT / "data/processed/pjm_three_inputs"
    load_bulk = bulk / "pjm_load_forecast_history.csv"
    if load_bulk.exists():
        inputs.append(("pjm_load_forecast_history", load_bulk, FORECAST_KEYS, ["A33", "P24"], None))
    elif FORECAST_PATH.exists():
        inputs.append(
            ("pjm_load_forecast_history", FORECAST_PATH, FORECAST_KEYS, ["A33", "P24"], None)
        )
    for table, refs in [
        ("pjm_da_constraint_marginal_values", ["P24"]),
        ("pjm_rt_constraint_marginal_values", ["A34", "P24"]),
        ("pjm_wind_forecast_history", ["A35", "P24"]),
        ("pjm_solar_forecast_history", ["A36", "P24"]),
    ]:
        path = bulk / f"{table}.csv"
        if path.exists():
            inputs.append((table, path, ["source_file", "source_row"], refs, None))
    tolerances = {name: tolerance for name, _, _, tolerance in PRICES}
    with (
        sqlite3.connect(temporary) as connection,
        (
            sqlite3.connect(f"file:{args.compare_with.resolve()}?mode=ro", uri=True)
            if args.compare_with
            else nullcontext()
        ) as original,
    ):
        for name, path, keys, references, offset in inputs:
            frame = read_table(path)
            if offset is not None:
                hour = "hour_ending" if name == "lmps" else "opr_hour"
                times = pd.to_datetime(frame.opr_date) + pd.to_timedelta(
                    frame[hour] - offset, unit="h"
                )
                frame["timestamp_source"] = times.dt.strftime("%Y-%m-%d %H:%M:%S")
            if name == "pjm_load_forecast_history":
                for prefix in ["evaluated_at", "forecast_hour_beginning"]:
                    utc = pd.to_datetime(frame[f"{prefix}_utc"], utc=True)
                    ept = pd.to_datetime(frame[f"{prefix}_ept"])
                    assert utc.dt.tz_convert("America/New_York").dt.tz_localize(None).equals(ept)
                assert frame.forecast_load_mw.notna().all()
                assert (frame.forecast_load_mw >= 0).all()
            write_table(connection, name, frame, keys)
            if original is not None:
                exists = original.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
                ).fetchone()
                if exists:
                    compare_existing(original, name, frame, keys)
                else:
                    assert name.startswith("pjm_") and name in {
                        "pjm_load_forecast_history",
                        "pjm_da_constraint_marginal_values",
                        "pjm_rt_constraint_marginal_values",
                        "pjm_wind_forecast_history",
                        "pjm_solar_forecast_history",
                    }, name
            audits[name] = {
                "rows": len(frame),
                "columns": len(frame.columns),
                "null_counts": frame.isna().sum().to_dict(),
                "exact_match_to_preserved_database": original is not None and bool(exists),
            }
            if name in tolerances:
                audits[name].update(check_price_snapshot(frame, tolerances[name]))
                connection.execute(
                    f'CREATE INDEX "{name}_ept" ON "{name}" (timestamp_ept,pnode_id)'
                )
            elif offset is not None:
                entity_order = ", ".join(f'"{key}"' for key in keys[1:])
                connection.execute(
                    f'CREATE INDEX "{name}_entity_time" ON "{name}" '
                    f"({entity_order},timestamp_source)"
                )
            catalogue.append(
                {
                    "table_name": name,
                    "input_path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "row_count": len(frame),
                    "primary_key": ",".join(keys),
                    "reference_ids": ",".join(references),
                }
            )
            print(f"{name}: {len(frame):,} rows; input readback passed", flush=True)
        registry = json.loads((ROOT / "references/analysis_sources.json").read_text())
        verified_keys = json.loads((ROOT / "references/zotero_items.json").read_text())
        used_ids = {ref for row in catalogue for ref in row["reference_ids"].split(",")}
        sources = [
            {
                "reference_id": source["id"],
                "title": source["title"],
                "location": source.get("url") or source["path"],
                "description": source["description"],
                "summary": source["summary"],
                "result_used": source["used"],
                "zotero_key": source.get("zotero_key") or verified_keys[source["id"]],
            }
            for source in registry
            if source["id"] in used_ids
        ]
        assert used_ids == {source["reference_id"] for source in sources}
        write_table(connection, "source_references", pd.DataFrame(sources), ["reference_id"])
        write_table(connection, "data_catalog", pd.DataFrame(catalogue), ["table_name"])
        checks = {
            "sqlite_integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "panel_rows": connection.execute("SELECT COUNT(*) FROM hourly_analysis").fetchone()[0],
            "records": connection.execute(
                "SELECT SUM(event_recorded) FROM hourly_analysis"
            ).fetchone()[0],
            "event_value_mismatches": connection.execute(
                "SELECT COUNT(*) FROM constraints c LEFT JOIN hourly_analysis a "
                "ON a.timestamp = c.timestamp_source AND a.flowgate = c.flowgate "
                "WHERE a.event_recorded IS NOT 1 OR a.avg_shadow_price IS NOT c.avg_shadow_price"
            ).fetchone()[0],
            "absent_hour_shadow_values": connection.execute(
                "SELECT COUNT(*) FROM hourly_analysis WHERE event_recorded = 0 "
                "AND (avg_shadow_price IS NOT NULL OR shadow_magnitude IS NOT NULL)"
            ).fetchone()[0],
            "eligible_hours_per_gate": [
                list(row)
                for row in connection.execute(
                    "SELECT flowgate,COUNT(*) FROM hourly_analysis "
                    "WHERE dst_transition_date=0 GROUP BY flowgate"
                )
            ],
        }
        assert checks["sqlite_integrity"] == "ok"
        assert checks["panel_rows"] == 70119 and checks["records"] == 10732
        assert checks["event_value_mismatches"] == checks["absent_hour_shadow_values"] == 0
        assert all(row[1] == 23256 for row in checks["eligible_hours_per_gate"])
        connection.execute("ANALYZE")
    temporary.replace(args.output)
    pd.DataFrame(catalogue).to_csv(OUT / "input_catalog.csv", index=False)
    (OUT / "rebuild_checks.json").write_text(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "compared_against": str(args.compare_with.resolve()) if args.compare_with else None,
                "database_bytes": args.output.stat().st_size,
                "checks": checks,
                "tables": audits,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Saved {args.output}; canonical database is unchanged unless explicitly selected.")


if __name__ == "__main__":
    main()
