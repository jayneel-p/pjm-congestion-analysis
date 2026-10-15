"""Read-only full-block price and DA/RT difference analysis; see methods.md."""

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
for d in ["tables", "figures"]:
    (OUT / d).mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
COLORS = ["#146287", "#d18432", "#93435e"]
PAIRS = {
    "A": ("BGE_RESID_AGG", "WESTERN HUB", "peak"),
    "B": ("DOMINION HUB", "WESTERN HUB", "peak"),
    "B-local": ("ACCA", "DOMINION HUB", "peak"),
    "C": ("COMED_RESID_AGG", "WESTERN HUB", "offpeak"),
}


def save(fig, name):
    fig.savefig(OUT / "figures" / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def summary(x):
    x = np.asarray(x, dtype=float)
    return {
        "n": len(x),
        "mean": x.mean(),
        "median": np.median(x),
        "p05": np.quantile(x, 0.05),
        "p95": np.quantile(x, 0.95),
        "min": x.min(),
        "max": x.max(),
        "positive_fraction": (x > 0).mean(),
    }


def interval(frame, metric, days=7):
    dates = pd.to_datetime(frame.timestamp_ept).dt.normalize()
    groups = ((dates - pd.Timestamp("2024-01-01")).dt.days // days).to_numpy()
    unique, codes = np.unique(groups, return_inverse=True)
    sums = np.bincount(codes, weights=frame[metric])
    counts = np.bincount(codes)
    rng = np.random.default_rng(20261009 + days)
    weights = rng.multinomial(len(unique), np.ones(len(unique)) / len(unique), size=599)
    means = (weights @ sums) / (weights @ counts)
    return np.quantile(means, [0.025, 0.975])


def main():
    c = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    p = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da,total_lmp_rt,congestion_price_da,congestion_price_rt FROM pjm_multi_node_hourly_lmps",
        c,
    )
    a = pd.read_sql_query(
        "SELECT timestamp,flowgate,event_recorded FROM hourly_analysis WHERE dst_transition_date=0",
        c,
    )
    c.close()
    assert not p.duplicated(["timestamp_utc", "pnode_name"]).any()
    w = p.pivot(index="timestamp_utc", columns="pnode_name")
    utc = pd.to_datetime(w.index, utc=True)
    ept = utc.tz_convert("America/New_York")
    holidays = pd.read_csv(ROOT / "results/base_case/tables/block_holidays.csv")
    dates = ept.strftime("%Y-%m-%d")
    hcol = "date" if "date" in holidays else holidays.columns[0]
    peak = (
        (ept.dayofweek < 5)
        & (ept.hour >= 7)
        & (ept.hour <= 22)
        & ~pd.Index(dates).isin(holidays[hcol])
    )
    panels = []
    for gate, (left, right, block) in PAIRS.items():
        f = pd.DataFrame(
            {
                "timestamp_utc": w.index,
                "timestamp_ept": ept.tz_localize(None),
                "date": dates,
                "year": ept.year,
                "month": ept.month,
                "year_month": ept.strftime("%Y-%m"),
                "gate": gate,
                "block": block,
            }
        )
        for market in ["da", "rt"]:
            for kind, field in [("total", "total_lmp"), ("congestion", "congestion_price")]:
                f[f"{kind}_{market}"] = (
                    w[f"{field}_{market}"][left] - w[f"{field}_{market}"][right]
                ).to_numpy()
        f["rt_minus_da"] = f.total_rt - f.total_da
        f = f.loc[peak if block == "peak" else ~peak].copy()
        source = a.loc[a.flowgate.eq("Flowgate " + gate[0]), ["timestamp", "event_recorded"]].copy()
        source["timestamp_ept"] = pd.to_datetime(source.pop("timestamp"))
        f = f.merge(source, on="timestamp_ept", how="left", validate="many_to_one")
        f["left"] = left
        f["right"] = right
        panels.append(f)
    all_hours = pd.concat(panels, ignore_index=True)
    assert not all_hours[["total_da", "total_rt"]].isna().any().any()
    all_hours.to_csv(OUT / "tables/block_hours.csv", index=False)
    metrics = ["total_da", "total_rt", "congestion_da", "congestion_rt", "rt_minus_da"]
    months = (
        all_hours.groupby(["gate", "block", "year", "month", "year_month"])
        .agg(hours=("total_da", "size"), **{x: (x, "mean") for x in metrics})
        .reset_index()
    )
    daily = (
        all_hours.groupby(["gate", "block", "year", "month", "date"])
        .agg(hours=("total_da", "size"), **{x: (x, "mean") for x in metrics})
        .reset_index()
    )
    months.to_csv(OUT / "tables/months.csv", index=False)
    daily.to_csv(OUT / "tables/days.csv", index=False)
    rows, anticipation = [], []
    for (gate, year), f in all_hours.loc[all_hours.month.le(8)].groupby(["gate", "year"]):
        for m in metrics:
            rows.append({"gate": gate, "year": year, "metric": m, **summary(f[m])})
        for event, g in f.dropna(subset=["event_recorded"]).groupby("event_recorded"):
            lo, hi = interval(g, "rt_minus_da")
            anticipation.append(
                {
                    "gate": gate,
                    "year": year,
                    "recorded": int(event),
                    **summary(g.rt_minus_da),
                    "lower_week": lo,
                    "upper_week": hi,
                    "da_mean": g.total_da.mean(),
                    "rt_mean": g.total_rt.mean(),
                }
            )
    dist = pd.DataFrame(rows)
    dist.to_csv(OUT / "tables/distributions.csv", index=False)
    ant = pd.DataFrame(anticipation)
    ant.to_csv(OUT / "tables/anticipation.csv", index=False)
    sensitivity = []
    for gate, f in all_hours.loc[all_hours.year.eq(2026) & all_hours.month.le(8)].groupby("gate"):
        for event, g in f.dropna(subset=["event_recorded"]).groupby("event_recorded"):
            for days in [1, 7, 14]:
                lo, hi = interval(g, "rt_minus_da", days)
                sensitivity.append(
                    {
                        "gate": gate,
                        "recorded": int(event),
                        "block_days": days,
                        "mean": g.rt_minus_da.mean(),
                        "low": lo,
                        "high": hi,
                    }
                )
    pd.DataFrame(sensitivity).to_csv(OUT / "tables/interval_sensitivity.csv", index=False)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.7))
    labels = {
        "A": "A · BGE residual − Western · peak",
        "B": "B · Dominion Hub − Western · peak",
        "C": "C · ComEd residual − Western · off-peak",
    }
    for ax, gate in zip(axes, "ABC", strict=True):
        for year, color in zip([2024, 2025, 2026], COLORS, strict=True):
            f = months.loc[months.gate.eq(gate) & months.year.eq(year) & months.month.le(8)]
            ax.plot(f.month, f.total_da, "o-", label=str(year), color=color, lw=2)
        ax.axhline(0, color="#87959b", lw=0.8)
        ax.set(
            title=labels[gate],
            xlabel="Delivery month",
            ylabel="DA total spread ($/MWh)",
            xticks=range(1, 9),
            xticklabels=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"],
        )
        ax.tick_params(axis="x", labelsize=10)
        ax.grid(axis="y", alpha=0.2)
    axes[0].legend(frameon=False)
    fig.suptitle("The delivery block changes the question: include every covered hour", fontsize=17)
    fig.tight_layout()
    save(fig, "block_months")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, gate in zip(axes, "ABC", strict=True):
        f = ant.loc[ant.gate.eq(gate) & ant.year.eq(2026)].sort_values("recorded")
        for i, r in enumerate(f.itertuples()):
            ax.errorbar(
                r.mean,
                i,
                xerr=[[r.mean - r.lower_week], [r.upper_week - r.mean]],
                fmt="o",
                color=COLORS[int(r.recorded)],
                capsize=5,
                ms=8,
            )
            ax.annotate(
                f"{r.mean:+.2f}\nn={r.n:,}",
                (r.mean, i),
                xytext=(0, 13),
                textcoords="offset points",
                ha="center",
                fontsize=11,
            )
        ax.axvline(0, color="#87959b")
        ax.set(
            title=labels[gate],
            yticks=[0, 1],
            yticklabels=["No record", "Record"],
            ylim=(-0.65, 1.65),
            xlabel="RT spread minus DA spread ($/MWh)",
        )
        ax.grid(axis="x", alpha=0.2)
    fig.suptitle("Binding and a surprise in the priced spread are different questions", fontsize=17)
    fig.tight_layout()
    save(fig, "price_surprises")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, gate in zip(axes, "ABC", strict=True):
        h = all_hours.loc[all_hours.gate.eq(gate) & all_hours.year.eq(2026) & all_hours.month.le(8)]
        d = daily.loc[daily.gate.eq(gate) & daily.year.eq(2026) & daily.month.le(8)]
        for vals, label, color in [
            (h.total_da, "Hourly", COLORS[0]),
            (d.total_da, "Daily block mean", COLORS[1]),
        ]:
            x = np.sort(vals)
            y = np.arange(1, len(x) + 1) / len(x)
            ax.step(x, y, where="post", label=f"{label} · n={len(x):,}", color=color, lw=2)
        ax.axvline(0, color="#87959b", lw=0.8)
        ax.set_xscale("symlog", linthresh=10)
        ax.set(
            title=labels[gate],
            xlabel="DA total spread ($/MWh; compressed tails)",
            ylabel="Fraction at or below price",
            ylim=(0, 1),
        )
        ax.legend(fontsize=10, frameon=False)
        ax.grid(alpha=0.2)
    fig.suptitle("A typical hour and a whole day have different distributions", fontsize=17)
    fig.tight_layout()
    save(fig, "block_distributions")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    for i, gate in enumerate(["B", "B-local"]):
        x = ant.loc[ant.gate.eq(gate) & ant.year.eq(2026) & ant.recorded.eq(1)].iloc[0]
        axes[0].errorbar(
            x["mean"],
            i,
            xerr=[[x["mean"] - x.lower_week], [x.upper_week - x["mean"]]],
            fmt="o",
            color=COLORS[i],
            capsize=5,
            ms=8,
        )
        axes[0].plot(x["median"], i, "x", color=COLORS[i], ms=9, mew=2)
        axes[0].annotate(
            f"mean {x['mean']:+.2f}; median {x['median']:+.2f}",
            (x["mean"], i),
            xytext=(0, 14),
            textcoords="offset points",
            ha="center",
            fontsize=11,
        )
        f = all_hours.loc[
            all_hours.gate.eq(gate)
            & all_hours.year.eq(2026)
            & all_hours.month.le(8)
            & all_hours.event_recorded.eq(1)
        ]
        vals = np.sort(f.rt_minus_da)
        axes[1].step(
            vals,
            np.arange(1, len(vals) + 1) / len(vals),
            where="post",
            color=COLORS[i],
            lw=2,
            label=("Dominion Hub − Western" if i == 0 else "ACCA − Dominion Hub"),
        )
    axes[0].set(
        yticks=[0, 1],
        yticklabels=["Dominion Hub − Western", "ACCA − Dominion Hub"],
        ylim=(-0.6, 1.6),
        xlabel="RT spread minus DA spread ($/MWh)",
        title="Mean, week interval, and median (×)",
    )
    axes[1].set(
        xlabel="RT spread minus DA spread ($/MWh)",
        ylabel="Fraction at or below difference",
        ylim=(0, 1),
        title="Same 136 B-recorded peak hours",
    )
    axes[1].legend(frameon=False, fontsize=10)
    axes[1].set_xscale("symlog", linthresh=10)
    for ax in axes:
        ax.axvline(0, color="#aaa", lw=1)
        ax.grid(alpha=0.2)
    fig.suptitle(
        "B: local RT separation and a regional hub discount are different exposures", fontsize=16
    )
    save(fig, "b_location_surprises")
    tail_rows = []
    for gate in ["A", "B", "B-local", "C"]:
        f = all_hours.loc[
            all_hours.gate.eq(gate)
            & all_hours.year.eq(2026)
            & all_hours.month.le(8)
            & all_hours.event_recorded.eq(1)
        ].copy()
        f["week"] = pd.to_datetime(f.timestamp_ept).dt.to_period("W-SUN")
        k = int(np.ceil(0.05 * len(f)))
        x = np.sort(f.rt_minus_da)
        leave = np.array([f.loc[f.week.ne(w), "rt_minus_da"].mean() for w in f.week.unique()])
        tail_rows.append(
            {
                "gate": gate,
                "n": len(f),
                "dates": f.date.nunique(),
                "weeks": f.week.nunique(),
                "mean": f.rt_minus_da.mean(),
                "median": f.rt_minus_da.median(),
                "tail_hours": k,
                "lowest_5pct_sum_per_all_hours": x[:k].sum() / len(x),
                "highest_5pct_sum_per_all_hours": x[-k:].sum() / len(x),
                "leave_week_mean_min": leave.min(),
                "leave_week_mean_max": leave.max(),
            }
        )
    pd.DataFrame(tail_rows).to_csv(OUT / "tables/surprise_tails.csv", index=False)
    result = {
        "date": "2026-10-09",
        "passed": True,
        "source_price_table": "pjm_multi_node_hourly_lmps",
        "source_rows": len(p),
        "physical_hours_per_node": len(w),
        "pairs": PAIRS,
        "yearly_jan_aug": dist.loc[dist.metric.eq("total_da")].to_dict("records"),
        "anticipation_2026": ant.loc[ant.year.eq(2026)].to_dict("records"),
        "figures": ["block_months", "price_surprises", "block_distributions"],
        "limits": [
            "Research blocks, not official settlements or profits.",
            "RT−DA uses realized prices; no virtual-trade costs or entry information.",
            "Eight 2026 months do not estimate future monthly odds.",
            "Weekly ranges omit regime and specification uncertainty.",
        ],
    }
    result["figures"].append("b_location_surprises")
    result["surprise_tails"] = tail_rows
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ["physical_hours_per_node", "yearly_jan_aug", "anticipation_2026"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
