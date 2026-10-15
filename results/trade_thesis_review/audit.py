"""Independent standard-library arithmetic audit; see methods.md."""

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
checks = 0


def rows(path):
    with (ROOT / path).open(newline="") as f:
        return list(csv.DictReader(f))


def number(value):
    if value in ("True", "False"):
        return float(value == "True")
    return float(value)


def eq(a, b):
    global checks
    assert math.isclose(number(a), number(b), rel_tol=1e-9, abs_tol=1e-8), (a, b)
    checks += 1


p = rows("results/new_data_review/decisions/tables/selected_2026.csv")
p = [r for r in p if r["gate"] in ("A", "C")]
groups = defaultdict(list)
for r in p:
    assert r["model"] == "demand"
    groups[r["gate"], r["date"][:7]].append(r)
    eq(r["below05"], float(r["actual"]) < float(r["p05"]))
    eq(r["above95"], float(r["actual"]) > float(r["p95"]))
    eq(r["coverage90"], float(r["p05"]) <= float(r["actual"]) <= float(r["p95"]))
for r in rows("results/trade_thesis_review/tables/forecast_months.csv"):
    x = groups[r["gate"], r["month"]]
    eq(r["n"], len(x))
    for key in ["prediction", "actual"]:
        eq(r[key], mean(float(z[key]) for z in x))
    eq(r["mean_error"], mean(float(z["actual"])-float(z["prediction"]) for z in x))
    for outkey, inkey in [("below05", "below05"), ("above95", "above95"), ("covered", "coverage90")]:
        eq(r[outkey], sum(number(z[inkey]) for z in x))
scores = rows("results/new_data_review/decisions/tables/scores.csv")
for r in rows("results/trade_thesis_review/tables/forecast_tails.csv"):
    x = [z for z in p if z["gate"] == r["gate"]]
    eq(r["n"], len(x))
    for outkey, inkey in [("below05", "below05"), ("above95", "above95"), ("covered", "coverage90")]:
        eq(r[outkey], sum(number(z[inkey]) for z in x))
    s = next(z for z in scores if z["gate"]==r["gate"] and z["model"]=="demand" and z["year"]=="2026")
    for key in ["coverage90", "below_fraction", "above_fraction"]:
        inkey = {"below_fraction":"below05", "above_fraction":"above95"}.get(key,key)
        eq(r[key], mean(number(z[inkey]) for z in x))
        eq(r[key], s[inkey])

pred = rows("results/new_data_review/decisions/tables/predictions.csv")
support = {}
for r in rows("results/trade_thesis_review/tables/forecast_rmse.csv"):
    x = [z for z in pred if z["gate"]==r["gate"] and z["model"]==r["model"] and z["year"]=="2026"
         and (r["period"]=="Jan–Aug" or z["date"][:7] in ("2026-07", "2026-08"))]
    eq(r["n"], len(x))
    eq(r["rmse"], math.sqrt(mean((float(z["actual"])-float(z["prediction"]))**2 for z in x)))
    k = (r["gate"],r["period"])
    dates = {z["date"] for z in x}
    if k in support:
        assert support[k] == dates
    support[k] = dates
    if r["period"]=="Jan–Aug":
        s=next(z for z in scores if z["gate"]==r["gate"] and z["model"]==r["model"] and z["year"]=="2026")
        eq(r["rmse"], s["rmse"])

b = rows("results/new_data_review/trading/tables/block_hours.csv")
for r in rows("results/trade_thesis_review/tables/b_support.csv"):
    x = [z for z in b if z["gate"]==r["gate"] and z["year"]=="2026" and int(z["month"])<=8 and z["block"]=="peak"
         and (r["support"]=="Every peak hour" or z["event_recorded"]=="1.0")]
    eq(r["n"], len(x))
    v = []
    for z in x:
        d=float(z["total_rt"])-float(z["total_da"])
        eq(z["rt_minus_da"], d)
        v.append(d)
    eq(r["mean"],mean(v)); eq(r["median"],median(v))
    eq(r["positive_fraction"],sum(z>0 for z in v)/len(v))
    eq(r["mean_da"],mean(float(z["total_da"]) for z in x))
    eq(r["mean_rt"],mean(float(z["total_rt"]) for z in x))

c = [r for r in rows("results/base_case/tables/c_block_monthly.csv") if r["block"]=="offpeak" and "2026-01"<=r["month"]<="2026-08"]
for r in rows("results/trade_thesis_review/tables/c_quote_stress.csv"):
    s = next(z for z in c if z["month"]==r["month"])
    eq(r["hour_weighted_mean"],s["hour_weighted_mean"])
    eq(r["physical_hours"],s["physical_hours"])
    eq(r["hypothetical_short_outcome"],float(r["hypothetical_entry"])-float(s["hour_weighted_mean"])-float(r["hypothetical_cost"]))
manifest = json.loads((OUT/"manifest.json").read_text())
stats = manifest["c_concentration"]
h = sum(int(r["physical_hours"]) for r in c)
total = sum(int(r["physical_hours"])*float(r["hour_weighted_mean"]) for r in c)
early = [r for r in c if r["month"]<="2026-02"]
late = [r for r in c if r["month"]>"2026-02"]
eq(stats["hours"],h)
eq(stats["negative_months"],sum(float(r["hour_weighted_mean"])<0 for r in c))
eq(stats["losing_months_at_assumed_quote"],sum(-21-float(r["hour_weighted_mean"])<0 for r in c))
eq(stats["full_mean"],total/h)
eq(stats["jan_feb_hour_fraction"],sum(int(r["physical_hours"]) for r in early)/h)
eq(stats["jan_feb_negative_spread_sum_fraction"],sum(int(r["physical_hours"])*float(r["hour_weighted_mean"]) for r in early)/total)
eq(stats["mar_aug_mean"],sum(int(r["physical_hours"])*float(r["hour_weighted_mean"]) for r in late)/sum(int(r["physical_hours"]) for r in late))
for name in ["input_hashes", "original_deliverable_hashes"]:
    for path, saved in manifest[name].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==saved,path
        checks += 1
for name in manifest["figures"]:
    assert (OUT/"figures"/name).stat().st_size>10000
    checks += 1
result = {"status":"pass", "scalar_checks":checks,
          "scope":"Reconstruction from saved CSVs; original deliverables unchanged; no tree refit or forecast calibration claim"}
(OUT/"numeric_check.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
