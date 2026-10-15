"""Align the supplied source tables; assumptions and mappings: build_hourly_panel.md."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"
OUT = ROOT / "results/base_case"
MAPPINGS = [
    ("Flowgate A", "BC Zone", "MIDATL", "BGE_RESID_AGG"),
    ("Flowgate B", "DOM Zone", "SOUTH", "DOM_RESID_AGG"),
    ("Flowgate C", "COMED Zone", "WEST", "COMED_RESID_AGG"),
]


def read_hourly(filename, hour_column="opr_hour", offset=0):
    frame = pd.read_csv(DATA / filename, parse_dates=["opr_date"], float_precision="round_trip")
    frame["timestamp"] = frame.opr_date + pd.to_timedelta(frame[hour_column] - offset, unit="h")
    return frame


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = read_hourly("pjm_constraints_2024_2026.csv")
    load = read_hourly("PJM_load_2024_2026.csv", offset=1).pivot(
        index="timestamp", columns="region_zone", values="load_value"
    )
    solar = read_hourly("PJM_hourly_solar_actuals_2024_2026.csv").pivot(
        index="timestamp", columns="area", values="solar_value"
    )
    wind = read_hourly("PJM_hourly_wind_actuals_2024_2026.csv").pivot(
        index="timestamp", columns="area", values="wind_value"
    )
    fuel = read_hourly("pjm_fuel_gen_2024_2026.csv").pivot(
        index="timestamp", columns="fuel_type", values="mw"
    )
    prices = read_hourly("pjm_hourly_lmps_2024_2026.csv", "hour_ending", offset=1)
    lmp = prices.pivot(index="timestamp", columns="pnode_name", values="total_lmp_rt")
    congestion = prices.pivot(index="timestamp", columns="pnode_name", values="congestion_price_rt")
    calendar = solar.index
    assert calendar.equals(wind.index) and calendar.equals(lmp.index)
    assert events.timestamp.isin(calendar).all()
    assert not events.duplicated(["timestamp", "flowgate"]).any()
    event_counts = events.groupby("timestamp").size().reindex(calendar, fill_value=0)

    # Exclude entire clock-change dates from comparisons; retain them in the saved panel.
    dst_dates = pd.to_datetime(
        ["2024-03-10", "2024-11-03", "2025-03-09", "2025-11-02", "2026-03-08"]
    )
    panels = []
    coverage = []
    for gate, zone, area, node in MAPPINGS:
        frame = pd.DataFrame(index=calendar)
        shadow = events.loc[events.flowgate.eq(gate)].set_index("timestamp").avg_shadow_price
        frame["flowgate"] = gate
        frame["event_recorded"] = frame.index.isin(shadow.index)
        frame["avg_shadow_price"] = shadow
        frame["shadow_magnitude"] = frame.avg_shadow_price.abs()
        frame["other_constraint_recorded"] = event_counts - frame.event_recorded.astype(int) > 0
        frame["dst_transition_date"] = frame.index.normalize().isin(dst_dates)
        frame["zone_load_mw"] = load[zone]
        frame["pjm_load_mw"] = load["PJM RTO Total"]
        frame["regional_solar_mw"] = solar[area]
        frame["regional_wind_mw"] = wind[area]
        for kind in fuel:
            frame[f"pjm_{kind.lower().replace(' ', '_')}_mw"] = fuel[kind]
        frame["local_lmp"] = lmp[node]
        frame["western_hub_lmp"] = lmp["WESTERN HUB"]
        frame["lmp_spread"] = lmp[node] - lmp["WESTERN HUB"]
        frame["congestion_spread"] = congestion[node] - congestion["WESTERN HUB"]
        frame["year"] = frame.index.year
        frame["month"] = frame.index.month
        frame["year_month"] = frame.index.strftime("%Y-%m")
        frame["hour"] = frame.index.hour
        frame["weekend"] = frame.index.dayofweek >= 5
        for column in frame.select_dtypes("number"):
            coverage.append(
                {
                    "flowgate": gate,
                    "column": column,
                    "calendar_hours": len(frame),
                    "missing_hours": int(frame[column].isna().sum()),
                    "missing_event_hours": int(
                        frame.loc[frame.event_recorded, column].isna().sum()
                    ),
                }
            )
        panels.append(frame.reset_index())
    panel = pd.concat(panels, ignore_index=True)
    assert panel.event_recorded.sum() == len(events)
    assert not panel.duplicated(["flowgate", "timestamp"]).any()
    panel.to_csv(OUT / "hourly_panel.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "join_coverage.csv", index=False)
    pd.DataFrame(
        MAPPINGS, columns=["flowgate", "load_zone", "renewable_area", "price_node"]
    ).to_csv(OUT / "geographic_mapping.csv", index=False)
    print(f"Saved {len(panel):,} rows: {len(calendar):,} source clock hours × 3 flowgates.")
    print(
        f"Retained all {len(events):,} event records; "
        f"flagged {panel.dst_transition_date.sum():,} DST rows."
    )


if __name__ == "__main__":
    main()
