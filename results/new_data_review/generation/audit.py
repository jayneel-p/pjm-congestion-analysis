"""Independent raw-SQL/group-loop reconstruction; does not import analyzer."""
import calendar
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def main():
    errors, checks = [], 0
    def same(observed, expected, label):
        nonlocal checks
        checks += 1
        if not math.isclose(float(observed), float(expected), rel_tol=1e-10, abs_tol=1e-7):
            errors.append(f"{label}: {observed} != {expected}")
    with sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True) as con:
        fuel_rows = con.execute("SELECT timestamp_source,fuel_type,mw FROM fuel_generation").fetchall()
        statuses = con.execute("SELECT timestamp,flowgate,event_recorded,dst_transition_date FROM hourly_analysis").fetchall()
    output = defaultdict(dict)
    for stamp, fuel, mw in fuel_rows:
        assert fuel not in output[stamp]
        output[stamp][fuel] = mw
    eligible, by_gate = set(), defaultdict(dict)
    for stamp, gate, event, excluded in statuses:
        if excluded == 0:
            eligible.add(stamp)
            by_gate[gate[-1]][stamp] = event
    records, eligible_months = [], defaultdict(int)
    for stamp in sorted(eligible):
        eligible_months[stamp[:7]] += 1
        values = output.get(stamp, {})
        if len(values) != 10 or any(x is None for x in values.values()):
            continue
        dt = datetime.fromisoformat(stamp)
        records.append((stamp, dt.year, (dt.month, dt.hour, int(dt.weekday() >= 5)), values))
    monthly = defaultdict(list)
    cells = defaultdict(list)
    for record in records:
        stamp, year, key, values = record
        monthly[stamp[:7]].append(record)
        if key[0] <= 8:
            cells[year, key].append(record)
    monthly_csv = pd.read_csv(OUT / "tables/monthly.csv")
    for r in monthly_csv.itertuples():
        rows = monthly[r.month]
        same(r.mean_mw, sum(x[3][r.fuel] for x in rows) / len(rows), f"monthly MW {r.month}/{r.fuel}")
        same(r.mean_hourly_share_pct, sum(100 * x[3][r.fuel] / sum(x[3].values()) for x in rows) / len(rows), "monthly share")
        same(r.complete_hours, len(rows), "monthly complete support")
        same(r.eligible_hours, eligible_months[r.month], "monthly eligible support")
    common = set.intersection(*(set(key for year, key in cells if year == y) for y in [2024, 2025, 2026]))
    weight_total = sum(len(cells[2024, key]) for key in common)
    annual = pd.read_csv(OUT / "tables/annual.csv")
    for r in annual.itertuples():
        mean, share, count = 0, 0, 0
        for key in common:
            rows = cells[r.year, key]
            weight = len(cells[2024, key]) / weight_total
            mean += weight * sum(x[3][r.fuel] for x in rows) / len(rows)
            share += weight * sum(100 * x[3][r.fuel] / sum(x[3].values()) for x in rows) / len(rows)
            count += len(rows)
        for field, value in [("mean_mw", mean), ("mean_hourly_share_pct", share), ("complete_hours", count), ("calendar_cells", len(common))]:
            same(getattr(r, field), value, f"annual {r.year}/{r.fuel}/{field}")
    matched = pd.read_csv(OUT / "tables/gate_annual.csv")
    for r in matched.itertuples():
        target_values, control_values = [], []
        complete, binding, supported_controls = 0, 0, 0
        for (year, key), rows in cells.items():
            if year != r.year:
                continue
            controls = [x for x in rows if by_gate[r.gate][x[0]] == 0]
            targets = [x for x in rows if by_gate[r.gate][x[0]] == 1]
            complete += len(rows)
            binding += len(targets)
            if len(controls) < 3:
                continue
            supported_controls += len(controls)
            control = sum(x[3][r.fuel] for x in controls) / len(controls)
            target_values.extend(x[3][r.fuel] for x in targets)
            control_values.extend([control] * len(targets))
        target_mean = sum(target_values) / len(target_values)
        control_mean = sum(control_values) / len(control_values)
        eligible_count = sum(stamp[:4] == str(r.year) and int(stamp[5:7]) <= 8 for stamp in eligible)
        for field, value in [("binding_mean_mw", target_mean), ("control_mean_mw", control_mean),
                             ("difference_mw", target_mean - control_mean), ("eligible_hours", eligible_count),
                             ("complete_hours", complete), ("binding_complete_hours", binding),
                             ("matched_binding_hours", len(target_values)), ("supported_control_hours", supported_controls)]:
            same(getattr(r, field), value, f"matched {r.gate}/{r.year}/{r.fuel}/{field}")
    with gzip.open(ROOT / "data/raw/epa_baltimore_units_2024_2026q2.json.gz", "rt") as handle:
        raw = json.load(handle)
    plant_csv = pd.read_csv(OUT / "tables/a_nearby_plants.csv")
    for r in plant_csv.itertuples():
        facility, units = (602, ["1", "2"]) if r.plant_series.startswith("Brandon") else (1554, ["1", "3", "4"])
        rows = [x for x in raw if x["facilityId"] == facility and x["unitId"] in units and x["date"].startswith(str(r.year)) and int(x["date"][5:7]) <= 6]
        energy = sum(0 if x["opTime"] == 0 else x["grossLoad"] * x["opTime"] for x in rows)
        hours = sum(calendar.monthrange(r.year, m)[1] * 24 for m in range(1, 7))
        same(r.gross_mwh, energy, "EPA raw gross energy")
        same(r.physical_facility_hours, hours, "EPA physical hours")
        same(r.gross_average_mw, energy / hours, "EPA physical-hour average")
    result = json.loads((OUT / "result.json").read_text())
    for path, digest in result["output_sha256"].items():
        checks += 1
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            errors.append(f"Changed output {path}")
    review = dict(status="passed" if not errors else "failed", scalar_checks=checks, errors=errors,
                  scope="Independent raw SQL and EPA group-loop reconstruction of all descriptive means, shares and supports; no causal, uncertainty or forecast validation.",
                  reviewed_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT / "result.json", OUT / "analyze.py", OUT / "methods.md"]})
    (OUT / "numeric_check.json").write_text(json.dumps(review, indent=2) + "\n")
    print(json.dumps(review, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
