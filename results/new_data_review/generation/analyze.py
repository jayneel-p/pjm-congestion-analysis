"""Descriptive generation trends; definitions in methods.md."""

import hashlib
import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
YEARS = [2024, 2025, 2026]
FUELS = ["Gas", "Nuclear", "Coal", "Wind", "Solar", "Hydro", "Multiple Fuels", "Oil", "Other Renewables", "Storage"]
KEYS = ["month", "hour", "weekend"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "svg.fonttype": "none", "svg.hashsalt": "pjm-generation-20261009"})


def save(fig, name):
    fig.savefig(OUT / "figures" / f"{name}.svg", metadata={"Date": None}, facecolor="white")
    fig.savefig(OUT / "figures" / f"{name}.png", dpi=135, facecolor="white")
    plt.close(fig)


def main():
    for folder in ["tables", "figures"]:
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True) as con:
        fuels = pd.read_sql_query("SELECT timestamp_source,fuel_type,mw FROM fuel_generation", con)
        panel = pd.read_sql_query("SELECT timestamp,flowgate,event_recorded,dst_transition_date FROM hourly_analysis", con)
    assert not fuels.duplicated(["timestamp_source", "fuel_type"]).any()
    wide = fuels.pivot(index="timestamp_source", columns="fuel_type", values="mw")[FUELS]
    assert len(wide.columns) == 10
    complete = wide.dropna().reset_index().rename(columns={"timestamp_source": "timestamp"})
    all_hours = panel.loc[panel.flowgate.eq("Flowgate A") & panel.dst_transition_date.eq(0), ["timestamp"]]
    data = all_hours.merge(complete, on="timestamp", how="inner", validate="one_to_one")
    data["time"] = pd.to_datetime(data.timestamp)
    data["year"] = data.time.dt.year
    data["month"] = data.time.dt.month
    data["hour"] = data.time.dt.hour
    data["weekend"] = data.time.dt.dayofweek.ge(5).astype(int)
    data["year_month"] = data.time.dt.strftime("%Y-%m")
    total = data[FUELS].sum(axis=1)
    assert (total > 0).all()
    for fuel in FUELS:
        data[f"{fuel}_share"] = 100 * data[fuel] / total
    monthly = []
    eligible = pd.to_datetime(all_hours.timestamp).dt.strftime("%Y-%m").value_counts()
    for month, group in data.groupby("year_month"):
        for fuel in FUELS:
            monthly.append(dict(month=month, fuel=fuel, mean_mw=group[fuel].mean(),
                                mean_hourly_share_pct=group[f"{fuel}_share"].mean(),
                                complete_hours=len(group), eligible_hours=int(eligible[month])))
    monthly = pd.DataFrame(monthly)
    monthly.to_csv(OUT / "tables/monthly.csv", index=False)
    annual_data = data.loc[data.month.le(8)].copy()
    counts = annual_data.groupby(["year"] + KEYS).size().unstack("year")
    common = counts.dropna().index
    weights = counts.loc[common, 2024]
    weights = weights / weights.sum()
    annual = []
    for year, group in annual_data.groupby("year"):
        means = group.groupby(KEYS)[FUELS + [f"{f}_share" for f in FUELS]].mean().loc[common]
        for fuel in FUELS:
            annual.append(dict(year=year, fuel=fuel, mean_mw=float(means[fuel].dot(weights)),
                               mean_hourly_share_pct=float(means[f"{fuel}_share"].dot(weights)),
                               complete_hours=int(counts.loc[common, year].sum()), calendar_cells=len(common)))
    annual = pd.DataFrame(annual)
    annual.to_csv(OUT / "tables/annual.csv", index=False)
    matched = []
    for gate in "ABC":
        status = panel.loc[panel.flowgate.eq(f"Flowgate {gate}") & panel.dst_transition_date.eq(0), ["timestamp", "event_recorded"]]
        joined = annual_data.merge(status, on="timestamp", validate="one_to_one")
        for year, group in joined.groupby("year"):
            controls = group.loc[group.event_recorded.eq(0)].groupby(KEYS)[FUELS].mean()
            control_counts = group.loc[group.event_recorded.eq(0)].groupby(KEYS).size()
            controls = controls.loc[control_counts.ge(3)]
            targets = group.loc[group.event_recorded.eq(1)].join(controls, on=KEYS, rsuffix="_control").dropna(subset=[f"{f}_control" for f in FUELS])
            for fuel in FUELS:
                matched.append(dict(gate=gate, year=year, fuel=fuel,
                                    binding_mean_mw=targets[fuel].mean(), control_mean_mw=targets[f"{fuel}_control"].mean(),
                                    difference_mw=(targets[fuel] - targets[f"{fuel}_control"]).mean(),
                                    eligible_hours=int((panel.flowgate.eq(f"Flowgate {gate}") & panel.dst_transition_date.eq(0) & pd.to_datetime(panel.timestamp).dt.year.eq(year) & pd.to_datetime(panel.timestamp).dt.month.le(8)).sum()),
                                    complete_hours=len(group), binding_complete_hours=int(group.event_recorded.sum()),
                                    matched_binding_hours=len(targets), supported_control_hours=int(control_counts.loc[controls.index].sum())))
    matched = pd.DataFrame(matched)
    matched.to_csv(OUT / "tables/gate_annual.csv", index=False)
    local = json.loads((ROOT / "results/base_case/local_supply.json").read_text())
    plants = pd.DataFrame([r for r in local["periods"] if r["period"] == "Jan–Jun"])
    plants.to_csv(OUT / "tables/a_nearby_plants.csv", index=False)
    fig, axes = plt.subplots(2, 5, figsize=(14.8, 6.8), constrained_layout=True)
    for ax, fuel in zip(axes.flat, FUELS):
        rows = monthly.loc[monthly.fuel.eq(fuel)]
        ax.plot(pd.to_datetime(rows.month), rows.mean_mw / 1000, color="#246fa0", lw=1.8)
        ax.set(title=fuel, ylabel="Mean output (GW)")
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.grid(alpha=.18)
    fig.suptitle("PJM generation through time · all complete eligible hours", fontsize=17)
    fig.supxlabel("Monthly means · Jan 2024–Aug 2026 · separate vertical scales · 2026 is incomplete", fontsize=11)
    save(fig, "monthly")
    for gate in "ABC":
        fig, axes = plt.subplots(2, 5, figsize=(14.8, 7.8))
        fig.subplots_adjust(left=.06, right=.985, top=.83, bottom=.15, hspace=.52, wspace=.48)
        for ax, fuel in zip(axes.flat, FUELS):
            rows = matched.loc[matched.gate.eq(gate) & matched.fuel.eq(fuel)].sort_values("year")
            for field, label, color, style in [("binding_mean_mw", "Binding", "#246fa0", "-"), ("control_mean_mw", "Similar nonbinding", "#d8822b", "--")]:
                ax.plot(rows.year, rows[field] / 1000, marker="o", color=color, ls=style, label=label)
            context = annual.loc[annual.fuel.eq(fuel)].sort_values("year")
            ax.plot(context.year, context.mean_mw / 1000, color="#71838c", ls=":", label="All hours, same calendar weights")
            ax.set(title=fuel, ylabel="Mean output (GW)", xticks=YEARS, xticklabels=["2024", "2025", "2026"])
            ax.grid(alpha=.18)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(.5,.94))
        support = matched.loc[matched.gate.eq(gate) & matched.fuel.eq("Gas")]
        text = "; ".join(f"{r.year}: {r.matched_binding_hours:,}/{r.binding_complete_hours:,}" for r in support.itertuples())
        fig.suptitle(f"{gate}: how PJM fuel output changed · January–August each year", fontsize=17)
        fig.supxlabel(f"Matched / complete binding hours — {text}\nAll ten fuels share support · separate vertical scales · descriptive means, no uncertainty bars", fontsize=10)
        save(fig, f"gate_{gate.lower()}")
    paths = list((OUT / "tables").glob("*.csv")) + list((OUT / "figures").glob("*"))
    result = dict(date="2026-10-09", years=YEARS, fuel_categories=FUELS,
                  annual_calendar_cells=len(common), complete_eligible_hours=len(data),
                  individual_B_C_unit_histories_available=False,
                  output_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(annual.loc[annual.fuel.isin(["Gas", "Nuclear", "Coal", "Wind", "Solar"])].to_string(index=False))
    print(matched.loc[matched.fuel.isin(["Gas", "Nuclear", "Coal"])].to_string(index=False))


if __name__ == "__main__":
    main()
