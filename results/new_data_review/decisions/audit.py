"""Independent SQL/input/model-output/scenario audit; does not refit trees."""

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TAB = OUT / "tables"
ZONE = ZoneInfo("America/New_York")
checks = []
max_error = 0.0
scalars = 0


def ck(label, observed, expected, tol=1e-7):
    global max_error, scalars
    a = np.asarray(observed, dtype=float)
    b = np.asarray(expected, dtype=float)
    assert a.shape == b.shape, (label, a.shape, b.shape)
    assert np.allclose(a, b, atol=tol, rtol=1e-9, equal_nan=True), label
    finite = np.isfinite(a) & np.isfinite(b)
    err = float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.0
    max_error = max(max_error, err)
    scalars += a.size
    checks.append({"check": label, "scalar_checks": int(a.size), "max_absolute_error": err})


c = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
holidays = set(
    pd.read_csv(ROOT / "results/base_case/tables/block_holidays.csv")["date"].astype(str)
)
raw = defaultdict(dict)
for utc, node, da, rt in c.execute(
    "SELECT timestamp_utc,pnode_name,total_lmp_da,total_lmp_rt FROM pjm_multi_node_hourly_lmps WHERE pnode_name IN ('BGE_RESID_AGG','WESTERN HUB','DOMINION HUB','ACCA','COMED_RESID_AGG')"
):
    raw[utc][node] = (da, rt)
byday = defaultdict(list)
pairs = {
    "A": ("BGE_RESID_AGG", "WESTERN HUB", 0, True),
    "B-hub": ("DOMINION HUB", "WESTERN HUB", 0, True),
    "B-local": ("ACCA", "DOMINION HUB", 1, True),
    "C": ("COMED_RESID_AGG", "WESTERN HUB", 0, False),
}
for utc, nodes in sorted(raw.items()):
    dt = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    local = dt.astimezone(ZONE)
    date = local.date().isoformat()
    peak = local.weekday() < 5 and 7 <= local.hour <= 22 and date not in holidays
    for gate, (left, right, field, wantpeak) in pairs.items():
        if peak == wantpeak:
            byday[(gate, date)].append((dt, nodes[left][field] - nodes[right][field]))
prices = {k: float(np.mean([r[1] for r in v])) for k, v in byday.items()}
saved_prices = pd.read_csv(TAB / "all_daily_prices.csv")
ck(
    "All complete daily prices from raw UTC/entity rows",
    [r.actual for r in saved_prices.itertuples()],
    [prices[(r.gate, r.date)] for r in saved_prices.itertuples()],
)
ck(
    "Every daily block physical-hour count",
    saved_prices.hours,
    [len(byday[(r.gate, r.date)]) for r in saved_prices.itertuples()],
)
# Independently retain latest eligible evaluation for every UTC/entity using dictionaries.
selected = {}
dtcache = {}
cutoffs = {}
for delivery, evaluation, area, mw in c.execute(
    "SELECT forecast_hour_beginning_utc,evaluated_at_utc,forecast_area,forecast_load_mw FROM pjm_load_forecast_history"
):
    if delivery not in dtcache:
        dt = datetime.fromisoformat(delivery.replace("Z", "+00:00"))
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        dtcache[delivery] = dt
        cutoffs[delivery] = datetime.combine(
            dt.astimezone(ZONE).date() - timedelta(days=1), datetime.min.time(), tzinfo=ZONE
        ) + timedelta(hours=9)
    ev = datetime.fromisoformat(evaluation.replace("Z", "+00:00"))
    ev = ev.replace(tzinfo=timezone.utc) if ev.tzinfo is None else ev
    if ev <= cutoffs[delivery]:
        key = (dtcache[delivery], area)
        if key not in selected or ev > selected[key][0]:
            selected[key] = (ev, float(mw))
c.close()
features = pd.read_csv(TAB / "features.csv", parse_dates=["date"], float_precision="round_trip")
reconstructed = []
for row in features.itertuples():
    key = (row.gate, row.date.date().isoformat())
    hours = byday[key]
    array = np.array(
        [[selected[(dt, a)][1] for a in ["RTO", "MIDATL", "DOM", "COMED"]] for dt, value in hours]
    )
    record = {}
    for j, a in enumerate(["RTO", "MIDATL", "DOM", "COMED"]):
        record.update(
            {
                a + "_mean": array[:, j].mean(),
                a + "_max": array[:, j].max(),
                a + "_change": array[-1, j] - array[0, j],
            }
        )
    prior = [
        (datetime.fromisoformat(date), p)
        for (gate, date), p in prices.items()
        if gate == row.gate
        and datetime.fromisoformat(date) <= row.date.to_pydatetime() - timedelta(days=7)
        and int(len(byday[(gate, date)]) >= 23) == row.full_day
    ]
    prior.sort()
    short = [p for d, p in prior if d > row.date.to_pydatetime() - timedelta(days=35)]
    long = [p for d, p in prior if d > row.date.to_pydatetime() - timedelta(days=91)]
    assert row.history_max_date == prior[-1][0].date().isoformat()
    assert row.history_max_date <= (row.date - timedelta(days=7)).date().isoformat()
    record.update(
        recent28=np.mean(short),
        recent84=np.mean(long),
        sd84=np.std(long),
        latest_price=prior[-1][1],
        actual=prices[key],
        hours=len(hours),
        full_day=int(len(hours) >= 23),
        weekday=row.date.weekday(),
        month_sin=np.sin(2 * np.pi * (row.date.month - 1) / 12),
        month_cos=np.cos(2 * np.pi * (row.date.month - 1) / 12),
    )
    cutoff = datetime.combine(
        row.date.date() - timedelta(days=1), datetime.min.time(), tzinfo=ZONE
    ) + timedelta(hours=9)
    assert all(
        selected[(dt, a)][0] <= cutoff
        for dt, value in hours
        for a in ["RTO", "MIDATL", "DOM", "COMED"]
    )
    reconstructed.append(record)
cols = list(reconstructed[0])
ck(
    "Every saved price-history/calendar/load feature independently reconstructed",
    features[cols].to_numpy(),
    pd.DataFrame(reconstructed)[cols].to_numpy(),
)
# Full eligible support: no cherry-picking complete delivery blocks.
expected = set()
for (gate, date), hours in byday.items():
    d = datetime.fromisoformat(date)
    if any(
        (dt, a) not in selected for dt, value in hours for a in ["RTO", "MIDATL", "DOM", "COMED"]
    ):
        continue
    dayclass = int(len(hours) >= 23)
    hist = [
        (datetime.fromisoformat(t), p)
        for (g, t), p in prices.items()
        if g == gate
        and datetime.fromisoformat(t) <= d - timedelta(days=7)
        and int(len(byday[(g, t)]) >= 23) == dayclass
    ]
    if (
        sum(t > d - timedelta(days=35) for t, p in hist) >= 5
        and sum(t > d - timedelta(days=91) for t, p in hist) >= 10
    ):
        expected.add((gate, date))
assert expected == set(zip(features.gate, features.date.dt.strftime("%Y-%m-%d")))
rawp = pd.read_csv(TAB / "raw_predictions.csv", parse_dates=["date", "fold"])
folds = json.load(open(OUT / "folds.json"))
for fold in folds:
    g = features[features.gate.eq(fold["gate"])]
    start = pd.Timestamp(fold["month"])
    tr = g[g.date.le(start - pd.Timedelta(days=7)) & g.date.gt(start - pd.Timedelta(days=730))]
    te = rawp[
        rawp.gate.eq(fold["gate"]) & rawp.model.eq(fold["model"]) & rawp.fold.eq(start)
    ].sort_values("date")
    assert len(tr) == fold["train_days"] and str(tr.date.max().date()) == fold["train_max"]
    assert tr.date.max() <= start - pd.Timedelta(days=7)
    digest = hashlib.sha256(
        tr[["date", *fold["features"], "actual"]].to_csv(index=False, float_format="%.12g").encode()
    ).hexdigest()
    assert digest == fold["training_hash"], fold["file"]
    model = XGBRegressor()
    model.load_model(OUT / fold["file"])
    assert model.get_booster().num_boosted_rounds() == 120
    tx = g.set_index("date").loc[te.date, fold["features"]]
    ck("Saved tree predictions " + fold["file"], te.raw, model.predict(tx))
a = rawp[rawp.model.eq("recent")]
ck(
    "Delayed recent raw predictions",
    a.raw,
    [
        features.set_index(["gate", "date"]).loc[(r.gate, r.date), "recent28"]
        for r in a.itertuples()
    ],
)
p = pd.read_csv(TAB / "predictions.csv", parse_dates=["date"])
s = pd.read_csv(TAB / "scenarios.csv.gz", parse_dates=["date", "residual_date"])
groups = {(g, k): v for (g, k), v in rawp.groupby(["gate", "model"])}
scenario_groups = {key: v for key, v in s.groupby(["gate", "model", "date"])}
for row in p.itertuples():
    g = groups[(row.gate, row.model)]
    past = g[
        g.date.le(row.date - pd.Timedelta(days=7))
        & g.date.gt(row.date - pd.Timedelta(days=187))
        & g.full_day.eq(row.full_day)
    ]
    errors = past.actual.to_numpy() - past.raw.to_numpy()
    v = row.raw + errors
    actual = prices[(row.gate, row.date.date().isoformat())]
    saved = scenario_groups[(row.gate, row.model, row.date)]
    assert list(saved.residual_date) == list(past.date) and len(v) >= 20
    ck(
        "Historical residual scenarios " + str((row.gate, row.model, row.date.date())),
        saved.scenario,
        v,
    )
    lo, median, hi = np.quantile(v, [0.05, 0.5, 0.95])
    n = len(v)
    pairterm = np.mean(np.abs(v[:, None] - v[None, :])) / 2
    score = np.mean(np.abs(v - actual)) - pairterm
    ck(
        "Point/quantile/calibration/CRPS " + str((row.gate, row.model, row.date.date())),
        [
            row.actual,
            row.prediction,
            row.p05,
            row.median,
            row.p95,
            row.coverage90,
            row.below05,
            row.above95,
            row.prob_negative,
            row.pit,
            row.crps,
        ],
        [
            actual,
            np.mean(v),
            lo,
            median,
            hi,
            lo <= actual <= hi,
            actual < lo,
            actual > hi,
            np.mean(v < 0),
            np.mean(v <= actual),
            score,
        ],
    )
    assert row.calibration_max_date == past.date.max().date().isoformat()
metrics = pd.read_csv(TAB / "scores.csv")
for r in metrics.itertuples():
    t = p[p.gate.eq(r.gate) & p.model.eq(r.model) & p.year.eq(r.year)]
    e = t.prediction - t.actual
    ck(
        "Held-forward score " + str((r.gate, r.year, r.model)),
        [r.n, r.hours, r.rmse, r.mae, r.bias, r.coverage90, r.mean_width90, r.crps],
        [
            len(t),
            t.hours.sum(),
            np.sqrt(np.mean(e**2)),
            np.mean(abs(e)),
            np.mean(e),
            np.mean(t.coverage90),
            np.mean(t.p95 - t.p05),
            np.mean(t.crps),
        ],
    )
paired = pd.read_csv(TAB / "paired_scores.csv")
for r in paired.itertuples():
    t = p[p.gate.eq(r.gate) & p.year.eq(r.year)].pivot(
        index="date", columns="model", values=["actual", "prediction", "crps"]
    )
    assert t.notna().all().all()
    e = (t["prediction"][r.model] - t["actual"][r.model]) ** 2 - (
        t["prediction"]["recent"] - t["actual"]["recent"]
    ) ** 2
    cv = t["crps"][r.model] - t["crps"]["recent"]
    ck(
        "Paired loss means " + str((r.gate, r.year, r.model)),
        [r.mse_minus_recent, r.crps_minus_recent],
        [e.mean(), cv.mean()],
    )
    for block, values, low, high in [
        (7, e, r.week_low, r.week_high),
        (14, e, r.fortnight_low, r.fortnight_high),
        (7, cv, r.crps_week_low, r.crps_week_high),
    ]:
        labels = (
            t.index.to_period("W-SUN").astype(str)
            if block == 7
            else ((t.index - pd.Timestamp("2024-01-01")).days // 14)
        )
        unique = list(dict.fromkeys(labels))
        rng = np.random.default_rng(20261009 + block)
        draws = rng.multinomial(len(unique), np.full(len(unique), 1 / len(unique)), size=799)
        means = []
        for mult in draws:
            weights = np.array([mult[unique.index(x)] for x in labels])
            means.append(np.average(values, weights=weights))
        ck(
            "Joint block endpoints " + str((r.gate, r.year, r.model, block, str(values.name))),
            [low, high],
            np.quantile(means, [0.025, 0.975]),
            tol=1e-6,
        )
selection = json.load(open(OUT / "selection.json"))
chosen = pd.read_csv(TAB / "selected_2026.csv")
for r in selection:
    t = p[p.gate.eq(r["gate"]) & p.year.eq(2025) & p.date.le("2025-12-24")]
    scores = {k: np.mean((v.prediction - v.actual) ** 2) for k, v in t.groupby("model")}
    assert r["selected_model"] == min(scores, key=scores.get)
    ck(
        "Pre-2026 model choice " + r["gate"],
        list(r["candidate_mse"].values()),
        [scores[k] for k in r["candidate_mse"]],
    )
    assert chosen[chosen.gate.eq(r["gate"])].model.eq(r["selected_model"]).all()
quote_cases = 0
for e in json.load(open(OUT / "examples.json")):
    v = np.array(e["scenarios"])
    row = p[p.gate.eq(e["gate"]) & p.model.eq(e["model"]) & p.date.eq(e["date"])].iloc[0]
    ck("Replay forecast mean " + e["gate"], e["prediction"], v.mean())
    assert e["quote"] is None
    for q in [-100, -20, 0, 20, 100]:
        for cost in [0, 1, 5]:
            profit = e["direction"] * (v - q) - cost
            expected = e["direction"] * (np.mean(v) - q) - cost
            ck("Quote EV " + str((e["gate"], q, cost)), np.mean(profit), expected)
            # Exact 5% mass via overlap of each equal-weight atom with [0,.05].
            x = np.sort(profit)
            mass = np.maximum(
                0, np.minimum((np.arange(len(x)) + 1) / len(x), 0.05) - np.arange(len(x)) / len(x)
            )
            tail = np.dot(mass, x) / 0.05
            bound = 0.05 * len(x)
            n = int(bound)
            formula = (x[:n].sum() + (bound - n) * x[n]) / bound
            ck("Exact lower-tail profit " + str((e["gate"], q, cost)), tail, formula)
            quote_cases += 1
result = {
    "status": "passed",
    "scalar_checks": scalars,
    "maximum_absolute_error": max_error,
    "source_price_rows": sum(len(v) for v in byday.values()),
    "feature_rows": len(features),
    "models_checked": len(folds),
    "scenario_rows": len(s),
    "quote_cases": quote_cases,
    "all_feature_support_reconstructed": True,
    "training_dates_and_matrix_hashes_checked": True,
    "raw_forecasts_reproduced_from_saved_trees": True,
    "model_selection_uses_2025_only": True,
    "checks": checks,
    "scope": "Independent raw-SQL UTC/entity block prices, latest eligible archived load evaluations, every calendar/history/load input, complete support, dated training matrix hashes, saved tree predictions, all residual scenarios, scores, paired block endpoints, 2025-only selection and quote/tail arithmetic. Does not independently refit trees, authenticate publication or price revision availability, validate contracts or establish executable profit.",
}
(OUT / "numeric_check.json").write_text(json.dumps(result, indent=2) + "\n")
print({k: v for k, v in result.items() if k not in ["checks", "scope"]})
