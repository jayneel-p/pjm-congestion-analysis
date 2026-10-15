"""Compact empirical A/B/C evidence; see analyze_flowgates.md."""

import argparse
import gzip
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import ecdf, gaussian_kde
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier, XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/base_case"
FIG = OUT / "figures"
TABLE = OUT / "tables"
CALENDAR = ["year_month", "hour", "weekend"]
BOOTSTRAPS = 599
LOCAL = {"A": "BGE_RESID_AGG", "B": "DOM_RESID_AGG", "C": "COMED_RESID_AGG"}
BLUE, ORANGE, RED, GRAY = "#246fa0", "#d8822b", "#ac3d52", "#71838c"
YEARS = [2024, 2025, 2026]
COLORS = [BLUE, ORANGE, RED]
LOAD_NAMES = {
    "PJM RTO Total": "PJM",
    "Mid-Atlantic Region": "MIDATL",
    "Southern Region": "SOUTH",
    "Western Region": "WEST",
    "PEP Zone": "PEPCO",
    "PL Zone": "PPL",
}
LABELS = {
    "zone_load_mw": "Local demand",
    "pjm_load_mw": "PJM demand",
    "regional_solar_mw": "Regional solar",
    "solar_ramp_1h": "Solar change over 1 hour",
    "solar_ramp_3h": "Solar change over 3 hours",
    "regional_wind_mw": "Regional wind",
}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name, title, note):
    fig.suptitle(title, x=0.07, ha="left", fontsize=16, fontweight="bold")
    fig.text(0.07, 0.012, note, fontsize=8.5, va="bottom")
    fig.tight_layout(rect=(0.01, 0.105, 0.99, 0.94), pad=1.6)
    fig.savefig(FIG / f"{name}.png", dpi=145)
    plt.close(fig)


def prepare():
    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    panel = pd.read_sql_query(
        "SELECT * FROM hourly_analysis ORDER BY flowgate,timestamp",
        connection,
        parse_dates=["timestamp"],
    )
    for table, entity, value in [
        ("load", "region_zone", "load_value"),
        ("wind", "area", "wind_value"),
    ]:
        source = pd.read_sql_query(
            f"SELECT timestamp_source,{entity},{value} FROM {table}",
            connection,
            parse_dates=["timestamp_source"],
        )
        assert not source.duplicated(["timestamp_source", entity]).any()
        if table == "load":
            source[entity] = source[entity].map(
                lambda name: LOAD_NAMES.get(name, name.removesuffix(" Zone"))
            )
        wide = source.pivot(index="timestamp_source", columns=entity, values=value)
        wide.columns = [f"{table}::{name}" for name in wide]
        panel = panel.merge(
            wide, left_on="timestamp", right_index=True, how="left", validate="many_to_one"
        )
    groups = panel.groupby("flowgate")
    for hours in [1, 3]:
        valid = panel.dst_transition_date.eq(0) & panel.regional_solar_mw.notna()
        for lag in range(1, hours + 1):
            valid &= groups.timestamp.diff(lag).eq(pd.Timedelta(hours=lag))
            valid &= groups.dst_transition_date.shift(lag).eq(0)
            valid &= groups.regional_solar_mw.shift(lag).notna()
        panel[f"solar_ramp_{hours}h"] = groups.regional_solar_mw.diff(hours).where(valid)
    panel["solar_drop_3h"] = -panel.solar_ramp_3h
    panel = panel.loc[panel.dst_transition_date.eq(0)].copy()
    panel["date"] = panel.timestamp.dt.normalize()
    panel["week"] = panel.timestamp.dt.to_period("W-SUN").astype(str)
    panel["day"] = panel.timestamp.dt.strftime("%Y-%m-%d")
    panel["fortnight"] = ((panel.date - pd.Timestamp("2024-01-01")).dt.days // 14).astype(str)
    panel["weekday"] = panel.timestamp.dt.dayofweek
    panel["season"] = panel.month.map(
        {
            12: "Winter",
            1: "Winter",
            2: "Winter",
            3: "Spring",
            4: "Spring",
            5: "Spring",
            6: "Summer",
            7: "Summer",
            8: "Summer",
            9: "Autumn",
            10: "Autumn",
            11: "Autumn",
        }
    )
    fuel_columns = [name for name in panel if name.startswith("pjm_") and name.endswith("_mw")]
    fuel_columns.remove("pjm_load_mw")
    total = panel[fuel_columns].sum(axis=1, min_count=len(fuel_columns))
    for column in fuel_columns:
        panel[column.replace("_mw", "_share_pct")] = 100 * panel[column] / total
    eligible = panel.timestamp.unique()
    prices = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da,total_lmp_rt,"
        "congestion_price_da,congestion_price_rt FROM pjm_multi_node_hourly_lmps "
        "WHERE pnode_name IN ('BGE_RESID_AGG','DOM_RESID_AGG','COMED_RESID_AGG',"
        "'WESTERN HUB','DOMINION HUB')",
        connection,
        parse_dates=["timestamp_utc", "timestamp_ept"],
    )
    prices = prices.loc[prices.timestamp_ept.isin(eligible)]
    assert not prices.duplicated(["timestamp_utc", "pnode_name"]).any()
    assert not prices.duplicated(["timestamp_ept", "pnode_name"]).any()
    wide = prices.pivot(index="timestamp_utc", columns="pnode_name")
    spreads = []
    for gate in "ABC":
        pairs = [("local_western", LOCAL[gate], "WESTERN HUB")]
        if gate == "B":
            pairs += [
                ("local_dominion", LOCAL[gate], "DOMINION HUB"),
                ("dominion_western", "DOMINION HUB", "WESTERN HUB"),
            ]
        for pair, left, right in pairs:
            row = pd.DataFrame(index=wide.index)
            row["timestamp"] = wide["timestamp_ept"][left]
            row["flowgate"] = f"Flowgate {gate}"
            for market in ["da", "rt"]:
                for component, field in [
                    ("total", "total_lmp"),
                    ("congestion", "congestion_price"),
                ]:
                    row[f"{pair}_{component}_{market}"] = (
                        wide[f"{field}_{market}"][left] - wide[f"{field}_{market}"][right]
                    )
            row = row.reset_index(drop=True)
            spreads.append(row)
    spread_panel = pd.concat(spreads, ignore_index=True).groupby(["timestamp", "flowgate"]).first()
    panel = panel.merge(
        spread_panel, on=["timestamp", "flowgate"], how="left", validate="one_to_one"
    )
    connection.close()
    assert len(panel) == 69768
    assert not panel.duplicated(["timestamp", "flowgate"]).any()
    assert panel.loc[panel.event_recorded.eq(0), "shadow_magnitude"].isna().all()
    assert np.allclose(panel.shadow_magnitude, panel.avg_shadow_price.abs(), equal_nan=True)
    shares = [name for name in panel if name.endswith("_share_pct")]
    assert np.allclose(panel[shares].sum(axis=1, min_count=10).dropna(), 100)
    for gate, frame in panel.groupby("flowgate"):
        assert frame.local_western_total_da.notna().all(), gate
    b = panel.loc[panel.flowgate.eq("Flowgate B")]
    for market in ["da", "rt"]:
        for component in ["total", "congestion"]:
            assert np.allclose(
                b[f"local_western_{component}_{market}"],
                b[f"local_dominion_{component}_{market}"]
                + b[f"dominion_western_{component}_{market}"],
            )
    return panel, fuel_columns


def bootstrap_weights(frame, block="week"):
    weeks = sorted(frame[block].unique())
    rng = np.random.default_rng(20261008)
    weights = rng.multinomial(len(weeks), np.full(len(weeks), 1 / len(weeks)), BOOTSTRAPS)
    return dict(zip(weeks, range(len(weeks)), strict=True)), weights


def matched(frame, metric, uncertainty=True, block="week"):
    data = frame.dropna(subset=[metric]).copy()
    absent = data.loc[data.event_recorded.eq(0)]
    control = absent.groupby(CALENDAR)[metric].agg(control_mean="mean", controls="size")
    control = control.loc[control.controls.ge(3)]
    data = data.join(control, on=CALENDAR).dropna(subset=["control_mean"])
    recorded = data.loc[data.event_recorded.eq(1)]
    effect = (recorded[metric] - recorded.control_mean).mean()
    result = {
        "recorded_hours": int(frame.event_recorded.sum()),
        "available_hours": int(frame[metric].notna().sum()),
        "matched_recorded_hours": len(recorded),
        "matched_recorded_dates": int(recorded.date.nunique()),
        "control_hours": int(data.event_recorded.eq(0).sum()),
        "matched_recorded_mean": recorded[metric].mean(),
        "matched_control_mean": recorded.control_mean.mean(),
        "difference": effect,
    }
    if uncertainty and len(recorded):
        group = pd.factorize(pd.MultiIndex.from_frame(data[CALENDAR]))[0]
        weeks, weights = bootstrap_weights(frame, block)
        week = data[block].map(weeks).to_numpy()
        is_recorded = data.event_recorded.to_numpy().astype(bool)
        value = data[metric].to_numpy()
        n_groups = group.max() + 1
        draws = []
        for counts in weights:
            w = counts[week]
            control_n = np.bincount(
                group[~is_recorded], weights=w[~is_recorded], minlength=n_groups
            )
            control_sum = np.bincount(
                group[~is_recorded],
                weights=w[~is_recorded] * value[~is_recorded],
                minlength=n_groups,
            )
            control_mean = np.divide(
                control_sum, control_n, out=np.full(n_groups, np.nan), where=control_n > 0
            )
            difference = value[is_recorded] - control_mean[group[is_recorded]]
            use = np.isfinite(difference) & (w[is_recorded] > 0)
            if use.any():
                draws.append(np.average(difference[use], weights=w[is_recorded][use]))
        result["lower_95"], result["upper_95"] = np.quantile(draws, [0.025, 0.975])
        result["bootstrap_blocks"] = len(weeks)
        result["bootstrap_block"] = block
    return result


def distribution(series):
    values = series.dropna().to_numpy()
    q = np.quantile(values, [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
    return {
        "hours": len(values),
        "mean": float(np.mean(values)),
        **dict(zip(["p01", "p05", "p25", "median", "p75", "p95", "p99"], q, strict=True)),
        "min": float(values.min()),
        "max": float(values.max()),
        "fraction_positive": float(np.mean(values > 0)),
        "fraction_negative": float(np.mean(values < 0)),
    }


def standardized_cells(data, cell, cells):
    counts = data.groupby([*CALENDAR, cell], observed=True).size().unstack(cell, fill_value=0)
    counts = counts.reindex(columns=cells, fill_value=0)
    keep = counts.loc[counts.ge(1).all(axis=1)]
    data = data.set_index(CALENDAR).loc[lambda x: x.index.isin(keep.index)].reset_index()
    totals = data.groupby(CALENDAR).size()
    data = data.join(totals.rename("stratum_hours"), on=CALENDAR)
    data["cell_hours"] = data.groupby([*CALENDAR, cell], observed=True)[cell].transform("size")
    data["weight"] = data.stratum_hours / data.cell_hours
    weeks, draws = bootstrap_weights(data)
    rows = []
    for category in cells:
        sample = data.loc[data[cell].eq(category)]
        rate = np.average(sample.event_recorded, weights=sample.weight)
        numerator = (
            sample.assign(weighted=sample.weight * sample.event_recorded)
            .groupby("week")
            .weighted.sum()
        )
        denominator = sample.groupby("week").weight.sum()
        num = np.array([numerator.get(week, 0) for week in weeks])
        den = np.array([denominator.get(week, 0) for week in weeks])
        estimate = (draws @ num) / (draws @ den)
        lo, hi = np.quantile(estimate, [0.025, 0.975])
        rows.append(
            {
                "cell": category,
                "rate": rate,
                "lower_95": lo,
                "upper_95": hi,
                "hours": len(sample),
                "recorded_hours": int(sample.event_recorded.sum()),
                "dates": int(sample.date.nunique()),
                "groups": len(keep),
                "retained_hours": len(data),
                "retained_weekend_hours": int(data.weekend.sum()),
            }
        )
    return rows


def dose_curve(frame, metric):
    data = frame.dropna(subset=[metric]).copy()
    groups = data.groupby(CALENDAR)[metric]
    data["bin"] = np.minimum(((groups.rank(pct=True, method="average") - 1e-12) * 5).astype(int), 4)
    variable = groups.transform("max").gt(groups.transform("min"))
    data = data.loc[variable]
    counts = data.groupby([*CALENDAR, "bin"]).size().unstack("bin", fill_value=0)
    keep = counts.reindex(columns=range(5), fill_value=0).ge(1).all(axis=1)
    data = data.set_index(CALENDAR).loc[lambda x: x.index.isin(counts.index[keep])].reset_index()
    rows = standardized_cells(data, "bin", list(range(5)))
    for row in rows:
        sample = data.loc[data.bin.eq(row["cell"])]
        row["input_median"] = sample[metric].median()
        row["available_hours"] = len(frame.dropna(subset=[metric]))
    return rows


def joint_cells(frame, first, second, hours=None):
    data = frame.dropna(subset=[first, second]).copy()
    if hours is not None:
        data = data.loc[data.hour.between(*hours)]
    available = len(data)
    data["first_high"] = data[first].gt(data.groupby(CALENDAR)[first].transform("median"))
    data["second_high"] = data[second].gt(data.groupby(CALENDAR)[second].transform("median"))
    data["cell"] = data.first_high.astype(int) * 2 + data.second_high.astype(int)
    count = data.groupby([*CALENDAR, "cell"]).size().unstack("cell", fill_value=0)
    count = count.reindex(columns=range(4), fill_value=0)
    support = count.loc[count.ge(3).all(axis=1)].index
    data = data.set_index(CALENDAR).loc[lambda x: x.index.isin(support)].reset_index()
    if data.empty:
        return []
    rows = standardized_cells(data, "cell", list(range(4)))
    for row in rows:
        row["available_hours"] = available
        row["first"] = first
        row["second"] = second
        row["first_mean"] = data.loc[data.cell.eq(row["cell"]), first].mean()
        row["second_mean"] = data.loc[data.cell.eq(row["cell"]), second].mean()
    return rows


def timing(frame, gate):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    rows = []
    for year, color in zip(YEARS, COLORS, strict=True):
        comparable = frame.loc[frame.year.eq(year) & frame.month.le(8)]
        for dimension in ["hour", "weekday", "season"]:
            stats = comparable.groupby(dimension).event_recorded.agg(["mean", "sum", "size"])
            for value, row in stats.iterrows():
                rows.append(
                    {
                        "flowgate": gate,
                        "scope": f"jan_aug_{year}",
                        "dimension": dimension,
                        "value": value,
                        "rate": row["mean"],
                        "records": row["sum"],
                        "hours": row["size"],
                    }
                )
            if dimension == "hour":
                axes[0, 0].plot(stats.index, stats["mean"] * 100, color=color, label=str(year))
            elif dimension == "weekday":
                axes[1, 0].plot(stats.index, stats["mean"] * 100, color=color, label=str(year))
            else:
                order = ["Winter", "Spring", "Summer"]
                axes[1, 1].plot(
                    order, stats["mean"].reindex(order) * 100, color=color, label=str(year)
                )
    monthly = frame.groupby("year_month").event_recorded.agg(["mean", "sum", "size"])
    for value, row in monthly.iterrows():
        rows.append(
            {
                "flowgate": gate,
                "scope": "observed_month",
                "dimension": "year_month",
                "value": value,
                "rate": row["mean"],
                "records": row["sum"],
                "hours": row["size"],
            }
        )
    for (year, season), sample in frame.groupby(["year", "season"]):
        rows.append(
            {
                "flowgate": gate,
                "scope": f"observed_{year}",
                "dimension": "season",
                "value": season,
                "rate": sample.event_recorded.mean(),
                "records": int(sample.event_recorded.sum()),
                "hours": len(sample),
            }
        )
    axes[0, 1].bar(np.arange(len(monthly)), monthly["mean"] * 100, color=BLUE)
    ticks = np.arange(0, len(monthly), 4)
    axes[0, 1].set_xticks(ticks, monthly.index[ticks], rotation=35, ha="right")
    axes[0, 0].set_xticks(range(0, 24, 3))
    axes[0, 0].set_xlabel("Recorded source-hour label")
    axes[0, 0].legend(ncol=3)
    axes[1, 0].set_xticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    for ax, title in zip(
        axes.flat,
        [
            "Hour: January–August in each year",
            "Month: all observed months",
            "Weekday: January–August in each year",
            "Season: January–August in each year",
        ],
        strict=True,
    ):
        ax.set_title(title, loc="left")
        ax.set_ylabel("Recorded-hour fraction (%)")
        ax.grid(axis="y", alpha=0.2)
    save(
        fig,
        f"{gate.lower()}_timing",
        f"Flowgate {gate}: when records appear",
        "A recorded hour is a supplied row, not one event or a full hour bound. "
        "Fractions require a complete export.\n"
        "January–August year comparisons have the same months; "
        "winter here excludes December and autumn is absent.",
    )
    return rows


def driver_curves(frame, gate):
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    rows = []
    for ax, metric in zip(axes.flat, LABELS, strict=True):
        bins = dose_curve(frame, metric)
        for row in bins:
            row.update(flowgate=gate, metric=metric)
        rows.extend(bins)
        values = pd.DataFrame(bins)
        ax.errorbar(
            values.cell,
            values.rate * 100,
            yerr=[(values.rate - values.lower_95) * 100, (values.upper_95 - values.rate) * 100],
            color=BLUE,
            marker="o",
            capsize=3,
        )
        ax.set_title(LABELS[metric], loc="left")
        ax.set_xticks(range(5), ["Lowest", "2", "Middle", "4", "Highest"], rotation=25)
        ax.set_ylabel("Calendar-standardized records (%)")
        ax.grid(axis="y", alpha=0.2)
        ax.text(
            0.02,
            0.97,
            f"{int(values.retained_hours.iloc[0]):,}/"
            f"{int(values.available_hours.iloc[0]):,} hours retained",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
        )
    save(
        fig,
        f"{gate.lower()}_driver_curves",
        f"Flowgate {gate}: does more of an input always mean more records?",
        "Bins rank each input within the same year-month, hour and weekday/weekend; "
        "only strata containing all five bins remain.\n"
        "Bars: 95% week-block bootstrap uncertainty with fixed bins/weights. "
        "This controls calendar, not other fundamentals or outages.",
    )
    return rows


def contrast_plot(ax, frame, metrics, effects, title, divisor=1000, units="GW"):
    labels = []
    values, low, high = [], [], []
    for metric in metrics:
        result = effects[metric]
        labels.append(metric.split("::")[-1] if "::" in metric else LABELS.get(metric, metric))
        values.append(result["difference"] / divisor)
        low.append((result["difference"] - result["lower_95"]) / divisor)
        high.append((result["upper_95"] - result["difference"]) / divisor)
    ax.errorbar(values, np.arange(len(values)), xerr=[low, high], color=BLUE, fmt="o", capsize=3)
    ax.set_yticks(range(len(values)), labels)
    ax.invert_yaxis()
    ax.axvline(0, color=GRAY, linewidth=0.8)
    ax.set_xlabel(f"Recorded minus matched absent\nmean ({units})")
    ax.set_title(title, loc="left")
    ax.grid(axis="x", alpha=0.2)


def load_wind(frame, gate, effects):
    load_regions = {
        "A": ["PJM", "MIDATL", "WEST", "AEP", "BC", "PEPCO", "PPL", "DOM"],
        "B": ["PJM", "MIDATL", "WEST", "AEP", "DOM", "BC", "PEPCO", "COMED"],
        "C": ["PJM", "MIDATL", "WEST", "AEP", "COMED", "DOM", "BC", "PEPCO"],
    }
    existing = [name for name in load_regions[gate] if f"load::{name}" in effects]
    fig, axes = plt.subplots(1, 2, figsize=(12, 7))
    contrast_plot(
        axes[0],
        frame,
        [f"load::{name}" for name in existing],
        effects,
        "Which demand areas rise with records?",
    )
    contrast_plot(
        axes[1],
        frame,
        [name for name in effects if name.startswith("wind::")],
        effects,
        "Which wind-output regions rise with records?",
    )
    save(
        fig,
        f"{gate.lower()}_load_wind",
        f"Flowgate {gate}: geography matters",
        "Calendar matches: same year-month, source hour and weekday/weekend, "
        "with at least 3 absent controls; 95% week-block intervals.\n"
        "Load regions overlap and are not independent evidence. "
        "Wind labels are output geography, not compass wind direction.",
    )


def load_context(frame, gate):
    remote = "load::WEST" if gate == "A" else "load::MIDATL"
    metrics = ["zone_load_mw", "pjm_load_mw", remote]
    contexts = [
        ("time", "Night 00–07", frame.hour.between(0, 7)),
        ("time", "Day 08–15", frame.hour.between(8, 15)),
        ("time", "Evening 16–23", frame.hour.between(16, 23)),
        *[
            ("season", season, frame.season.eq(season))
            for season in ["Winter", "Spring", "Summer", "Autumn"]
        ],
        ("week", "Weekday", frame.weekend.eq(0)),
        ("week", "Weekend", frame.weekend.eq(1)),
    ]
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(14, 6.5))
    for ax, metric in zip(axes, metrics, strict=True):
        for position, (dimension, name, mask) in enumerate(contexts):
            values = matched(frame.loc[mask], metric, uncertainty=False)
            rows.append(
                {
                    "flowgate": gate,
                    "metric": metric,
                    "dimension": dimension,
                    "context": name,
                    **values,
                }
            )
            color = {"time": BLUE, "season": ORANGE, "week": RED}[dimension]
            ax.scatter(position, values["difference"] / 1000, color=color, s=45)
        ax.set_xticks(range(9), [name for _, name, _ in contexts], rotation=55, ha="right")
        ax.axhline(0, color=GRAY, linewidth=0.8)
        ax.axvline(2.5, color=GRAY, linestyle=":", alpha=0.5)
        ax.axvline(6.5, color=GRAY, linestyle=":", alpha=0.5)
        ax.set_ylabel("Recorded minus matched absent mean (GW)")
        name = {
            "zone_load_mw": "Local demand",
            "pjm_load_mw": "PJM demand",
            "load::WEST": "Western-region demand",
            "load::MIDATL": "Mid-Atlantic demand",
        }[metric]
        ax.set_title(name, loc="left")
        ax.grid(axis="y", alpha=0.2)
    save(
        fig,
        f"{gate.lower()}_load_context",
        f"Flowgate {gate}: when does demand move with records?",
        "Each point is a separate subset with exact-calendar matches; "
        "means are in GW and each panel has its own scale.\n"
        "Point comparisons are exploratory; support counts are in the table. "
        "Observed seasons have unequal yearly coverage; no autumn 2026.",
    )
    return rows


def solar_fuels(frame, gate, effects, fuel_columns):
    fig, axes = plt.subplots(1, 3, figsize=(14, 7))
    contrast_plot(
        axes[0],
        frame,
        ["regional_solar_mw", "solar_ramp_1h", "solar_ramp_3h"],
        effects,
        "Solar level and changes",
        divisor=1,
        units="MW",
    )
    names = [
        column.removeprefix("pjm_").removesuffix("_mw").replace("_", " ") for column in fuel_columns
    ]
    shares = [column.replace("_mw", "_share_pct") for column in fuel_columns]
    y = np.arange(len(shares))
    recorded = [effects[column]["matched_recorded_mean"] for column in shares]
    controls = [effects[column]["matched_control_mean"] for column in shares]
    axes[1].barh(y - 0.17, recorded, height=0.34, label="Recorded", color=BLUE)
    axes[1].barh(y + 0.17, controls, height=0.34, label="Matched absent", color=ORANGE)
    axes[1].set_yticks(y, names)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("PJM generation share (%)")
    axes[1].set_title("What fuels are running?", loc="left")
    axes[1].legend(fontsize=8)
    contrast_plot(
        axes[2], frame, fuel_columns, effects, "Output differences", divisor=1000, units="GW"
    )
    axes[2].set_yticks(y, names)
    save(
        fig,
        f"{gate.lower()}_solar_fuels",
        f"Flowgate {gate}: solar ramps and generation context",
        "A 3-hour change is current minus output 3 hours earlier, in MW over that interval; "
        "positive means rising solar.\n"
        "Shares require all 10 fuels and sum to 100%. Generation is PJM-wide actual dispatch: "
        "it may respond to congestion, not cause it.",
    )


def joint_plot(frame, gate):
    pairs = {
        "A": [("pjm_load_mw", "wind::WEST", None), ("zone_load_mw", "solar_drop_3h", (15, 22))],
        "B": [
            ("regional_solar_mw", "zone_load_mw", (8, 17)),
            ("regional_solar_mw", "load::MIDATL", (8, 17)),
        ],
        "C": [("wind::WEST", "load::MIDATL", None), ("wind::WEST", "zone_load_mw", None)],
    }[gate]
    label = {
        **LABELS,
        "wind::WEST": "WEST wind",
        "load::MIDATL": "Mid-Atlantic demand",
        "solar_drop_3h": "3-hour solar drop",
    }
    fig, axes = plt.subplots(2, 3, figsize=(13, 8))
    rows = []
    for line, (first, second, hours) in enumerate(pairs):
        for col, year in enumerate(YEARS):
            sample = frame.loc[frame.year.eq(year) & frame.month.le(8)]
            bins = joint_cells(sample, first, second, hours)
            values = pd.DataFrame(bins)
            for row in bins:
                row.update(flowgate=gate, year=year, pair=line)
            rows.extend(bins)
            ax = axes[line, col]
            matrix = values.rate.to_numpy().reshape(2, 2) * 100
            ax.imshow(matrix, vmin=0, vmax=65, cmap="Blues")
            for row in bins:
                i, j = divmod(row["cell"], 2)
                ax.text(
                    j,
                    i,
                    f"{row['rate'] * 100:.1f}%\nn={row['hours']:,}",
                    ha="center",
                    va="center",
                    color="white" if row["rate"] > 0.35 else "#17334b",
                    fontsize=11,
                )
            ax.set_xticks([0, 1], ["Lower", "Higher"])
            ax.set_yticks([0, 1], ["Lower", "Higher"])
            ax.set_xlabel(label[second])
            ax.set_ylabel(label[first])
            ax.set_title(
                f"{year}: {int(values.retained_hours.iloc[0]):,}/"
                f"{int(values.available_hours.iloc[0]):,} hours",
                loc="left",
                fontsize=10,
            )
    save(
        fig,
        f"{gate.lower()}_joint",
        f"Flowgate {gate}: combinations can change the story",
        "Higher/lower means above/below each exact-calendar median. All four cells need 3 hours; "
        "retained samples are weekdays only.\n"
        "Same weights across cells remove calendar imbalance. Rates are descriptive on retained "
        "support; the table includes week-bootstrap intervals.",
    )
    return rows


def empirical_curve(ax, values, label, color, style="-"):
    cumulative = ecdf(values.dropna()).cdf
    ax.step(
        cumulative.quantiles,
        cumulative.probabilities * 100,
        where="post",
        color=color,
        linestyle=style,
        label=label,
    )


def price_distributions(frame, gate):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    recorded = frame.loc[frame.event_recorded.eq(1)]
    absent = frame.loc[frame.event_recorded.eq(0)]
    empirical_curve(axes[0, 0], recorded.shadow_magnitude, "Recorded only", RED)
    axes[0, 0].set_xscale("symlog", linthresh=10)
    axes[0, 0].set_xticks([0, 10, 100, 1000], ["0", "10", "100", "1,000"])
    shadow = distribution(recorded.shadow_magnitude)
    axes[0, 0].set_xlabel("Shadow magnitude (source units; log scale above 10)")
    axes[0, 0].set_title(
        f"Shadow: median {shadow['median']:.0f}; mean {shadow['mean']:.0f}; "
        f"p95 {shadow['p95']:.0f}",
        loc="left",
        fontsize=10,
    )
    pair = "dominion_western" if gate == "B" else "local_western"
    pair_name = "DOMINION HUB" if gate == "B" else LOCAL[gate]
    for ax, metric, title in [
        (axes[0, 1], f"{pair}_total_da", "DA total LMP"),
        (axes[1, 0], f"{pair}_total_rt", "RT total LMP"),
        (axes[1, 1], f"{pair}_congestion_rt", "RT congestion component"),
    ]:
        empirical_curve(ax, recorded[metric], "Recorded", BLUE)
        empirical_curve(ax, absent[metric], "Absent record", ORANGE)
        ax.axvline(0, color=GRAY, linewidth=0.8)
        ax.set_xscale("symlog", linthresh=5)
        low, high = ax.get_xlim()
        ticks = [value for value in [-1000, -100, -10, 0, 10, 100, 1000] if low <= value <= high]
        ax.set_xticks(ticks, [f"{value:,}" for value in ticks])
        ax.set_title(title, loc="left")
        ax.set_xlabel(f"{pair_name} minus WESTERN HUB ($/MWh)")
    for ax in axes.flat:
        ax.set_ylabel("Share of observations at or below value (%)")
        ax.grid(alpha=0.2)
    axes[0, 1].legend()
    save(
        fig,
        f"{gate.lower()}_price_distributions",
        f"Flowgate {gate}: the distribution, including reversals and extreme hours",
        "Empirical cumulative distributions use actual observations, with no fitted normal "
        "distribution or trimming. Tail values remain visible on log-like axes.\n"
        "These raw distributions mix calendar conditions. Median describes a typical hour; "
        "mean matters for a linear payoff. Shadow is not trading revenue.",
    )


def price_regimes(frame, gate):
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    pair = "dominion_western" if gate == "B" else "local_western"
    pair_name = "DOMINION HUB" if gate == "B" else LOCAL[gate]
    monthly = frame.groupby("year_month")[[f"{pair}_total_da", f"{pair}_total_rt"]].mean()
    for market, color in [("da", BLUE), ("rt", ORANGE)]:
        axes[0].plot(
            np.arange(len(monthly)),
            monthly[f"{pair}_total_{market}"],
            color=color,
            label=f"{market.upper()} total",
        )
    ticks = np.arange(0, len(monthly), 4)
    axes[0].set_xticks(ticks, monthly.index[ticks], rotation=20)
    axes[0].set_title(f"All-hour monthly mean: {pair_name} minus WESTERN HUB", loc="left")
    axes[0].legend(ncol=2)
    rows = []
    pairs = (
        ["local_western"]
        if gate != "B"
        else ["local_western", "local_dominion", "dominion_western"]
    )
    for p in pairs:
        for year in YEARS:
            sample = frame.loc[frame.year.eq(year) & frame.month.le(8)]
            for market in ["da", "rt"]:
                for component in ["total", "congestion"]:
                    metric = f"{p}_{component}_{market}"
                    rows.append(
                        {
                            "flowgate": gate,
                            "scope": f"jan_aug_{year}",
                            "year": year,
                            "pair": p,
                            "market": market,
                            "component": component,
                            **matched(sample, metric),
                        }
                    )
    table = pd.DataFrame(rows)
    if gate == "B":
        for p, name, color in [
            ("local_western", "DOM_RESID_AGG − WESTERN HUB", BLUE),
            ("local_dominion", "DOM_RESID_AGG − DOMINION HUB", ORANGE),
            ("dominion_western", "DOMINION HUB − WESTERN HUB", RED),
        ]:
            points = table.loc[
                table.pair.eq(p) & table.market.eq("rt") & table.component.eq("congestion")
            ]
            axes[1].errorbar(
                points.year,
                points.difference,
                yerr=[points.difference - points.lower_95, points.upper_95 - points.difference],
                color=color,
                marker="o",
                capsize=3,
                label=name,
            )
        points = table.loc[
            table.pair.eq("dominion_western") & table.market.eq("da") & table.component.eq("total")
        ]
        axes[1].errorbar(
            points.year,
            points.difference,
            yerr=[points.difference - points.lower_95, points.upper_95 - points.difference],
            color=GRAY,
            linestyle="--",
            marker="s",
            capsize=3,
            label="DOMINION HUB − WESTERN HUB (DA total)",
        )
    else:
        for market, component, color, style in [
            ("da", "total", BLUE, "-"),
            ("rt", "total", ORANGE, "-"),
            ("da", "congestion", BLUE, "--"),
            ("rt", "congestion", ORANGE, "--"),
        ]:
            points = table.loc[table.market.eq(market) & table.component.eq(component)]
            axes[1].plot(
                points.year,
                points.difference,
                color=color,
                linestyle=style,
                marker="o",
                label=f"{market.upper()} {component}",
            )
    axes[1].set_xticks(YEARS)
    axes[1].set_title(
        "January–August: recorded minus calendar-matched absent price difference", loc="left"
    )
    if gate == "B":
        axes[1].set_title(
            "January–August: matched price differences (RT congestion; dashed: DA total)",
            loc="left",
        )
    axes[1].legend(ncol=2, fontsize=9)
    recorded = frame.loc[frame.event_recorded.eq(1)].copy()
    recorded["shadow_bin"] = pd.qcut(recorded.shadow_magnitude, 5, labels=False, duplicates="drop")
    shadow_rows = []
    shadow_pairs = ["local_western"] if gate != "B" else ["local_western", "dominion_western"]
    for p, color in zip(shadow_pairs, [BLUE, ORANGE], strict=False):
        groups = recorded.groupby("shadow_bin")
        quantiles = groups[f"{p}_congestion_rt"].quantile([0.25, 0.50, 0.75]).unstack()
        axes[2].errorbar(
            quantiles.index,
            quantiles[0.50],
            yerr=[quantiles[0.50] - quantiles[0.25], quantiles[0.75] - quantiles[0.50]],
            color=color,
            marker="o",
            capsize=3,
            label=("DOMINION HUB" if p == "dominion_western" else LOCAL[gate]) + " − WESTERN HUB",
        )
        for category, sample in groups:
            shadow_rows.append(
                {
                    "flowgate": gate,
                    "pair": p,
                    "bin": int(category),
                    "shadow_low": sample.shadow_magnitude.min(),
                    "shadow_high": sample.shadow_magnitude.max(),
                    **distribution(sample[f"{p}_congestion_rt"]),
                }
            )
    axes[2].set_xticks(range(5), ["Lowest", "2", "Middle", "4", "Highest"])
    axes[2].set_xlabel("Shadow magnitude: five equal-count groups of recorded hours")
    axes[2].set_title("Higher shadow: does the location spread actually become larger?", loc="left")
    axes[2].legend(ncol=2, fontsize=9)
    for ax in axes:
        ax.axhline(0, color=GRAY, linewidth=0.8)
        ax.set_ylabel("$/MWh")
        ax.grid(axis="y", alpha=0.2)
    save(
        fig,
        f"{gate.lower()}_price_regimes",
        f"Flowgate {gate}: price exposure, market and regime are separate questions",
        "Monthly means include all hours; middle-panel changes are matched group differences, "
        "not spread levels or profits.\n"
        "Bottom bars show the middle 50% of observations, not confidence intervals. "
        "Pooled shadow groups mix calendar regimes and other constraints.",
    )
    return rows, shadow_rows


def independent_checks(summary):
    """Reconstruct selected comparisons from SQL rows without pandas matching."""
    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    checks = []
    for gate in "ABC":
        lead = {"A": "pjm_load_mw", "B": "regional_solar_mw", "C": "regional_wind_mw"}[gate]
        fundamental = connection.execute(
            f"SELECT year_month,hour,weekend,event_recorded,{lead} FROM hourly_analysis "
            "WHERE dst_transition_date=0 AND flowgate=?",
            (f"Flowgate {gate}",),
        ).fetchall()
        prices = connection.execute(
            "SELECT h.year_month,h.hour,h.weekend,h.event_recorded,"
            "l.total_lmp_da-r.total_lmp_da FROM hourly_analysis h "
            "JOIN pjm_multi_node_hourly_lmps l ON h.timestamp=l.timestamp_ept "
            "JOIN pjm_multi_node_hourly_lmps r ON l.timestamp_utc=r.timestamp_utc "
            "WHERE h.dst_transition_date=0 AND h.flowgate=? AND l.pnode_name=? "
            "AND r.pnode_name='WESTERN HUB'",
            (f"Flowgate {gate}", LOCAL[gate]),
        ).fetchall()
        for metric, rows in [(lead, fundamental), ("local_western_total_da", prices)]:
            controls = defaultdict(list)
            for year_month, hour, weekend, recorded, value in rows:
                if not recorded and value is not None:
                    controls[(year_month, hour, weekend)].append(value)
            differences = []
            for year_month, hour, weekend, recorded, value in rows:
                comparison = controls[(year_month, hour, weekend)]
                if recorded and value is not None and len(comparison) >= 3:
                    differences.append(value - sum(comparison) / len(comparison))
            actual = sum(differences) / len(differences)
            expected = summary["gates"][gate]["matched_contrasts"][metric]
            assert len(differences) == expected["matched_recorded_hours"]
            assert abs(actual - expected["difference"]) < 1e-9
            checks.append(
                {
                    "gate": gate,
                    "metric": metric,
                    "hours": len(differences),
                    "absolute_difference": abs(actual - expected["difference"]),
                }
            )
        shadows = sorted(
            value
            for (value,) in connection.execute(
                "SELECT ABS(avg_shadow_price) FROM hourly_analysis "
                "WHERE dst_transition_date=0 AND flowgate=? AND event_recorded=1",
                (f"Flowgate {gate}",),
            )
        )
        expected = summary["gates"][gate]["distributions"]["shadow_magnitude:recorded=1"]
        for probability, name in [(0.50, "median"), (0.95, "p95"), (0.99, "p99")]:
            position = (len(shadows) - 1) * probability
            lower = int(position)
            weight = position - lower
            actual = (
                shadows[lower] * (1 - weight) + shadows[min(lower + 1, len(shadows) - 1)] * weight
            )
            assert abs(actual - expected[name]) < 1e-9
        checks.append(
            {"gate": gate, "shadow_quantiles_independently_checked": ["median", "p95", "p99"]}
        )
    connection.close()
    return checks


def paired_brier_interval(frame, omitted, full):
    """Resample evaluation weeks, keeping paired losses together."""
    loss = (frame.event_recorded.to_numpy() - omitted) ** 2
    loss -= (frame.event_recorded.to_numpy() - full) ** 2
    weeks = pd.DataFrame({"week": frame.week.to_numpy(), "loss": loss})
    grouped = weeks.groupby("week").loss.agg(["sum", "size"])
    rng = np.random.default_rng(20261008)
    draws = rng.multinomial(len(grouped), np.full(len(grouped), 1 / len(grouped)), BOOTSTRAPS)
    values = (draws @ grouped["sum"].to_numpy()) / (draws @ grouped["size"].to_numpy())
    return float(loss.mean()), *np.quantile(values, [0.025, 0.975]).tolist()


def model_investigation(panel):
    scores, predictions, ablations, calibration, price_scores, price_predictions = (
        [] for _ in range(6)
    )
    support, ranges, features = [], [], {}
    splits = [
        ("2025_sep_dec", "2025-08-25", "2025-09-01", "2026-01-01"),
        ("2026_jan_aug", "2025-12-25", "2026-01-01", "2026-09-01"),
    ]
    parameters = dict(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.05,
        min_child_weight=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5,
        tree_method="hist",
        n_jobs=2,
        random_state=20261008,
    )
    for gate in "ABC":
        print(f"Model diagnostics {gate}", flush=True)
        raw = panel.loc[panel.flowgate.eq(f"Flowgate {gate}")].copy()
        for name, value, period in [
            ("hour", raw.hour, 24),
            ("month", raw.month - 1, 12),
            ("weekday", raw.weekday, 7),
        ]:
            raw[f"{name}_sin"] = np.sin(2 * np.pi * value / period)
            raw[f"{name}_cos"] = np.cos(2 * np.pi * value / period)
        groups = {
            "calendar": [
                f"{name}_{wave}" for name in ["hour", "month", "weekday"] for wave in ["sin", "cos"]
            ]
            + ["weekend"],
            "load": ["zone_load_mw", "pjm_load_mw", "load::MIDATL", "load::WEST"],
            "wind": ["wind::WEST", "wind::MIDATL", "wind::SOUTH"],
            "solar": ["regional_solar_mw", "solar_ramp_1h", "solar_ramp_3h"],
            "fuel": ["pjm_gas_mw", "pjm_coal_mw", "pjm_nuclear_mw"],
        }
        if gate != "B":
            groups["load"].append("load::DOM")
        columns = sum(groups.values(), [])
        features[gate] = groups
        data = raw.dropna(subset=columns).copy()
        for split, cutoff, start, end in splits:
            train = data.loc[data.timestamp.lt(cutoff)].copy()
            test = data.loc[data.timestamp.ge(start) & data.timestamp.lt(end)].copy()
            support.append(
                {
                    "gate": gate,
                    "split": split,
                    "train_hours": len(train),
                    "train_end": str(train.timestamp.max()),
                    "test_start": str(test.timestamp.min()),
                    "test_end": str(test.timestamp.max()),
                    "test_hours": len(test),
                    "eligible_test_hours": int(
                        (raw.timestamp.ge(start) & raw.timestamp.lt(end)).sum()
                    ),
                    "training_fraction": float(train.event_recorded.mean()),
                    "observed_fraction": float(test.event_recorded.mean()),
                }
            )
            assert train.timestamp.max() < test.timestamp.min() - pd.Timedelta(days=7)
            assert len(columns) == len(set(columns))
            assert not any(
                "price" in name or "shadow" in name or "record" in name for name in columns
            )
            y = train.event_recorded.to_numpy()
            models = {
                "constant": None,
                "logistic_calendar": make_pipeline(
                    StandardScaler(), LogisticRegression(C=1, max_iter=1500)
                ),
                "logistic_full": make_pipeline(
                    StandardScaler(), LogisticRegression(C=1, max_iter=1500)
                ),
                "xgb_full": XGBClassifier(**parameters),
                **{
                    f"xgb_without_{group}": XGBClassifier(**parameters)
                    for group in ["solar", "wind", "load", "fuel"]
                },
            }
            probs = {}
            for name, model in models.items():
                use = groups["calendar"] if name == "logistic_calendar" else columns
                if name.startswith("xgb_without_"):
                    omitted = name.removeprefix("xgb_without_")
                    use = [c for c in columns if c not in groups[omitted]]
                if model is None:
                    probability = np.full(len(test), y.mean())
                else:
                    model.fit(train[use], y)
                    probability = model.predict_proba(test[use])[:, 1]
                # Reconcile saved predictions and metrics at the same precision.
                probability = np.asarray(probability, dtype=np.float64)
                probs[name] = probability
                scores.append(
                    {
                        "gate": gate,
                        "split": split,
                        "model": name,
                        "hours": len(test),
                        "observed_fraction": float(test.event_recorded.mean()),
                        "predicted_fraction": float(probability.mean()),
                        "brier": brier_score_loss(test.event_recorded, probability),
                        "log_loss": log_loss(test.event_recorded, probability, labels=[0, 1]),
                        "auc": roc_auc_score(test.event_recorded, probability),
                        "average_precision": average_precision_score(
                            test.event_recorded, probability
                        ),
                    }
                )
                predictions.append(
                    pd.DataFrame(
                        {
                            "gate": gate,
                            "split": split,
                            "model": name,
                            "timestamp": test.timestamp.to_numpy(),
                            "week": test.week.to_numpy(),
                            "observed": test.event_recorded.to_numpy(),
                            "probability": probability,
                        }
                    )
                )
            for group in ["solar", "wind", "load", "fuel"]:
                point, lower, upper = paired_brier_interval(
                    test, probs[f"xgb_without_{group}"], probs["xgb_full"]
                )
                ablations.append(
                    {
                        "gate": gate,
                        "split": split,
                        "omitted": group,
                        "brier_omitted_minus_full": point,
                        "lower_95": lower,
                        "upper_95": upper,
                        "hours": len(test),
                        "weeks": test.week.nunique(),
                    }
                )
            check = pd.DataFrame({"p": probs["xgb_full"], "y": test.event_recorded.to_numpy()})
            check["bin"] = pd.qcut(check.p, 10, labels=False, duplicates="drop")
            for cell, sample in check.groupby("bin"):
                calibration.append(
                    {
                        "gate": gate,
                        "split": split,
                        "bin": int(cell),
                        "hours": len(sample),
                        "predicted": sample.p.mean(),
                        "observed": sample.y.mean(),
                    }
                )
            outside = (
                test[columns].lt(train[columns].min()) | test[columns].gt(train[columns].max())
            ).any(axis=1)
            ranges.append(
                {
                    "gate": gate,
                    "split": split,
                    "outside_any_train_range": float(outside.mean()),
                    "hours": len(test),
                }
            )
            pair = "dominion_western" if gate == "B" else "local_western"
            target = f"{pair}_total_da"
            lead = "solar" if gate == "B" else "wind" if gate == "C" else "load"
            regressors = {
                "constant": None,
                "ridge_calendar": make_pipeline(StandardScaler(), Ridge(alpha=10)),
                "ridge_full": make_pipeline(StandardScaler(), Ridge(alpha=10)),
                "xgb_full": XGBRegressor(**parameters),
                f"xgb_without_{lead}": XGBRegressor(**parameters),
            }
            for name, model in regressors.items():
                use = groups["calendar"] if name == "ridge_calendar" else columns
                if name.startswith("xgb_without_"):
                    use = [c for c in columns if c not in groups[lead]]
                if model is None:
                    estimate = np.full(len(test), train[target].mean())
                else:
                    model.fit(train[use], train[target])
                    estimate = model.predict(test[use])
                price_scores.append(
                    {
                        "gate": gate,
                        "split": split,
                        "model": name,
                        "pair": pair,
                        "hours": len(test),
                        "mae": mean_absolute_error(test[target], estimate),
                        "rmse": np.sqrt(mean_squared_error(test[target], estimate)),
                        "mean_error_predicted_minus_actual": float(
                            (estimate - test[target]).mean()
                        ),
                        "actual_mean": float(test[target].mean()),
                        "predicted_mean": float(estimate.mean()),
                    }
                )
                price_predictions.append(
                    pd.DataFrame(
                        {
                            "gate": gate,
                            "split": split,
                            "model": name,
                            "pair": pair,
                            "timestamp": test.timestamp.to_numpy(),
                            "actual": test[target].to_numpy(),
                            "predicted": estimate,
                        }
                    )
                )
    for name, rows in [
        ("ml_scores", scores),
        ("ml_ablations", ablations),
        ("ml_calibration", calibration),
        ("ml_price_scores", price_scores),
        ("ml_support", support),
        ("ml_range_support", ranges),
    ]:
        pd.DataFrame(rows).to_csv(TABLE / f"{name}.csv", index=False)
    pred = pd.concat(predictions, ignore_index=True)
    pred.to_csv(TABLE / "ml_predictions.csv", index=False)
    pp = pd.concat(price_predictions, ignore_index=True)
    pp.to_csv(TABLE / "ml_price_predictions.csv", index=False)
    month = pred.loc[pred.model.eq("xgb_full")].copy()
    month["month"] = month.timestamp.dt.to_period("M").astype(str)
    monthly = (
        month.groupby(["gate", "split", "month"])
        .agg(
            actual=("observed", "mean"),
            predicted=("probability", "mean"),
            hours=("observed", "size"),
        )
        .reset_index()
    )
    monthly.to_csv(TABLE / "ml_monthly.csv", index=False)
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    score = pd.DataFrame(scores)
    cal = pd.DataFrame(calibration)
    for j, gate in enumerate("ABC"):
        d = score.loc[score.gate.eq(gate) & score.split.eq("2026_jan_aug")]
        names = ["constant", "logistic_calendar", "logistic_full", "xgb_full"]
        values = [float(d.loc[d.model.eq(n), "brier"].iloc[0]) for n in names]
        axes[0, j].bar(range(4), values, color=[GRAY, BLUE, ORANGE, RED])
        axes[0, j].set_xticks(
            range(4), ["Constant", "Calendar", "Logistic", "XGBoost"], rotation=25
        )
        axes[0, j].set_title(f"{gate}: probability error (lower is better)")
        axes[0, j].set_ylabel("Brier score")
        cells = cal.loc[cal.gate.eq(gate) & cal.split.eq("2026_jan_aug")]
        axes[1, j].plot(cells.predicted, cells.observed, "o-", color=RED)
        axes[1, j].plot([0, 1], [0, 1], "--", color=GRAY)
        axes[1, j].set(
            xlabel="Mean estimated fraction in decile",
            ylabel="Actual recorded fraction",
            xlim=(0, 1),
            ylim=(0, 1),
            title=f"{gate}: calibration on 2026 actual states",
        )
    save(
        fig,
        "ml_occurrence",
        "XGBoost: ranking and calibration are separate tests",
        "Fixed models trained through 24 Dec 2025; seven-day gap; "
        "Jan–Aug 2026 complete-case actuals.\n"
        "Already explored period, no issued forecasts. Deciles are "
        "empirical groups, not calibrated trade odds.",
    )
    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    ps = pd.DataFrame(price_scores)
    for j, gate in enumerate("ABC"):
        d = ps.loc[ps.gate.eq(gate) & ps.split.eq("2026_jan_aug")]
        names = ["constant", "ridge_calendar", "ridge_full", "xgb_full"]
        axes[j].bar(
            range(4),
            [float(d.loc[d.model.eq(n), "rmse"].iloc[0]) for n in names],
            color=[GRAY, BLUE, ORANGE, RED],
        )
        axes[j].set_xticks(range(4), ["Constant", "Calendar", "Ridge", "XGBoost"], rotation=25)
        axes[j].set(title=f"{gate}: DA total-spread error", ylabel="RMSE ($/MWh)")
    save(
        fig,
        "ml_prices",
        "Predicting a record is different from explaining the DA price spread",
        "All complete eligible test hours, not just recorded rows; "
        "tails retained. Same frozen 2025 fit/2026 diagnostic.\n"
        "A/C local aggregate − Western; B Dominion Hub − Western. "
        "Same-hour actual inputs are not entry-time forecasts.",
    )
    return {
        "scores": scores,
        "ablations": ablations,
        "price_scores": price_scores,
        "support": support,
        "range_support": ranges,
        "features": features,
        "parameters": parameters,
        "monthly": monthly.to_dict("records"),
    }


def mechanism_investigation(panel, models):
    a = panel.loc[panel.flowgate.eq("Flowgate A") & panel.month.le(8)].copy()
    loads, regimes = [], []
    for gate in "ABC":
        f = panel.loc[panel.flowgate.eq(f"Flowgate {gate}") & panel.month.le(8)]
        for year, g in f.groupby("year"):
            regimes.append(
                {
                    "gate": gate,
                    "year": int(year),
                    "hours": len(g),
                    "records": int(g.event_recorded.sum()),
                    "rate": g.event_recorded.mean(),
                }
            )
    for period, frame in [("all", a), ("overnight_0_5", a.loc[a.hour.le(5)])]:
        for metric in ["zone_load_mw", "pjm_load_mw", "load::DOM", "load::MIDATL", "load::WEST"]:
            x = frame.dropna(subset=[metric])
            means = x.groupby(["month", "hour", "weekend", "year"])[metric].mean().unstack()
            means = means.dropna(subset=YEARS)
            counts = x.loc[x.year.eq(2024)].groupby(["month", "hour", "weekend"]).size()
            weights = counts.reindex(means.index)
            reference = np.average(means[2024], weights=weights)
            for year in YEARS:
                mean = np.average(means[year], weights=weights)
                loads.append(
                    {
                        "period": period,
                        "metric": metric,
                        "year": year,
                        "standardized_mean_mw": mean,
                        "change_from_2024_pct": 100 * (mean / reference - 1),
                        "common_cells": len(means),
                        "reference_hours": int(weights.sum()),
                    }
                )
    pd.DataFrame(loads).to_csv(TABLE / "a_load_regime.csv", index=False)
    pd.DataFrame(regimes).to_csv(TABLE / "regime_rates.csv", index=False)
    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    ar = [x for x in regimes if x["gate"] == "A"]
    axes[0].bar([x["year"] for x in ar], [100 * x["rate"] for x in ar], color=COLORS)
    axes[0].set(
        title="A: Jan–Aug supplied-row fraction", ylabel="Recorded labels (%)", xticks=YEARS
    )
    ld = pd.DataFrame(loads)
    labels = {"zone_load_mw": "BC zone", "load::DOM": "DOM zone", "pjm_load_mw": "PJM"}
    for metric, label in labels.items():
        d = ld.loc[ld.metric.eq(metric) & ld.period.eq("all")]
        axes[1].plot(d.year, d.change_from_2024_pct, "o-", label=label)
    axes[1].set(
        title="Same-calendar actual load change", ylabel="Change versus 2024 (%)", xticks=YEARS
    )
    axes[1].legend()
    monthly = pd.DataFrame(models["monthly"])
    d = monthly.loc[monthly.gate.eq("A") & monthly.split.eq("2026_jan_aug")]
    axes[2].plot(range(len(d)), 100 * d.actual, "o-", color=RED, label="Actual rows")
    axes[2].plot(range(len(d)), 100 * d.predicted, "o-", color=BLUE, label="Frozen 2025 model")
    axes[2].set_xticks(range(len(d)), d.month.str[-2:])
    axes[2].set(
        title="2026: does the old mapping transfer?",
        ylabel="Complete-case fraction (%)",
        xlabel="2026 month",
    )
    axes[2].legend()
    save(
        fig,
        "a_regime",
        "A: demand growth and a changing operating relationship",
        "Jan–Aug aligned years; identical month/hour/week-type load "
        "weights. Actual demand is not weather normalized.\n"
        "Model uses actual operating inputs, no customer type or "
        "network state. A residual gap cannot identify its cause.",
    )
    b = panel.loc[panel.flowgate.eq("Flowgate B")].copy()
    rows = []
    subsets = [("All", b), ("No Mar 2025", b.loc[b.year_month.ne("2025-03")])]
    subsets += [(f"No {year}", b.loc[b.year.ne(year)]) for year in YEARS]
    metrics = [
        "regional_solar_mw",
        "solar_ramp_3h",
        "local_dominion_total_da",
        "dominion_western_total_da",
        "dominion_western_total_rt",
    ]
    for scope, frame in subsets:
        for metric in metrics:
            rows.append({"scope": scope, "metric": metric, **matched(frame, metric)})
    pd.DataFrame(rows).to_csv(TABLE / "b_exclusions.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, metric, label in zip(
        axes,
        ["regional_solar_mw", "dominion_western_total_da"],
        ["SOUTH solar (MW)", "Dominion Hub − Western DA total ($/MWh)"],
        strict=True,
    ):
        d = [x for x in rows if x["metric"] == metric]
        x = np.arange(len(d))
        ax.vlines(x, [r["lower_95"] for r in d], [r["upper_95"] for r in d], color=BLUE)
        ax.scatter(x, [r["difference"] for r in d], color=BLUE, zorder=3)
        ax.set_xticks(x, [r["scope"] for r in d], rotation=25)
        ax.set_ylabel(label)
        ax.axhline(0, color=GRAY, lw=1)
        ax.set_title("Recorded − calendar-control contrast")
    save(
        fig,
        "b_robustness",
        "B: remove the dominant month and each year before trusting the story",
        "Same calendar estimator; weeks resampled on each retained "
        "subset. Support changes with exclusions.\n"
        "Solar robustness is different from hub-price direction. These "
        "are retrospective sensitivities, not causal experiments.",
    )
    c = panel.loc[panel.flowgate.eq("Flowgate C") & panel.month.le(8)]
    cr = []
    for year in YEARS:
        for weekend in [0, 1]:
            frame = c.loc[c.year.eq(year) & c.weekend.eq(weekend)]
            for metric in ["regional_wind_mw", "local_western_total_da", "local_western_total_rt"]:
                cr.append(
                    {"year": year, "weekend": weekend, "metric": metric, **matched(frame, metric)}
                )
    pd.DataFrame(cr).to_csv(TABLE / "c_weekday_weekend.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, metric, label in zip(
        axes,
        ["regional_wind_mw", "local_western_total_da"],
        ["WEST wind (MW)", "ComEd − Western DA total ($/MWh)"],
        strict=True,
    ):
        for weekend, offset, color in [(0, -0.10, BLUE), (1, 0.10, ORANGE)]:
            d = [r for r in cr if r["metric"] == metric and r["weekend"] == weekend]
            x = np.arange(3) + offset
            ax.vlines(x, [r["lower_95"] for r in d], [r["upper_95"] for r in d], color=color)
            ax.scatter(
                x,
                [r["difference"] for r in d],
                color=color,
                label="Weekend" if weekend else "Weekday",
                zorder=3,
            )
        ax.set_xticks(range(3), YEARS)
        ax.axhline(0, color=GRAY, lw=1)
        ax.set_ylabel(label)
        ax.legend()
        ax.set_title("Jan–Aug matched contrast")
    save(
        fig,
        "c_weekends",
        "C: test weekends directly instead of borrowing weekday joint odds",
        "Same-calendar recorded − absent contrasts, separate "
        "week-bootstrap ranges; support saved for every point.\n"
        "Weekends are not the full official off-peak calendar. All "
        "contract hours and settlement conventions still matter.",
    )
    return {"regime_rates": regimes, "a_load": loads, "b_exclusions": rows, "c_weekends": cr}


def graph_investigation(panel):
    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    price = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,congestion_price_da,congestion_price_rt "
        "FROM pjm_multi_node_hourly_lmps",
        connection,
        parse_dates=["timestamp_utc", "timestamp_ept"],
    )
    connection.close()
    assert not price.duplicated(["timestamp_utc", "pnode_name"]).any()
    price = price.loc[price.timestamp_ept.isin(panel.timestamp.unique())]
    edges, correlations, trees, labels = [], [], [], {}
    nodes = sorted(price.pnode_name.unique())
    assert len(nodes) == 17
    for name in nodes:
        if name.endswith("RESID_AGG"):
            labels[name] = name.replace("_RESID_AGG", " agg")
        elif "HUB" in name:
            labels[name] = name.replace(" HUB", " hub").replace("N ILLINOIS", "NI")
        else:
            labels[name] = name.split()[0].split("_")[0][:12]
    assert len(set(labels.values())) == 17
    for market in ["da", "rt"]:
        wide = price.pivot(
            index="timestamp_utc", columns="pnode_name", values=f"congestion_price_{market}"
        )
        timestamps = price.groupby("timestamp_utc").timestamp_ept.first().reindex(wide.index)
        for period in ["2024_2025_jan_aug", "2026_jan_aug"]:
            select = timestamps.dt.month.le(8)
            select &= (
                timestamps.dt.year.eq(2026)
                if period == "2026_jan_aug"
                else timestamps.dt.year.lt(2026)
            )
            d = wide.loc[select].dropna()
            t = timestamps.reindex(d.index)
            calendar = pd.DataFrame(
                {
                    "month": t.dt.to_period("M").astype(str),
                    "hour": t.dt.hour,
                    "weekend": t.dt.dayofweek.ge(5),
                }
            )
            residual = d - d.groupby([calendar[c] for c in calendar]).transform("mean")
            corr = residual.corr(method="spearman")
            assert np.isfinite(corr.to_numpy()).all()
            graph = nx.Graph()
            graph.add_nodes_from(nodes)
            for i, left in enumerate(nodes):
                for right in nodes[i + 1 :]:
                    rho = float(corr.loc[left, right])
                    distance = np.sqrt(max(0, 2 * (1 - rho)))
                    graph.add_edge(left, right, weight=distance, rho=rho)
                    correlations.append(
                        {
                            "period": period,
                            "market": market,
                            "left": left,
                            "right": right,
                            "rho": rho,
                            "hours": len(d),
                        }
                    )
            tree = nx.minimum_spanning_tree(graph)
            assert nx.is_tree(tree) and tree.number_of_edges() == 16
            for left, right, properties in tree.edges(data=True):
                edges.append(
                    {
                        "period": period,
                        "market": market,
                        "left": left,
                        "right": right,
                        **properties,
                        "hours": len(d),
                    }
                )
            if period == "2026_jan_aug":
                trees.append(tree)
    # Same deliberate layout in both markets: positions convey no geography.
    position = nx.circular_layout(nodes)
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    for ax, tree, market in zip(axes, trees, ["DA", "RT"], strict=True):
        colors = [
            ORANGE
            if name in {"DOM_RESID_AGG", "ACCA", "BASIN", "BELLWOOD"}
            else BLUE
            if name.endswith("HUB")
            else GRAY
            for name in nodes
        ]
        nx.draw_networkx_nodes(tree, position, ax=ax, node_size=180, node_color=colors)
        nx.draw_networkx_edges(tree, position, ax=ax, edge_color=GRAY, width=1.4)
        outer = {n: 1.17 * p for n, p in position.items()}
        nx.draw_networkx_labels(tree, outer, labels=labels, ax=ax, font_size=8)
        ax.set_title(f"2026 Jan–Aug {market} congestion co-movement tree")
        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-1.4, 1.4)
        ax.axis("off")
    save(
        fig,
        "price_graph",
        "Graph theory: shared congestion-price movements",
        "17 fixed nodes; within-calendar demeaned congestion; Spearman "
        "distance; 16 MST edges. Labels shortened in graph only.\n"
        "Edges summarize shared price movement, not power flow, "
        "physical proximity or the anonymous gate's sensitivities.",
    )
    pd.DataFrame(edges).to_csv(TABLE / "price_graph_edges.csv", index=False)
    pd.DataFrame(correlations).to_csv(TABLE / "price_graph_correlations.csv", index=False)
    pd.DataFrame([{"node": name, "label": label} for name, label in labels.items()]).to_csv(
        TABLE / "price_graph_nodes.csv", index=False
    )
    return {"nodes": 17, "edges_per_tree": 16, "correlations": correlations}


def c_block_investigation():
    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    price = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da "
        "FROM pjm_multi_node_hourly_lmps "
        "WHERE pnode_name IN ('COMED_RESID_AGG','WESTERN HUB')",
        connection,
        parse_dates=["timestamp_utc", "timestamp_ept"],
    )
    connection.close()
    assert not price.duplicated(["timestamp_utc", "pnode_name"]).any()
    wide = price.pivot(index="timestamp_utc", columns="pnode_name", values="total_lmp_da")
    eastern = wide.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    saved = price.groupby("timestamp_utc").timestamp_ept.first().reindex(wide.index)
    assert np.array_equal(eastern.to_numpy(), saved.to_numpy())
    holiday_rows = []
    for year in YEARS:
        for name, date in [
            ("New Year", pd.Timestamp(year, 1, 1)),
            ("Memorial", pd.date_range(f"{year}-05-01", f"{year}-05-31", freq="W-MON")[-1]),
            ("Independence", pd.Timestamp(year, 7, 4)),
            ("Labor", pd.date_range(f"{year}-09-01", f"{year}-09-07", freq="W-MON")[0]),
            ("Thanksgiving", pd.date_range(f"{year}-11-01", f"{year}-11-30", freq="W-THU")[3]),
            ("Christmas", pd.Timestamp(year, 12, 25)),
        ]:
            if date.dayofweek == 6:
                date += pd.Timedelta(days=1)
            holiday_rows.append({"name": name, "date": date.strftime("%Y-%m-%d")})
    holidays = pd.to_datetime([r["date"] for r in holiday_rows])
    d = pd.DataFrame(
        {
            "timestamp_utc": wide.index,
            "timestamp_ept": eastern,
            "spread": (wide.COMED_RESID_AGG - wide["WESTERN HUB"]).to_numpy(),
        }
    )
    d["date"] = d.timestamp_ept.dt.normalize()
    d["month"] = d.timestamp_ept.dt.to_period("M").astype(str)
    d["year"] = d.timestamp_ept.dt.year
    d["offpeak"] = (
        d.timestamp_ept.dt.dayofweek.ge(5)
        | d.date.isin(holidays)
        | d.timestamp_ept.dt.hour.lt(7)
        | d.timestamp_ept.dt.hour.eq(23)
    )
    assert len(d) == 23375 and d.spread.notna().all()
    monthly, annual = [], []
    for (month, offpeak), sample in d.groupby(["month", "offpeak"]):
        daily = sample.groupby("date").spread.mean()
        monthly.append(
            {
                "month": month,
                "block": "offpeak" if offpeak else "peak",
                "physical_hours": len(sample),
                "delivery_days": len(daily),
                "hour_weighted_mean": sample.spread.mean(),
                "equal_day_mean": daily.mean(),
                "p05_hour": sample.spread.quantile(0.05),
                "p95_hour": sample.spread.quantile(0.95),
            }
        )
    for (year, offpeak), sample in d.loc[d.timestamp_ept.dt.month.le(8)].groupby(
        ["year", "offpeak"]
    ):
        annual.append(
            {
                "year": int(year),
                "block": "offpeak" if offpeak else "peak",
                "physical_hours": len(sample),
                "mean": sample.spread.mean(),
                "median": sample.spread.median(),
                "negative_fraction": sample.spread.lt(0).mean(),
            }
        )
    pd.DataFrame(monthly).to_csv(TABLE / "c_block_monthly.csv", index=False)
    pd.DataFrame(annual).to_csv(TABLE / "c_block_yearly.csv", index=False)
    pd.DataFrame(holiday_rows).to_csv(TABLE / "block_holidays.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    m = pd.DataFrame(monthly)
    for block, color in [("offpeak", BLUE), ("peak", ORANGE)]:
        sample = m.loc[m.block.eq(block)]
        axes[0].plot(
            pd.to_datetime(sample.month),
            sample.hour_weighted_mean,
            color=color,
            label=block.title(),
        )
    off = m.loc[m.block.eq("offpeak")]
    axes[1].plot(
        pd.to_datetime(off.month), off.hour_weighted_mean, color=BLUE, label="Equal hour weights"
    )
    axes[1].plot(
        pd.to_datetime(off.month),
        off.equal_day_mean,
        color=ORANGE,
        linestyle="--",
        label="Equal delivery-day weights",
    )
    for ax in axes:
        ax.axhline(0, color=GRAY, lw=0.8)
        ax.set_ylabel("ComEd − Western DA total ($/MWh)")
        ax.legend()
        ax.tick_params(axis="x", rotation=30)
    axes[0].set_title("Every physical delivery hour in each class")
    axes[1].set_title("Off-peak averaging sensitivity")
    save(
        fig,
        "c_blocks",
        "C: complete-hour DA price benchmarks include ordinary and reversal states",
        "Published hour classes; all UTC hours retained, including "
        "holidays and repeated/gapped clock hours.\n"
        "Reconstructed price benchmarks, not official ICE settlements, "
        "entry quotes or returns. Averaging conventions need verification.",
    )
    return {
        "monthly": monthly,
        "yearly": annual,
        "physical_hours": len(d),
        "holiday_dates": holiday_rows,
    }


def investigate(panel):
    models = model_investigation(panel)
    print("Mechanism robustness", flush=True)
    mechanisms = mechanism_investigation(panel, models)
    graph = graph_investigation(panel)
    blocks = c_block_investigation()
    output = {
        "models": models,
        "mechanisms": mechanisms,
        "graph": graph,
        "c_blocks": blocks,
        "scope": (
            "Exploratory actual-state diagnostics; "
            "no causal attribution, issued forecast or ICE EV."
        ),
    }
    (OUT / "investigations.json").write_text(json.dumps(output, indent=2, default=float) + "\n")
    checks = {
        "chronological_seven_day_separation": True,
        "no_outcome_features": True,
        "common_complete_case_model_support": True,
        "fixed_model_parameters": True,
        "price_targets_include_absent_hours": True,
        "graph_utc_node_unique": True,
        "graph_nodes": 17,
        "edges_per_tree": 16,
        "models": len(models["scores"]),
        "price_models": len(models["price_scores"]),
        "new_figures": 7,
        "c_block_physical_hours": blocks["physical_hours"],
        "original_eligible_counts_preserved": panel.groupby("flowgate").size().to_dict(),
    }
    (OUT / "investigation_checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks), flush=True)


def local_supply_investigation(panel):
    """Test the nearby-output rival for A; do not infer plant availability."""
    path = ROOT / "data/raw/epa_baltimore_units_2024_2026q2.json.gz"
    manifest = json.loads((OUT / "local_supply_acquisition.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["compressed_sha256"]
    with gzip.open(path, "rt") as handle:
        raw = pd.DataFrame(json.load(handle))
    keys = ["facilityId", "unitId", "date", "hour"]
    assert not raw.duplicated(keys).any()
    assert raw.opTime.between(0, 1).all() and raw.hour.between(0, 23).all()
    assert set(zip(raw.facilityId, raw.unitId, strict=True)) == {
        (602, "1"),
        (602, "2"),
        (1554, "1"),
        (1554, "2"),
        (1554, "3"),
        (1554, "4"),
    }
    expected = pd.date_range("2024-01-01", "2026-06-30 23:00", freq="h")
    raw["standard_time"] = pd.to_datetime(raw.date) + pd.to_timedelta(raw.hour, unit="h")
    for _, unit in raw.groupby(["facilityId", "unitId"]):
        assert pd.DatetimeIndex(unit.standard_time).sort_values().equals(expected)
    # Only a present, explicitly nonoperating row implies zero gross energy.
    raw["gross_mwh"] = np.where(raw.opTime.eq(0), 0, raw.grossLoad * raw.opTime)
    coverage = []
    for (facility, unit), sample in raw.groupby(["facilityId", "unitId"]):
        coverage.append(
            {
                "facility_id": int(facility),
                "unit_id": unit,
                "rows": len(sample),
                "operating_rows": int(sample.opTime.gt(0).sum()),
                "missing_operating_gross_rows": int(
                    (sample.opTime.gt(0) & sample.grossLoad.isna()).sum()
                ),
            }
        )
    raw["utc"] = raw.standard_time.dt.tz_localize("Etc/GMT+5").dt.tz_convert("UTC")
    wide = raw.pivot(index="utc", columns=["facilityId", "unitId"], values="gross_mwh")
    units = pd.DataFrame(
        {
            "unit::brandon": wide[[(602, "1"), (602, "2")]].sum(axis=1, min_count=2),
            "unit::wagner134": wide[[(1554, "1"), (1554, "3"), (1554, "4")]].sum(
                axis=1, min_count=3
            ),
        }
    )
    assert units.notna().all().all()
    a = panel.loc[panel.flowgate.eq("Flowgate A")].copy()
    monthly = []
    for name, columns in [
        ("Brandon Shores units 1/2", [(602, "1"), (602, "2")]),
        ("Wagner electrical subtotal units 1/3/4", [(1554, "1"), (1554, "3"), (1554, "4")]),
    ]:
        sample = raw.loc[pd.MultiIndex.from_frame(raw[["facilityId", "unitId"]]).isin(columns)]
        for month, cell in sample.groupby(sample.date.str[:7]):
            hours = len(cell) // len(columns)
            energy = float(cell.gross_mwh.sum(min_count=len(cell)))
            gate = a.loc[a.year_month.eq(month)]
            monthly.append(
                {
                    "plant_series": name,
                    "month": month,
                    "year": int(month[:4]),
                    "month_number": int(month[5:]),
                    "physical_facility_hours": hours,
                    "gross_mwh": energy,
                    "gross_average_mw": energy / hours,
                    "eligible_gate_labels": len(gate),
                    "gate_records": int(gate.event_recorded.sum()),
                    "gate_fraction": float(gate.event_recorded.mean()),
                }
            )
    month_frame = pd.DataFrame(monthly)
    periods = []
    for name, sample in month_frame.groupby("plant_series"):
        for label, months in [("Jan–Jun", range(1, 7)), ("Apr–Jun", range(4, 7))]:
            for year, cell in sample.loc[sample.month_number.isin(months)].groupby("year"):
                periods.append(
                    {
                        "plant_series": name,
                        "period": label,
                        "year": int(year),
                        "physical_facility_hours": int(cell.physical_facility_hours.sum()),
                        "gross_mwh": float(cell.gross_mwh.sum()),
                        "gross_average_mw": float(
                            cell.gross_mwh.sum() / cell.physical_facility_hours.sum()
                        ),
                        "eligible_gate_labels": int(cell.eligible_gate_labels.sum()),
                        "gate_records": int(cell.gate_records.sum()),
                        "gate_fraction": float(
                            cell.gate_records.sum() / cell.eligible_gate_labels.sum()
                        ),
                    }
                )
    features = json.loads((OUT / "investigations.json").read_text())["models"]["features"]["A"]
    columns = sum(features.values(), [])
    unit_columns = list(units.columns)
    for name, value, period in [
        ("hour", a.hour, 24),
        ("month", a.month - 1, 12),
        ("weekday", a.weekday, 7),
    ]:
        a[f"{name}_sin"] = np.sin(2 * np.pi * value / period)
        a[f"{name}_cos"] = np.cos(2 * np.pi * value / period)
    parameters = dict(
        n_estimators=160,
        max_depth=3,
        learning_rate=0.05,
        min_child_weight=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5,
        tree_method="hist",
        n_jobs=2,
        random_state=20261008,
    )
    scores, predictions, comparisons, support = [], [], [], []
    for shift in [-1, 0, 1]:
        shifted = units.copy()
        shifted.index = (
            (shifted.index + pd.Timedelta(hours=shift))
            .tz_convert("America/New_York")
            .tz_localize(None)
        )
        # Repeated autumn labels are excluded, never averaged into an anonymous hour.
        shifted = shifted.loc[~shifted.index.duplicated(keep=False)]
        data = a.merge(
            shifted, left_on="timestamp", right_index=True, how="left", validate="one_to_one"
        )
        data = data.dropna(subset=columns + unit_columns)
        for split, cutoff, start, end in [
            ("2025_sep_dec", "2025-08-25", "2025-09-01", "2026-01-01"),
            ("2026_jan_jun", "2025-12-25", "2026-01-01", "2026-07-01"),
        ]:
            train = data.loc[data.timestamp.lt(cutoff)]
            test = data.loc[data.timestamp.ge(start) & data.timestamp.lt(end)]
            assert train.timestamp.max() < test.timestamp.min() - pd.Timedelta(days=7)
            support.append(
                {
                    "shift_hours": shift,
                    "split": split,
                    "train_hours": len(train),
                    "test_hours": len(test),
                    "train_end": str(train.timestamp.max()),
                    "test_start": str(test.timestamp.min()),
                    "test_end": str(test.timestamp.max()),
                }
            )
            probs = {}
            for name, estimator, use in [
                ("constant", None, columns),
                (
                    "logistic_full",
                    make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1500)),
                    columns,
                ),
                (
                    "logistic_units",
                    make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1500)),
                    columns + unit_columns,
                ),
                ("xgb_full", XGBClassifier(**parameters), columns),
                ("xgb_units", XGBClassifier(**parameters), columns + unit_columns),
            ]:
                if estimator is None:
                    probability = np.full(len(test), train.event_recorded.mean())
                else:
                    estimator.fit(train[use], train.event_recorded)
                    probability = estimator.predict_proba(test[use])[:, 1]
                probability = np.asarray(probability, dtype=np.float64)
                probs[name] = probability
                scores.append(
                    {
                        "shift_hours": shift,
                        "split": split,
                        "model": name,
                        "hours": len(test),
                        "observed_fraction": float(test.event_recorded.mean()),
                        "predicted_fraction": float(probability.mean()),
                        "brier": brier_score_loss(test.event_recorded, probability),
                    }
                )
                predictions.append(
                    pd.DataFrame(
                        {
                            "shift_hours": shift,
                            "split": split,
                            "model": name,
                            "timestamp": test.timestamp.to_numpy(),
                            "week": test.week.to_numpy(),
                            "observed": test.event_recorded.to_numpy(),
                            "probability": probability,
                        }
                    )
                )
            for method in ["logistic", "xgb"]:
                point, lower, upper = paired_brier_interval(
                    test, probs[f"{method}_full"], probs[f"{method}_units"]
                )
                comparisons.append(
                    {
                        "shift_hours": shift,
                        "split": split,
                        "method": method,
                        "brier_without_units_minus_with_units": point,
                        "lower_95": lower,
                        "upper_95": upper,
                    }
                )
    score_frame = pd.DataFrame(scores)
    prediction_frame = pd.concat(predictions, ignore_index=True)
    june = a.loc[a.month.eq(6)].copy()
    calendar = ["hour", "weekend"]
    weights = june.loc[june.year.eq(2025)].groupby(calendar).size() / 720
    june_rows = []
    for metric in [
        "zone_load_mw",
        "pjm_load_mw",
        "load::DOM",
        "wind::WEST",
        "event_recorded",
        "local_western_total_da",
    ]:
        for year in YEARS:
            cell = june.loc[june.year.eq(year)]
            means = cell.groupby(calendar)[metric].mean().reindex(weights.index)
            assert len(means) == 48 and means.notna().all()
            june_rows.append(
                {
                    "metric": metric,
                    "year": year,
                    "mean": float((means * weights).sum()),
                    "measurement_hours": int(cell[metric].notna().sum()),
                    "calendar_cells": len(means),
                    "method": "June-2025 hour/week-type weights",
                    "median": float(cell[metric].median()),
                    "p95": float(cell[metric].quantile(0.95)),
                }
            )
    for name, metric in [
        ("Brandon Shores units 1/2", "brandon_gross_mw"),
        ("Wagner electrical subtotal units 1/3/4", "wagner134_gross_mw"),
    ]:
        for r in monthly:
            if r["plant_series"] == name and r["month_number"] == 6:
                june_rows.append(
                    {
                        "metric": metric,
                        "year": r["year"],
                        "mean": r["gross_average_mw"],
                        "measurement_hours": r["physical_facility_hours"],
                        "calendar_cells": 0,
                        "method": "Complete EPA standard-clock June",
                        "median": None,
                        "p95": None,
                    }
                )
    june_frame = pd.DataFrame(june_rows)
    for name, frame in [
        ("a_unit_monthly", month_frame),
        ("a_unit_periods", pd.DataFrame(periods)),
        ("a_unit_scores", score_frame),
        ("a_unit_predictions", prediction_frame),
        ("a_unit_comparisons", pd.DataFrame(comparisons)),
        ("a_unit_coverage", pd.DataFrame(coverage)),
        ("a_unit_june", june_frame),
    ]:
        frame.to_csv(TABLE / f"{name}.csv", index=False)
    result = {
        "acquisition": manifest,
        "coverage": coverage,
        "monthly": monthly,
        "periods": periods,
        "june": june_rows,
        "scores": scores,
        "comparisons": comparisons,
        "support": support,
        "features": features,
        "unit_features": unit_columns,
        "clock_shift_hours": [-1, 0, 1],
        "quarter_cutoff": "2026-06-30",
        "wagner_unit_2_electrical_output_unknown": True,
        "retained_raw_rows": len(raw),
        "new_figures": 2,
    }
    (OUT / "local_supply.json").write_text(json.dumps(result, indent=2) + "\n")
    render_local_supply_figures(result)
    print(
        json.dumps({"local_supply_rows": len(raw), "unit_models": len(scores), "new_figures": 2}),
        flush=True,
    )


def render_local_supply_figures(result):
    """Draw the two unit checks from saved results without fitting models again."""
    month_frame = pd.DataFrame(result["monthly"])
    score_frame = pd.DataFrame(result["scores"])
    june_frame = pd.DataFrame(result["june"])
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5))
    bs = month_frame.loc[
        month_frame.plant_series.eq("Brandon Shores units 1/2") & month_frame.month_number.le(6)
    ]
    for year, color in zip(YEARS, COLORS, strict=True):
        cell = bs.loc[bs.year.eq(year)]
        axes[0].plot(cell.month_number, cell.gross_average_mw, "o-", color=color, label=str(year))
        axes[1].plot(
            cell.month_number, cell.gate_fraction * 100, "o-", color=color, label=str(year)
        )
    for ax in axes[:2]:
        ax.set_xticks(range(1, 7), ["Jan", "Feb", "Mar", "Apr", "May", "Jun"])
        ax.legend()
    axes[0].set(
        title="Brandon Shores actually generated", ylabel="Gross MWh / physical facility hour (MW)"
    )
    axes[1].set(title="A became more common", ylabel="Supplied-row fraction (%)")
    selected = score_frame.loc[
        score_frame.shift_hours.eq(0) & score_frame.split.eq("2026_jan_jun")
    ].set_index("model")
    names = ["logistic_full", "logistic_units", "xgb_full", "xgb_units"]
    axes[2].bar(
        range(4),
        [selected.loc[n, "predicted_fraction"] * 100 for n in names],
        color=[BLUE, ORANGE, BLUE, ORANGE],
    )
    axes[2].axhline(
        selected.loc["xgb_units", "observed_fraction"] * 100, color=RED, label="Observed"
    )
    axes[2].set_xticks(
        range(4),
        ["Logistic\nregional", "Logistic\n+ units", "XGBoost\nregional", "XGBoost\n+ units"],
    )
    axes[2].set(title="Does unit output explain 2026?", ylabel="Average row fraction (%)")
    axes[2].legend()
    save(
        fig,
        "a_local_supply",
        "A: more nearby generation did not prevent more records",
        "EPA actual gross output, Q2 cutoff. Wagner model subtotal excludes unit 2. "
        "Fixed 2025 fit; 2026 actuals.\nMore output can be a response to congestion. "
        "Neither plant is a verified relieving injection for anonymous A.",
    )
    levels = june_frame.set_index(["metric", "year"])
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5))
    metrics = [
        "zone_load_mw",
        "pjm_load_mw",
        "load::DOM",
        "wind::WEST",
        "brandon_gross_mw",
        "wagner134_gross_mw",
    ]
    changes = [
        (levels.loc[(m, 2026), "mean"] / levels.loc[(m, 2025), "mean"] - 1) * 100 for m in metrics
    ]
    axes[0].barh(range(6), changes, color=[BLUE] * 4 + [ORANGE] * 2)
    axes[0].set_yticks(
        range(6),
        [
            "BC demand",
            "PJM demand",
            "DOM demand",
            "WEST wind",
            "Brandon gross",
            "Wagner 1/3/4 gross",
        ],
    )
    axes[0].axvline(0, color=GRAY, lw=1)
    axes[0].set(title="Demand and generation changes", xlabel="June 2026 change from June 2025 (%)")
    for ax, metric, title, ylabel, scale in [
        (
            axes[1],
            "event_recorded",
            "Far more supplied A rows",
            "Share of hours with an A record (%)",
            100,
        ),
        (
            axes[2],
            "local_western_total_da",
            "A larger named DA premium",
            "BGE_RESID_AGG − WESTERN HUB ($/MWh)",
            1,
        ),
    ]:
        values = [levels.loc[(metric, year), "mean"] * scale for year in [2025, 2026]]
        ax.bar([0, 1], values, color=[ORANGE, RED])
        ax.set_xticks([0, 1], ["June 2025", "June 2026"])
        ax.set(title=title, ylabel=ylabel)
        for i, value in enumerate(values):
            ax.text(i, value, f"{value:.1f}", ha="center", va="bottom")
        ax.set_ylim(0, max(values) * 1.16)
    for field, marker, color, label in [
        ("median", "D", GRAY, "Raw hourly median"),
        ("p95", "^", BLUE, "Raw hourly 95th percentile"),
    ]:
        values = [levels.loc[("local_western_total_da", year), field] for year in [2025, 2026]]
        axes[2].scatter([0, 1], values, marker=marker, color=color, label=label, zorder=4)
    axes[2].set_ylim(0, levels.loc[("local_western_total_da", 2026), "p95"] * 1.3)
    axes[2].legend(fontsize=8, loc="upper left")
    save(
        fig,
        "a_june_check",
        "A: June worsened with lower average BC/PJM demand",
        "Both years use the same share of each time of day and weekday/weekend group; "
        "plant output uses complete months.\n"
        "Month chosen after reviewing the data. This compares averages, "
        "not identical operating conditions. Wagner subtotal fell 14 MW.",
    )


def b_investigation(panel):
    """Compare B with similar sunny states and retain fixed named-bus exposure."""
    target = ROOT / "results/short_case"
    tables = target / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    b = panel.loc[panel.flowgate.eq("Flowgate B")].copy().set_index("timestamp", drop=False)
    nodes = ["ACCA", "BASIN", "BELLWOOD", "DOM_RESID_AGG"]
    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    price = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da,total_lmp_rt,"
        "congestion_price_da,congestion_price_rt,marginal_loss_price_da,marginal_loss_price_rt,"
        "system_energy_price_da,system_energy_price_rt FROM pjm_multi_node_hourly_lmps "
        "WHERE pnode_name IN ('ACCA','BASIN','BELLWOOD','DOM_RESID_AGG','DOMINION HUB',"
        "'WESTERN HUB')",
        connection,
        parse_dates=["timestamp_utc", "timestamp_ept"],
    )
    connection.close()
    assert not price.duplicated(["timestamp_utc", "pnode_name"]).any()
    price = price.loc[price.timestamp_ept.isin(b.index)]
    assert not price.duplicated(["timestamp_ept", "pnode_name"]).any()
    wide = price.pivot(index="timestamp_ept", columns="pnode_name")
    metrics = [
        "regional_solar_mw",
        "zone_load_mw",
        "load::MIDATL",
        "wind::WEST",
        "pjm_gas_mw",
        "pjm_coal_mw",
        "pjm_nuclear_mw",
    ]
    for node in nodes:
        for market in ["da", "rt"]:
            for kind, field in [
                ("total", "total_lmp"),
                ("congestion", "congestion_price"),
                ("loss", "marginal_loss_price"),
            ]:
                name = f"{node}_hub_{kind}_{market}"
                b[name] = (
                    wide[f"{field}_{market}"][node] - wide[f"{field}_{market}"]["DOMINION HUB"]
                )
                metrics.append(name)
            assert np.allclose(
                wide[f"system_energy_price_{market}"][node],
                wide[f"system_energy_price_{market}"]["DOMINION HUB"],
            )
            assert np.allclose(
                b[f"{node}_hub_total_{market}"],
                b[f"{node}_hub_congestion_{market}"] + b[f"{node}_hub_loss_{market}"],
                atol=0.040002,
                rtol=0,
            )
        name = f"{node}_hub_congestion_rt_minus_da"
        b[name] = b[f"{node}_hub_congestion_rt"] - b[f"{node}_hub_congestion_da"]
        metrics.append(name)
    for pair in ["local_western", "dominion_western"]:
        for market in ["da", "rt"]:
            for kind in ["total", "congestion"]:
                metrics.append(f"{pair}_{kind}_{market}")
    all_daylight = b.loc[b.hour.between(8, 17)]
    complete = all_daylight.dropna(subset=metrics).reset_index(drop=True)
    scopes = [
        ("pooled", complete),
        ("without_march2025", complete.loc[~complete.year_month.eq("2025-03")]),
    ]
    scopes += [
        (f"jan_aug_{year}", complete.loc[complete.year.eq(year) & complete.month.le(8)])
        for year in [2024, 2025, 2026]
    ]
    metric_rows, support_rows, pair_rows, diff_rows = [], [], [], []

    def estimate(frame, targets, controls, block="week"):
        values = frame[metrics].to_numpy(dtype=float)
        ti = np.asarray(targets)
        width = max(map(len, controls))
        ci = np.zeros((len(ti), width), dtype=int)
        mask = np.zeros_like(ci, dtype=bool)
        for row, indices in enumerate(controls):
            ci[row, : len(indices)] = indices
            mask[row, : len(indices)] = True
        neighbor_values = values[ci]
        means = (neighbor_values * mask[:, :, None]).sum(axis=1) / mask.sum(axis=1)[:, None]
        differences = values[ti] - means
        week_ids, draws = bootstrap_weights(frame, block)
        wi = frame[block].map(week_ids).to_numpy()

        def weighted(counts):
            tw = counts[wi[ti]]
            cw = counts[wi[ci]] * mask
            denom = cw.sum(axis=1)
            use = (tw > 0) & (denom > 0)
            if not use.any():
                return np.full(len(metrics), np.nan)
            cm = (neighbor_values[use] * cw[use, :, None]).sum(axis=1) / denom[use, None]
            return np.average(values[ti[use]] - cm, weights=tw[use], axis=0)

        samples = np.array([weighted(draw) for draw in draws])
        limits = np.nanquantile(samples, [0.025, 0.975], axis=0)
        loo = []
        for index in range(len(week_ids)):
            counts = np.ones(len(week_ids))
            counts[index] = 0
            loo.append(weighted(counts))
        loo = np.array(loo)
        return differences, means, limits, np.nanmin(loo, axis=0), np.nanmax(loo, axis=0)

    for scope, frame in scopes:
        frame = frame.reset_index(drop=True)
        groups = []
        for _, group in frame.groupby(CALENDAR):
            control = group.index[group.event_recorded.eq(0)].to_numpy()
            records = group.index[group.event_recorded.eq(1)].to_numpy()
            if len(control) >= 3 and len(records):
                groups.append((records, control))
        variants = [("calendar_full", None, None)]
        variants += [
            (f"{name}_{estimator}", solar, load)
            for name, solar, load in [
                ("loose", 500, 2000),
                ("strict", 250, 1000),
                ("context", 500, 2000),
            ]
            for estimator in ["calendar_same_targets", "solar_load_matched"]
        ]
        selections = {}
        for name, solar, load in [
            ("loose", 500, 2000),
            ("strict", 250, 1000),
            ("context", 500, 2000),
        ]:
            targets, neighbors, calendar_controls = [], [], []
            for records, controls in groups:
                for record in records:
                    ds = np.abs(
                        frame.loc[controls, "regional_solar_mw"].to_numpy()
                        - frame.loc[record, "regional_solar_mw"]
                    )
                    dl = np.abs(
                        frame.loc[controls, "zone_load_mw"].to_numpy()
                        - frame.loc[record, "zone_load_mw"]
                    )
                    keep = (ds <= solar) & (dl <= load)
                    distance = (ds / solar) ** 2 + (dl / load) ** 2
                    if name == "context":
                        dm = np.abs(
                            frame.loc[controls, "load::MIDATL"].to_numpy()
                            - frame.loc[record, "load::MIDATL"]
                        )
                        dw = np.abs(
                            frame.loc[controls, "wind::WEST"].to_numpy()
                            - frame.loc[record, "wind::WEST"]
                        )
                        keep &= (dm <= 2000) & (dw <= 1000)
                        distance += (dm / 2000) ** 2 + (dw / 1000) ** 2
                    if keep.sum() < 3:
                        continue
                    indices = np.argsort(distance[keep], kind="stable")[:3]
                    targets.append(record)
                    neighbors.append(controls[keep][indices])
                    calendar_controls.append(controls)
            selections[name] = (targets, neighbors, calendar_controls)
        for variant, solar, load in variants:
            if variant == "calendar_full":
                targets = [int(r) for records, _ in groups for r in records]
                controls = [indices for records, indices in groups for _ in records]
            else:
                targets, neighbors, calendar_controls = selections[variant.split("_")[0]]
                controls = (
                    neighbors if variant.endswith("solar_load_matched") else calendar_controls
                )
            if not targets:
                continue
            differences, means, intervals, lo, hi = estimate(frame, targets, controls)
            fortnight = (
                estimate(frame, targets, controls, "fortnight")[2]
                if variant.endswith("solar_load_matched") and scope == "pooled"
                else None
            )
            selected = frame.iloc[targets]
            distinct_controls = sorted({int(c) for indices in controls for c in indices})
            support_rows.append(
                {
                    "scope": scope,
                    "variant": variant,
                    "solar_caliper_mw": solar,
                    "load_caliper_mw": load,
                    "midatl_caliper_mw": 2000 if variant.startswith("context_") else None,
                    "west_wind_caliper_mw": 1000 if variant.startswith("context_") else None,
                    "available_hours": len(frame),
                    "available_records": int(frame.event_recorded.sum()),
                    "matched_records": len(targets),
                    "matched_dates": selected.date.nunique(),
                    "unique_controls": len(distinct_controls),
                    "unmatched_records": int(frame.event_recorded.sum()) - len(targets),
                    "calendar_weeks": frame.week.nunique(),
                }
            )
            for index, metric in enumerate(metrics):
                difference = differences[:, index]
                metric_rows.append(
                    {
                        "scope": scope,
                        "variant": variant,
                        "metric": metric,
                        "difference": difference.mean(),
                        "lower_95": intervals[0, index],
                        "upper_95": intervals[1, index],
                        "matched_record_mean": selected[metric].mean(),
                        "matched_control_mean": means[:, index].mean(),
                        "median_hour_difference": np.median(difference),
                        "positive_fraction": np.mean(difference > 0),
                        "p05_hour_difference": np.quantile(difference, 0.05),
                        "p95_hour_difference": np.quantile(difference, 0.95),
                        "leave_one_week_min": lo[index],
                        "leave_one_week_max": hi[index],
                        "fortnight_lower_95": None if fortnight is None else fortnight[0, index],
                        "fortnight_upper_95": None if fortnight is None else fortnight[1, index],
                        "matched_records": len(targets),
                    }
                )
            for index, (record, indices) in enumerate(zip(targets, controls, strict=True)):
                row = {
                    "scope": scope,
                    "variant": variant,
                    "timestamp": frame.loc[record, "timestamp"],
                }
                row.update(dict(zip(metrics, differences[index], strict=True)))
                diff_rows.append(row)
                for rank, control in enumerate(indices, 1):
                    pair_rows.append(
                        {
                            "scope": scope,
                            "variant": variant,
                            "record_timestamp": frame.loc[record, "timestamp"],
                            "control_timestamp": frame.loc[control, "timestamp"],
                            "rank": rank,
                            "solar_difference_mw": frame.loc[record, "regional_solar_mw"]
                            - frame.loc[control, "regional_solar_mw"],
                            "load_difference_mw": frame.loc[record, "zone_load_mw"]
                            - frame.loc[control, "zone_load_mw"],
                        }
                    )
    outputs = {
        "b_matched_metrics": metric_rows,
        "b_matched_support": support_rows,
        "b_control_pairs": pair_rows,
        "b_hour_differences": diff_rows,
    }
    for name, rows in outputs.items():
        pd.DataFrame(rows).to_csv(tables / f"{name}.csv", index=False)
    result = {
        "date": "2026-10-08",
        "question": (
            "Does a local RT price signature survive similar solar and DOM-demand controls?"
        ),
        "nodes": nodes,
        "hours": "Supplied labels 08–17",
        "daylight_records_before_common_support": int(all_daylight.event_recorded.sum()),
        "daylight_records_common_support": int(complete.event_recorded.sum()),
        "bootstrap_replicates": BOOTSTRAPS,
        "same_hour_actuals": True,
        "causal_identification": False,
        "new_measurements": False,
        "source_ids": [
            "D00",
            "D01",
            "D02",
            "D03",
            "D04",
            "D05",
            "A29",
            "A32",
            "P01",
            "P06",
            "P11",
            "T02",
            "ST01",
        ],
        "metrics": len(metrics),
        "table_rows": {name: len(rows) for name, rows in outputs.items()},
        "limits": (
            "Fixed neighbors; exploratory specification; incomplete overlap; "
            "unknown B market/clock/coverage; unnamed equipment; no issued odds or trade EV."
        ),
    }
    (target / "b_investigation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


def uncertainty_investigation(panel):
    """Extend established states to price exposure; no forecast probabilities."""
    target = ROOT / "results/short_case"
    tables = target / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    old_joint = pd.read_csv(TABLE / "joint_conditions.csv")
    state_rows, difference_rows, distribution_rows = [], [], []
    specs = {
        "A": ("pjm_load_mw", "wind::WEST", None),
        "B": ("regional_solar_mw", "zone_load_mw", (8, 17)),
        "C": ("wind::WEST", "load::MIDATL", None),
    }
    checked = 0
    for gate, (first, second, hours) in specs.items():
        frame = panel.loc[panel.flowgate.eq(f"Flowgate {gate}") & panel.month.le(8)]
        pairs = ["local_western"]
        if gate == "B":
            pairs += ["local_dominion", "dominion_western"]
        metrics = [
            f"{pair}_{kind}_{market}"
            for pair in pairs
            for kind in ["total", "congestion"]
            for market in ["da", "rt"]
        ]
        for year, yearly in frame.groupby("year"):
            for status, sample in yearly.groupby("event_recorded"):
                for metric in metrics:
                    distribution_rows.append(
                        {
                            "gate": gate,
                            "year": int(year),
                            "recorded": int(status),
                            "metric": metric,
                            **distribution(sample[metric]),
                        }
                    )
            data = yearly.dropna(subset=[first, second]).copy()
            if hours:
                data = data.loc[data.hour.between(*hours)]
            available = len(data)
            data["cell"] = 2 * data[first].gt(
                data.groupby(CALENDAR)[first].transform("median")
            ) + data[second].gt(data.groupby(CALENDAR)[second].transform("median"))
            counts = data.groupby([*CALENDAR, "cell"]).size().unstack("cell", fill_value=0)
            keep = counts.reindex(columns=range(4), fill_value=0).ge(3).all(axis=1)
            data = (
                data.set_index(CALENDAR)
                .loc[lambda x: x.index.isin(counts.index[keep])]
                .reset_index()
            )
            totals = data.groupby(CALENDAR).size()
            data = data.join(totals.rename("stratum_hours"), on=CALENDAR)
            data["cell_hours"] = data.groupby([*CALENDAR, "cell"])["cell"].transform("size")
            data["weight"] = data.stratum_hours / data.cell_hours
            weeks, draws = bootstrap_weights(data)
            boot = {}
            for cell, sample in data.groupby("cell"):
                previous = old_joint.loc[
                    old_joint.flowgate.eq(gate)
                    & old_joint.year.eq(year)
                    & old_joint.pair.eq(0)
                    & old_joint.cell.eq(cell)
                ].iloc[0]
                rate = np.average(sample.event_recorded, weights=sample.weight)
                assert np.isclose(rate, previous.rate, atol=1e-12)
                assert len(sample) == previous.hours
                assert sample.event_recorded.sum() == previous.recorded_hours
                assert len(data) == previous.retained_hours and data.weekend.sum() == 0
                checked += 4
                for metric in ["event_recorded", *metrics]:
                    assert sample[metric].notna().all()
                    mean = np.average(sample[metric], weights=sample.weight)
                    num = (
                        sample.assign(weighted=sample.weight * sample[metric])
                        .groupby("week")
                        .weighted.sum()
                        .reindex(weeks, fill_value=0)
                        .to_numpy()
                    )
                    den = (
                        sample.groupby("week").weight.sum().reindex(weeks, fill_value=0).to_numpy()
                    )
                    estimates = (draws @ num) / (draws @ den)
                    boot[cell, metric] = estimates
                    low, high = np.quantile(estimates, [0.025, 0.975])
                    if metric == "event_recorded":
                        assert np.allclose([low, high], [previous.lower_95, previous.upper_95])
                        checked += 2
                    state_rows.append(
                        {
                            "gate": gate,
                            "year": int(year),
                            "cell": int(cell),
                            "first": first,
                            "second": second,
                            "metric": metric,
                            "mean": float(mean),
                            "lower_95": float(low),
                            "upper_95": float(high),
                            "hours": len(sample),
                            "recorded_hours": int(sample.event_recorded.sum()),
                            "groups": int(keep.sum()),
                            "retained_hours": len(data),
                            "available_hours": available,
                            "weekend_hours": int(data.weekend.sum()),
                        }
                    )
            for metric in ["event_recorded", *metrics]:
                rows = [
                    r
                    for r in state_rows
                    if r["gate"] == gate and r["year"] == year and r["metric"] == metric
                ]
                for higher in range(1, 4):
                    for lower in range(higher):
                        delta = boot[higher, metric] - boot[lower, metric]
                        difference_rows.append(
                            {
                                "gate": gate,
                                "year": int(year),
                                "metric": metric,
                                "higher_cell": higher,
                                "lower_cell": lower,
                                "contrast": f"cell {higher} minus cell {lower}",
                                "difference": rows[higher]["mean"] - rows[lower]["mean"],
                                "lower_95": float(np.quantile(delta, 0.025)),
                                "upper_95": float(np.quantile(delta, 0.975)),
                            }
                        )

    connection = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
    price = pd.read_sql_query(
        "SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da "
        "FROM pjm_multi_node_hourly_lmps "
        "WHERE pnode_name IN ('BGE_RESID_AGG','DOMINION HUB',"
        "'COMED_RESID_AGG','WESTERN HUB')",
        connection,
        parse_dates=["timestamp_utc", "timestamp_ept"],
    )
    connection.close()
    assert not price.duplicated(["timestamp_utc", "pnode_name"]).any()
    wide = price.pivot(index="timestamp_utc", columns="pnode_name", values="total_lmp_da")
    eastern = wide.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    stored = price.groupby("timestamp_utc").timestamp_ept.first().reindex(wide.index)
    assert np.array_equal(eastern.to_numpy(), stored.to_numpy())
    assert len(wide) == 23375 and wide.notna().all().all()
    holidays = pd.to_datetime(pd.read_csv(TABLE / "block_holidays.csv").date)
    clock = pd.DataFrame({"timestamp_utc": wide.index, "timestamp": eastern})
    clock["date"] = clock.timestamp.dt.normalize()
    clock["year"] = clock.timestamp.dt.year
    clock["month"] = clock.timestamp.dt.to_period("M").astype(str)
    clock["offpeak"] = (
        clock.timestamp.dt.dayofweek.ge(5)
        | clock.date.isin(holidays)
        | clock.timestamp.dt.hour.lt(7)
        | clock.timestamp.dt.hour.eq(23)
    )
    blocks, annual, accounting, hourly = [], [], [], []
    for gate, node, block in [
        ("A", "BGE_RESID_AGG", "peak"),
        ("B", "DOMINION HUB", "peak"),
        ("C", "COMED_RESID_AGG", "offpeak"),
    ]:
        data = clock.copy()
        data["spread"] = (wide[node] - wide["WESTERN HUB"]).to_numpy()
        data = data.loc[data.offpeak.eq(block == "offpeak")].copy()
        data["gate"], data["pair"], data["block"] = gate, f"{node} minus WESTERN HUB", block
        hourly.append(data)
        for month, sample in data.groupby("month"):
            blocks.append(
                {
                    "gate": gate,
                    "pair": f"{node} minus WESTERN HUB",
                    "block": block,
                    "month": month,
                    "physical_hours": len(sample),
                    "delivery_days": sample.date.nunique(),
                    "mean": sample.spread.mean(),
                    "equal_day_mean": sample.groupby("date").spread.mean().mean(),
                    "median_hour": sample.spread.median(),
                    "p05_hour": sample.spread.quantile(0.05),
                    "p95_hour": sample.spread.quantile(0.95),
                }
            )
        for year, sample in data.loc[data.timestamp.dt.month.le(8)].groupby("year"):
            annual.append(
                {"gate": gate, "year": int(year), "block": block, **distribution(sample.spread)}
            )
        joined = data.merge(
            panel.loc[panel.flowgate.eq(f"Flowgate {gate}"), ["timestamp", "event_recorded"]],
            on="timestamp",
            how="left",
            validate="many_to_one",
        )
        for month, sample in joined.groupby("month"):
            eligible = sample.dropna(subset=["event_recorded"])
            present = eligible.event_recorded.eq(1)
            fraction = present.mean()
            record_mean = eligible.loc[present, "spread"].mean() if present.any() else None
            absent_mean = eligible.loc[~present, "spread"].mean() if (~present).any() else None
            record_contribution = fraction * record_mean if record_mean is not None else 0.0
            absent_contribution = (1 - fraction) * absent_mean if absent_mean is not None else 0.0
            assert np.isclose(eligible.spread.mean(), record_contribution + absent_contribution)
            accounting.append(
                {
                    "gate": gate,
                    "month": month,
                    "block": block,
                    "eligible_hours": len(eligible),
                    "clock_excluded_hours": len(sample) - len(eligible),
                    "recorded_hours": int(present.sum()),
                    "record_fraction": fraction,
                    "recorded_mean": record_mean,
                    "absent_mean": absent_mean,
                    "recorded_contribution": record_contribution,
                    "absent_contribution": absent_contribution,
                    "eligible_mean": eligible.spread.mean(),
                    "physical_mean": sample.spread.mean(),
                }
            )
    monthly = pd.DataFrame(blocks)
    c = monthly.loc[monthly.gate.eq("C")].set_index("month")
    old_c = (
        pd.read_csv(TABLE / "c_block_monthly.csv").query("block == 'offpeak'").set_index("month")
    )
    assert np.allclose(c["mean"], old_c.hour_weighted_mean.reindex(c.index), atol=1e-11)
    assert np.array_equal(c.physical_hours, old_c.physical_hours.reindex(c.index))
    artifacts = {
        "joint_price_states": state_rows,
        "joint_price_differences": difference_rows,
        "price_distributions": distribution_rows,
        "block_monthly": blocks,
        "block_yearly": annual,
        "record_accounting": accounting,
    }
    for name, rows in artifacts.items():
        pd.DataFrame(rows).to_csv(tables / f"{name}.csv", index=False)
    pd.concat(hourly, ignore_index=True).to_csv(tables / "block_hourly.csv", index=False)
    selected_month_stats = []
    for gate, sample in monthly.groupby("gate"):
        stats = distribution(sample["mean"])
        stats["months"] = stats.pop("hours")
        selected_month_stats.append(
            {"gate": gate, "statistic": "distribution of observed monthly means", **stats}
        )
    result = {
        "date": "2026-10-08",
        "scope": "Retrospective actual-state and physical-hour price diagnostics",
        "forecast_probabilities_estimated": False,
        "physical_hours_per_node": len(wide),
        "joint_frequency_support_scalars_reconciled": checked,
        "monthly_mean_distribution": selected_month_stats,
        "table_rows": {name: len(rows) for name, rows in artifacts.items()},
        "c_monthly_reconstruction_reconciled": True,
        "limits": (
            "Anonymous cause, export completeness, issue-time odds, "
            "official settlements and live EV remain unverified."
        ),
    }
    (target / "uncertainty.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2), flush=True)


def density_investigation(panel):
    """Descriptive densities with exact counts; see the density methods note."""
    target = ROOT / "results/short_case"
    tables = target / "tables"
    comparisons = {}
    for gate in "ABC":
        frame = panel.loc[
            panel.flowgate.eq(f"Flowgate {gate}") & panel.year.eq(2026) & panel.month.le(8)
        ]
        specifications = (
            [
                ("local_western_total_da", "DA local aggregate minus Western"),
                ("dominion_western_total_da", "DA Dominion Hub minus Western"),
            ]
            if gate == "B"
            else [
                (f"local_western_total_{market}", f"{market.upper()} local aggregate minus Western")
                for market in ["da", "rt"]
            ]
        )
        for metric, label in specifications:
            comparisons[f"{gate}_{metric}"] = {
                "figure": f"{gate.lower()}_density",
                "label": label,
                "samples": {
                    status: frame.loc[frame.event_recorded.eq(recorded), metric].dropna().to_numpy()
                    for status, recorded in [("Nonbinding", 0), ("Binding", 1)]
                },
            }
    differences = pd.read_csv(tables / "b_hour_differences.csv")
    differences = differences.loc[
        differences.scope.eq("pooled") & differences.variant.eq("loose_solar_load_matched")
    ]
    assert len(differences) == 504 and not differences.timestamp.duplicated().any()
    for bus in ["ACCA", "BASIN", "BELLWOOD"]:
        comparisons[f"B_matched_{bus}"] = {
            "figure": "b_matched_density",
            "label": f"{bus} minus Dominion Hub: RT congestion",
            "samples": {"Matched differences": differences[f"{bus}_hub_congestion_rt"].to_numpy()},
        }
    blocks = pd.read_csv(tables / "block_hourly.csv", parse_dates=["timestamp"])
    for gate in "ABC":
        frame = blocks.loc[blocks.gate.eq(gate) & blocks.timestamp.dt.month.le(8)]
        comparisons[f"{gate}_block"] = {
            "figure": "block_density",
            "label": f"{gate}: {frame.pair.iloc[0]} ({frame.block.iloc[0]})",
            "samples": {
                str(year): frame.loc[frame.year.eq(year), "spread"].to_numpy() for year in YEARS
            },
        }
    metrics, curves, histograms = [], [], []
    for comparison, specification in comparisons.items():
        pooled = np.concatenate(list(specification["samples"].values()))
        assert np.isfinite(pooled).all()
        lo, hi = np.quantile(pooled, [0.05, 0.95])
        sd = pooled.std(ddof=1)
        robust_scale = min(sd, np.subtract(*np.quantile(pooled, [0.75, 0.25])) / 1.349)
        bandwidth = float(0.9 * robust_scale * len(pooled) ** (-0.2))
        assert bandwidth > 0 and hi > lo
        grid = np.linspace(lo, hi, 601)
        edges = np.linspace(lo, hi, 37)
        for label, sample in specification["samples"].items():
            sample = np.sort(sample)
            n = len(sample)
            tail_n = int(np.ceil(0.05 * n))
            central = sample[tail_n:-tail_n]
            row = {
                "comparison": comparison,
                "figure": specification["figure"],
                "label": specification["label"],
                "sample": label,
                **distribution(pd.Series(sample)),
                "fraction_nonpositive": float(np.mean(sample <= 0)),
                "fraction_above_10": float(np.mean(sample > 10)),
                "fraction_above_20": float(np.mean(sample > 20)),
                "fraction_below_minus20": float(np.mean(sample < -20)),
                "view_low": float(lo),
                "view_high": float(hi),
                "fraction_outside_view": float(np.mean((sample < lo) | (sample > hi))),
                "bandwidth_dollars": bandwidth,
                "tail_hours_each": tail_n,
                "lower_tail_mean_contribution": float(sample[:tail_n].sum() / n),
                "central_mean_contribution": float(central.sum() / n),
                "upper_tail_mean_contribution": float(sample[-tail_n:].sum() / n),
                "central_90pct_mean": float(central.mean()),
            }
            for multiplier in [0.5, 1.0, 2.0]:
                kde = gaussian_kde(sample, bw_method=bandwidth * multiplier / sample.std(ddof=1))
                density = kde(grid)
                assert np.isclose(kde.integrate_box_1d(-np.inf, np.inf), 1)
                row[f"mode_bw_{multiplier:g}"] = float(grid[density.argmax()])
                for x, y in zip(grid, density, strict=True):
                    curves.append(
                        {
                            "comparison": comparison,
                            "sample": label,
                            "bandwidth_multiplier": multiplier,
                            "spread": float(x),
                            "density": float(y),
                        }
                    )
            counts, _ = np.histogram(sample, bins=edges)
            for left, right, count in zip(edges[:-1], edges[1:], counts, strict=True):
                histograms.append(
                    {
                        "comparison": comparison,
                        "sample": label,
                        "left": float(left),
                        "right": float(right),
                        "count": int(count),
                        "density": float(count / (n * (right - left))),
                    }
                )
            assert np.isclose(
                sum(
                    row[k]
                    for k in [
                        "lower_tail_mean_contribution",
                        "central_mean_contribution",
                        "upper_tail_mean_contribution",
                    ]
                ),
                row["mean"],
            )
            metrics.append(row)
    for name, rows in [
        ("density_metrics", metrics),
        ("density_curves", curves),
        ("density_histograms", histograms),
    ]:
        pd.DataFrame(rows).to_csv(tables / f"{name}.csv", index=False)
    inputs = [
        ROOT / "data/pjm.sqlite",
        tables / "b_hour_differences.csv",
        tables / "block_hourly.csv",
    ]
    result = {
        "version": "density_revision_v5",
        "comparisons": len(comparisons),
        "samples": len(metrics),
        "figures": ["a_density", "b_density", "c_density", "b_matched_density", "block_density"],
        "input_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in inputs
        },
        "methods": "scripts/analyze_flowgates.md#price-density-views-user-requested-8-october-2026",
        "limits": (
            "Descriptive smoothing of unchanged hourly samples; no new causal identification, "
            "future odds or trade EV."
        ),
    }
    (target / "density_investigation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--investigations-only", action="store_true")
    parser.add_argument("--local-supply-only", action="store_true")
    parser.add_argument("--uncertainty-only", action="store_true")
    parser.add_argument("--b-investigation-only", action="store_true")
    parser.add_argument("--density-only", action="store_true")
    arguments = parser.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    TABLE.mkdir(parents=True, exist_ok=True)
    panel, fuel_columns = prepare()
    if arguments.density_only:
        density_investigation(panel)
        return
    if arguments.b_investigation_only:
        b_investigation(panel)
        return
    if arguments.uncertainty_only:
        uncertainty_investigation(panel)
        return
    if arguments.local_supply_only:
        local_supply_investigation(panel)
        return
    if arguments.investigations_only:
        investigate(panel)
        return
    (
        comparison_rows,
        distribution_rows,
        dose_rows,
        joint_rows,
        timing_rows,
        year_rows,
        shadow_rows,
    ) = ([] for _ in range(7))
    summary = {
        "sample": {
            "eligible_hours_per_gate": 23256,
            "clock_change_dates_excluded": 5,
            "bootstrap_replicates": BOOTSTRAPS,
            "bootstrap_block": "calendar Monday–Sunday week",
            "price_source": "A32 hourly paired current-version prices; "
            "separate from supplied RT and A28 settled feed",
        },
        "gates": {},
    }
    sensitivity_rows = []
    context_rows = []
    for gate in "ABC":
        print(f"Analyzing {gate}", flush=True)
        frame = panel.loc[panel.flowgate.eq(f"Flowgate {gate}")].copy()
        metrics = [name for name in frame if name.startswith("load::") or name.startswith("wind::")]
        metrics += (
            list(LABELS)
            + fuel_columns
            + [name.replace("_mw", "_share_pct") for name in fuel_columns]
        )
        metrics += [name for name in frame if name.startswith("local_western_")]
        if gate == "B":
            metrics += [
                name
                for name in frame
                if name.startswith("local_dominion_") or name.startswith("dominion_western_")
            ]
        effects = {metric: matched(frame, metric) for metric in dict.fromkeys(metrics)}
        lead = {"A": "pjm_load_mw", "B": "regional_solar_mw", "C": "regional_wind_mw"}[gate]
        trade_pair = "dominion_western" if gate == "B" else "local_western"
        sensitivity_metrics = [lead] + [
            f"{trade_pair}_{component}_{market}"
            for market in ["da", "rt"]
            for component in ["total", "congestion"]
        ]
        for metric in sensitivity_metrics:
            for block in ["day", "week", "fortnight"]:
                values = effects[metric] if block == "week" else matched(frame, metric, block=block)
                sensitivity_rows.append({"flowgate": gate, "metric": metric, **values})
        for metric, values in effects.items():
            comparison_rows.append({"flowgate": gate, "scope": "all", "metric": metric, **values})
        distributions = {}
        for metric in [
            "shadow_magnitude",
            *[name for name in frame if name.startswith("local_western_")],
        ]:
            for recorded in [1] if metric == "shadow_magnitude" else [0, 1]:
                values = distribution(frame.loc[frame.event_recorded.eq(recorded), metric])
                distributions[f"{metric}:recorded={recorded}"] = values
                distribution_rows.append(
                    {"flowgate": gate, "metric": metric, "recorded": recorded, **values}
                )
        if gate == "B":
            for metric in [
                name
                for name in frame
                if name.startswith("local_dominion_") or name.startswith("dominion_western_")
            ]:
                for recorded in [0, 1]:
                    values = distribution(frame.loc[frame.event_recorded.eq(recorded), metric])
                    distributions[f"{metric}:recorded={recorded}"] = values
                    distribution_rows.append(
                        {"flowgate": gate, "metric": metric, "recorded": recorded, **values}
                    )
        timing_rows.extend(timing(frame, gate))
        dose_rows.extend(driver_curves(frame, gate))
        load_wind(frame, gate, effects)
        context_rows.extend(load_context(frame, gate))
        solar_fuels(frame, gate, effects, fuel_columns)
        joint_rows.extend(joint_plot(frame, gate))
        price_distributions(frame, gate)
        annual, shadows = price_regimes(frame, gate)
        year_rows.extend(annual)
        shadow_rows.extend(shadows)
        summary["gates"][gate] = {
            "hours": len(frame),
            "recorded_hours": int(frame.event_recorded.sum()),
            "recorded_fraction": float(frame.event_recorded.mean()),
            "matched_contrasts": effects,
            "distributions": distributions,
            "year_prices": annual,
            "shadow_to_price": shadows,
        }
    for name, rows in [
        ("matched_contrasts", comparison_rows),
        ("distributions", distribution_rows),
        ("driver_curves", dose_rows),
        ("joint_conditions", joint_rows),
        ("timing", timing_rows),
        ("year_prices", year_rows),
        ("shadow_to_price", shadow_rows),
        ("bootstrap_sensitivity", sensitivity_rows),
        ("load_context", context_rows),
    ]:
        pd.DataFrame(rows).to_csv(TABLE / f"{name}.csv", index=False)
    summary["driver_curves"] = dose_rows
    summary["joint_conditions"] = joint_rows
    summary["timing"] = timing_rows
    summary["bootstrap_sensitivity"] = sensitivity_rows
    summary["load_context"] = context_rows
    summary["sample"]["load_aliases"] = LOAD_NAMES
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    checks = {
        "eligible_rows": len(panel),
        "recorded_counts": panel.groupby("flowgate").event_recorded.sum().to_dict(),
        "figures": 24,
        "statistical_figure_names": [
            f"{gate}_{name}.png"
            for gate in "abc"
            for name in [
                "timing",
                "driver_curves",
                "load_wind",
                "load_context",
                "solar_fuels",
                "joint",
                "price_distributions",
                "price_regimes",
            ]
        ],
        "unique_gate_hour_keys": True,
        "missing_absent_shadows_preserved": True,
        "fuel_shares_sum_to_100": True,
        "paired_prices_joined_by_utc": True,
        "b_reference_spread_algebra": True,
        "bootstrap_replicates": BOOTSTRAPS,
        "independent_sql_checks": independent_checks(summary),
    }
    (OUT / "statistics_checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks), flush=True)
    investigate(panel)
    local_supply_investigation(panel)


if __name__ == "__main__":
    main()
