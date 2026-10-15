"""Dated complete-block price forecasts; specification is in methods.md."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TAB = OUT / "tables"
FIG = OUT / "figures"
MOD = OUT / "models"
for p in [TAB, FIG, MOD]:
    p.mkdir(exist_ok=True)
MODELS = ["recent", "price_history", "demand"]
LABELS = {
    "recent": "Recent prices",
    "price_history": "Price history model",
    "demand": "Price + load forecasts",
}
PARAMS = dict(
    n_estimators=120,
    max_depth=2,
    learning_rate=0.05,
    min_child_weight=10,
    reg_lambda=20,
    subsample=1.0,
    colsample_bytree=1.0,
    objective="reg:squarederror",
    tree_method="hist",
    n_jobs=1,
    random_state=20261009,
)
CAL = ["month_sin", "month_cos", "weekday", "full_day", "hours"]
HIST = ["recent28", "recent84", "sd84", "latest_price"]
LOAD = [a + "_" + k for a in ["RTO", "MIDATL", "DOM", "COMED"] for k in ["mean", "max", "change"]]
PAIRS = {
    "A": ("A", "total_da", 1),
    "B-hub": ("B", "total_da", -1),
    "B-local": ("B-local", "total_rt", 1),
    "C": ("C", "total_da", -1),
}
plt.rcParams.update(
    {"font.size": 12, "axes.titlesize": 14, "axes.spines.top": False, "axes.spines.right": False}
)


def write(name, value):
    (OUT / name).write_text(
        json.dumps(
            value,
            indent=2,
            default=lambda v: v.item() if isinstance(v, np.generic) else str(v),
            allow_nan=False,
        )
        + "\n"
    )


def hash_frame(df):
    return hashlib.sha256(df.to_csv(index=False, float_format="%.12g").encode()).hexdigest()


def tail_mean(profit, mass=0.05):
    x = np.sort(np.asarray(profit))
    p = mass * len(x)
    n = int(np.floor(p))
    return (x[:n].sum() + (p - n) * x[n]) / p


def crps(x, y):
    x = np.sort(np.asarray(x))
    n = len(x)
    return np.abs(x - y).mean() - np.dot(2 * np.arange(1, n + 1) - n - 1, x) / n**2


def paired_interval(values, dates, days=7):
    groups = (
        pd.to_datetime(dates).dt.to_period("W-SUN").astype(str)
        if days == 7
        else ((pd.to_datetime(dates) - pd.Timestamp("2024-01-01")).dt.days // 14)
    )
    codes, u = pd.factorize(groups)
    s = np.bincount(codes, weights=values)
    n = np.bincount(codes)
    rng = np.random.default_rng(20261009 + days)
    m = rng.multinomial(len(u), np.full(len(u), 1 / len(u)), size=799)
    return np.quantile((m @ s) / (m @ n), [0.025, 0.975])


h = pd.read_csv(ROOT / "results/new_data_review/trading/tables/block_hours.csv")
h["utc"] = pd.to_datetime(h.timestamp_utc, utc=True)
f = pd.read_csv(ROOT / "results/new_data_review/forecasts/tables/selected_vintages.csv.gz")
f["utc"] = pd.to_datetime(f.forecast_hour_beginning_utc, utc=True)
f["evaluation"] = pd.to_datetime(f.evaluated_at_utc, utc=True)
w = f.pivot(index="utc", columns="forecast_area", values="forecast_load_mw").dropna()
metadata = f.groupby("utc").evaluation.max()
frames = []
all_prices = []
for gate, (src, target, direction) in PAIRS.items():
    p = h[h.gate.eq(src)].copy()
    p["date"] = pd.to_datetime(p.date)
    p = p.sort_values("utc")
    p["full_day"] = p.groupby("date").utc.transform("size").ge(23).astype(int)
    daily = (
        p.groupby("date")
        .agg(actual=(target, "mean"), hours=(target, "size"), full_day=("full_day", "first"))
        .reset_index()
    )
    daily["gate"] = gate
    all_prices.append(daily)
    z = p.merge(w, left_on="utc", right_index=True, how="left", validate="one_to_one")
    z["evaluation"] = z.utc.map(metadata)
    rows = []
    for date, g in z.groupby("date"):
        if not g[list(["RTO", "MIDATL", "DOM", "COMED"])].notna().all().all():
            continue
        r = {
            "gate": gate,
            "date": date,
            "actual": g[target].mean(),
            "hours": len(g),
            "full_day": int(g.full_day.iloc[0]),
            "evaluation_max_utc": str(g.evaluation.max()),
            "cutoff_utc": str(
                (date - pd.Timedelta(days=1) + pd.Timedelta(hours=9))
                .tz_localize("America/New_York")
                .tz_convert("UTC")
            ),
        }
        for a in ["RTO", "MIDATL", "DOM", "COMED"]:
            r.update(
                {
                    a + "_mean": g[a].mean(),
                    a + "_max": g[a].max(),
                    a + "_change": g[a].iloc[-1] - g[a].iloc[0],
                }
            )
        hist = daily[daily.date.le(date - pd.Timedelta(days=7)) & daily.full_day.eq(r["full_day"])]
        short = hist[hist.date.gt(date - pd.Timedelta(days=35))]
        long = hist[hist.date.gt(date - pd.Timedelta(days=91))]
        if len(short) < 5 or len(long) < 10:
            continue
        r.update(
            recent28=short.actual.mean(),
            recent84=long.actual.mean(),
            sd84=long.actual.std(ddof=0),
            latest_price=hist.actual.iloc[-1],
            history_max_date=str(hist.date.max().date()),
            weekday=date.dayofweek,
            month_sin=np.sin(2 * np.pi * (date.month - 1) / 12),
            month_cos=np.cos(2 * np.pi * (date.month - 1) / 12),
        )
        rows.append(r)
    frames.append(pd.DataFrame(rows))
features = pd.concat(frames, ignore_index=True).sort_values(["gate", "date"]).reset_index(drop=True)
features.to_csv(TAB / "features.csv", index=False)
pd.concat(all_prices).to_csv(TAB / "all_daily_prices.csv", index=False)
raw = []
folds = []
for gate, g in features.groupby("gate"):
    for month in pd.date_range("2024-07-01", "2026-08-01", freq="MS"):
        tr = g[g.date.le(month - pd.Timedelta(days=7)) & g.date.gt(month - pd.Timedelta(days=730))]
        te = g[g.date.ge(month) & g.date.lt(month + pd.offsets.MonthBegin(1))]
        if len(tr) < 60 or te.empty:
            continue
        weights = np.exp2(-(month - tr.date).dt.days.to_numpy() / 90)
        points = {"recent": te.recent28.to_numpy()}
        for kind, cols in [("price_history", CAL + HIST), ("demand", CAL + HIST + LOAD)]:
            model = XGBRegressor(**PARAMS)
            model.fit(tr[cols], tr.actual, sample_weight=weights)
            points[kind] = model.predict(te[cols])
            name = f"{gate}_{month:%Y%m}_{kind}.json"
            model.save_model(MOD / name)
            folds.append(
                {
                    "gate": gate,
                    "month": str(month.date()),
                    "model": kind,
                    "train_days": len(tr),
                    "train_min": str(tr.date.min().date()),
                    "train_max": str(tr.date.max().date()),
                    "training_hash": hash_frame(tr[["date", *cols, "actual"]]),
                    "file": "models/" + name,
                    "features": cols,
                }
            )
        for kind in MODELS:
            for (i, r), point in zip(te.iterrows(), points[kind]):
                raw.append(
                    {
                        "gate": gate,
                        "date": r.date,
                        "model": kind,
                        "raw": float(point),
                        "actual": r.actual,
                        "hours": r.hours,
                        "full_day": r.full_day,
                        "fold": str(month.date()),
                    }
                )
    print(gate, "monthly fits complete", flush=True)
raw = pd.DataFrame(raw).sort_values(["gate", "model", "date"])
raw.to_csv(TAB / "raw_predictions.csv", index=False)
write("folds.json", folds)
rows = []
scenarios = []
for (gate, kind), g in raw.groupby(["gate", "model"]):
    for _, r in g.iterrows():
        hist = g[
            g.date.le(r.date - pd.Timedelta(days=7))
            & g.date.gt(r.date - pd.Timedelta(days=187))
            & g.full_day.eq(r.full_day)
        ]
        if len(hist) < 20:
            continue
        residual = hist.actual.to_numpy() - hist.raw.to_numpy()
        s = r.raw + residual
        lo, med, hi = np.quantile(s, [0.05, 0.5, 0.95])
        y = r.actual
        rows.append(
            {
                **r.to_dict(),
                "prediction": s.mean(),
                "p05": lo,
                "median": med,
                "p95": hi,
                "scenario_n": len(s),
                "calibration_max_date": str(hist.date.max().date()),
                "bias_correction": residual.mean(),
                "coverage90": lo <= y <= hi,
                "below05": y < lo,
                "above95": y > hi,
                "prob_negative": np.mean(s < 0),
                "pit": np.mean(s <= y),
                "crps": crps(s, y),
            }
        )
        scenarios.extend(
            {
                "gate": gate,
                "model": kind,
                "date": r.date,
                "residual_date": old.date,
                "scenario": value,
                "raw_residual": err,
            }
            for (_, old), value, err in zip(hist.iterrows(), s, residual)
        )
p = pd.DataFrame(rows)
p["year"] = p.date.dt.year
p = p[p.year.ge(2025)]
# Identical rows across candidates, including cold-start calibration eligibility.
complete = p.groupby(["gate", "date"]).model.nunique().eq(3)
valid = complete[complete].index
p = p.set_index(["gate", "date"]).loc[valid].reset_index()
p.to_csv(TAB / "predictions.csv", index=False)
sc = pd.DataFrame(scenarios)
sc = sc.merge(
    p[["gate", "model", "date"]], on=["gate", "model", "date"], how="inner", validate="many_to_one"
)
sc.to_csv(TAB / "scenarios.csv.gz", index=False)
metrics = []
paired = []
selection = []
for (gate, year), g in p.groupby(["gate", "year"]):
    baseline = g[g.model.eq("recent")].set_index("date")
    for kind, t in g.groupby("model"):
        e = t.prediction - t.actual
        metrics.append(
            {
                "gate": gate,
                "year": year,
                "model": kind,
                "n": len(t),
                "hours": int(t.hours.sum()),
                "rmse": np.sqrt(np.mean(e**2)),
                "mae": np.abs(e).mean(),
                "bias": e.mean(),
                "coverage90": t.coverage90.mean(),
                "below05": t.below05.mean(),
                "above95": t.above95.mean(),
                "mean_width90": (t.p95 - t.p05).mean(),
                "crps": t.crps.mean(),
                "min_scenarios": int(t.scenario_n.min()),
                "median_scenarios": t.scenario_n.median(),
            }
        )
        b = baseline.loc[t.date]
        v = (t.prediction - t.actual).to_numpy() ** 2 - (b.prediction - b.actual).to_numpy() ** 2
        cv = t.crps.to_numpy() - b.crps.to_numpy()
        lo, hi = paired_interval(v, t.date)
        fl, fh = paired_interval(v, t.date, 14)
        cl, ch = paired_interval(cv, t.date)
        paired.append(
            {
                "gate": gate,
                "year": year,
                "model": kind,
                "mse_minus_recent": v.mean(),
                "week_low": lo,
                "week_high": hi,
                "fortnight_low": fl,
                "fortnight_high": fh,
                "crps_minus_recent": cv.mean(),
                "crps_week_low": cl,
                "crps_week_high": ch,
            }
        )
for gate, g in p[p.year.eq(2025) & p.date.le("2025-12-24")].groupby("gate"):
    loss = g.assign(loss=(g.prediction - g.actual) ** 2).groupby("model").loss.mean()
    winner = loss.idxmin()
    selection.append(
        {
            "gate": gate,
            "selected_model": winner,
            "selection_end": "2025-12-24",
            "selection_year": 2025,
            "selection_mse": loss[winner],
            "candidate_mse": loss.to_dict(),
        }
    )
mt = pd.DataFrame(metrics)
pa = pd.DataFrame(paired)
mt.to_csv(TAB / "scores.csv", index=False)
pa.to_csv(TAB / "paired_scores.csv", index=False)
write("selection.json", selection)
chosen = pd.concat(
    [p[p.gate.eq(r["gate"]) & p.year.eq(2026) & p.model.eq(r["selected_model"])] for r in selection]
)
chosen.to_csv(TAB / "selected_2026.csv", index=False)
examples = []
for gate in ["A", "C"]:
    row = chosen[chosen.gate.eq(gate)].sort_values("date").iloc[-1]
    s = sc[sc.gate.eq(gate) & sc.model.eq(row.model) & sc.date.eq(row.date)].scenario.to_numpy()
    direction = PAIRS[gate][2]
    examples.append(
        {
            "gate": gate,
            "date": str(row.date.date()),
            "model": row.model,
            "hours": int(row.hours),
            "prediction": row.prediction,
            "median": row["median"],
            "p05": row.p05,
            "p95": row.p95,
            "direction": direction,
            "scenarios": s.tolist(),
            "actual_reveal": row.actual,
            "publication_verified": False,
            "quote": None,
            "calibration_max_date": row.calibration_max_date,
        }
    )
write("examples.json", examples)
# Five readable evidence figures. All plotted points retain complete days/tails.
colors = {"recent": "#888888", "price_history": "#d48539", "demand": "#16718c"}
fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), layout="constrained")
for ax, year in zip(axs, [2025, 2026]):
    x = np.arange(4)
    for j, kind in enumerate(MODELS):
        a = mt[mt.year.eq(year) & mt.model.eq(kind)].set_index("gate").loc[list(PAIRS)]
        ax.bar(x + (j - 1) * 0.24, a.rmse, 0.23, label=LABELS[kind], color=colors[kind])
    ax.set_xticks(x, list(PAIRS))
    ax.set_title(str(year))
    ax.set_ylabel("Daily block price RMSE ($/MWh)")
    ax.legend(frameon=False, fontsize=9)
fig.suptitle("Forecast the full price block; compare with recent prices", fontsize=17)
fig.savefig(FIG / "forecast_skill.png", dpi=150)
plt.close(fig)
fig, axs = plt.subplots(2, 1, figsize=(13, 7), layout="constrained")
for ax, gate in zip(axs, ["A", "C"]):
    a = chosen[chosen.gate.eq(gate)].sort_values("date")
    b = p[p.gate.eq(gate) & p.year.eq(2026) & p.model.eq("recent")].set_index("date").loc[a.date]
    ax.plot(
        a.date, a.actual, color="#777777", lw=0.7, marker=".", ms=3, label="Realized full block"
    )
    ax.plot(a.date, a.prediction, color="#15738b", lw=1.6, label="Model selected using 2025")
    ax.plot(
        a.date,
        b.prediction.to_numpy(),
        color="#cc8c42",
        lw=1,
        ls="--",
        label="Recent-price forecast",
    )
    ax.set_title(f"{gate}: {LABELS[a.model.iloc[0]]}")
    ax.set_ylabel("Named spread ($/MWh)")
    ax.axhline(0, color="#cccccc", lw=0.7)
    ax.legend(frameon=False, fontsize=10)
fig.suptitle(
    "Earlier forecasts face the actual 2026 price path, including every extreme", fontsize=16
)
fig.savefig(FIG / "forecast_paths.png", dpi=150)
plt.close(fig)
fig, axs = plt.subplots(1, 2, figsize=(13, 4.7), layout="constrained")
for gate, color in zip(PAIRS, ["#156f88", "#b95d55", "#bd8b36", "#4c8a69"]):
    a = chosen[chosen.gate.eq(gate)]
    pit = np.sort(a.pit)
    axs[0].step(pit, np.arange(1, len(pit) + 1) / len(pit), where="post", label=gate, color=color)
axs[0].plot([0, 1], [0, 1], ls="--", color="#888888")
axs[0].set_xlabel("Forecast CDF evaluated at realized price")
axs[0].set_ylabel("Fraction of delivery days")
axs[0].set_title("A calibrated distribution follows the diagonal")
axs[0].legend(frameon=False)
a = chosen.groupby("gate").coverage90.mean().reindex(PAIRS)
axs[1].bar(a.index, 100 * a, color=["#156f88", "#b95d55", "#bd8b36", "#4c8a69"])
axs[1].axhline(90, color="#555555", ls="--", label="Nominal 90%")
axs[1].set_ylim(0, 100)
axs[1].set_ylabel("Days inside empirical 90% range (%)")
axs[1].set_title("Actual 2026 coverage of the selected model")
axs[1].legend(frameon=False)
for i, v in enumerate(a):
    axs[1].text(i, 100 * v + 2, f"{100 * v:.1f}%", ha="center", fontsize=12)
fig.suptitle("Check the price distribution before treating its probabilities as odds", fontsize=16)
fig.savefig(FIG / "forecast_calibration.png", dpi=150)
plt.close(fig)
fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), layout="constrained")
for ax, gate in zip(axs, ["A", "C"]):
    a = chosen[chosen.gate.eq(gate)]
    e = np.sort(a.actual - a.prediction)
    ax.step(e, np.arange(1, len(e) + 1) / len(e), where="post", lw=2, color="#15738b")
    ax.axvline(0, color="#888888")
    ax.set_xscale("symlog", linthresh=5)
    ax.set_xticks([-100, -10, 0, 10, 100], ["−100", "−10", "0", "10", "100"])
    ax.set_ylim(0, 1)
    ax.set_title(f"{gate}: {len(a)} complete delivery blocks")
    ax.set_xlabel("Realized spread minus predicted mean ($/MWh)")
    ax.set_ylabel("Fraction at or below error")
fig.suptitle("Forecast errors contain reversals and large tails", fontsize=17)
fig.supxlabel(
    "Signed-log axis retains every error; daily errors are not monthly settlement scenarios",
    fontsize=11,
)
fig.savefig(FIG / "forecast_error_distribution.png", dpi=150)
plt.close(fig)
fig, axs = plt.subplots(2, 2, figsize=(13, 7), layout="constrained")
for j, e in enumerate(examples):
    s = np.array(e["scenarios"])
    q = np.linspace(np.quantile(s, 0.01) - 10, np.quantile(s, 0.99) + 10, 161)
    pr = e["direction"] * (s[None, :] - q[:, None]) - 1
    ev = pr.mean(axis=1)
    loss = (pr < 0).mean(axis=1)
    axs[0, j].plot(q, ev, lw=2, color="#15738b")
    axs[0, j].axhline(0, color="#999999")
    axs[0, j].axvline(s.mean() - e["direction"], color="#a95454", ls="--")
    axs[0, j].set_ylabel("Scenario expected profit ($/MWh)")
    axs[0, j].set_title(f"{e['gate']}: historical forecast for {e['date']}")
    axs[1, j].plot(q, 100 * loss, color="#a95454", lw=2)
    axs[1, j].set_ylim(0, 100)
    axs[1, j].set_ylabel("Empirical scenario loss fraction (%)")
    axs[1, j].set_xlabel("Hypothetical entry spread ($/MWh)")
fig.suptitle("The entry quote changes the bet: $1/MWh assumed cost", fontsize=17)
fig.supxlabel(
    "Historical residual scenarios; no executable quote or certified future probabilities",
    fontsize=11,
)
fig.savefig(FIG / "forecast_quote_sensitivity.png", dpi=150)
plt.close(fig)
result = {
    "status": "passed",
    "specification": "methods.md",
    "models": PARAMS,
    "features": {"calendar": CAL, "delayed_prices": HIST, "archived_load": LOAD},
    "feature_rows": len(features),
    "raw_predictions": len(raw),
    "evaluated_predictions": len(p),
    "scenario_rows": len(sc),
    "scores": metrics,
    "paired_scores": paired,
    "selection": selection,
    "examples": examples,
    "publication_verified": False,
    "price_vintage_availability_verified": False,
    "live_quote_or_trade_profit_claimed": False,
    "monthly_forecast_claimed": False,
    "sources": ["A33", "P24", "A32", "T02", "ML01", "I01", "I04", "I05"],
    "figures": [str(x.relative_to(ROOT)) for x in sorted(FIG.glob("*.png"))],
}
write("result.json", result)
print(mt.to_string(index=False))
print(
    "2026 models selected only using 2025:", [(r["gate"], r["selected_model"]) for r in selection]
)
