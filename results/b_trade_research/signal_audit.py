"""Independent standard-library SQL audit of frozen B signal reconstructions."""
import bisect
import csv
import datetime as dt
import json
import math
import random
import sqlite3
import statistics as stats
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ZONE = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
ANCHOR = dt.date(2024, 1, 1)
RULES = ("Cap only", "Past prices plus cap", "Two-day forecast share plus cap",
         "Morning forecast share plus cap")
CUTOFFS = {"latest": (1, 9), "older": (2, 9), "morning_early": (1, 6), "morning_late": (1, 10)}
checks, failures = 0, []
categories = defaultdict(int)


def check(category, label, actual, expected):
    global checks
    checks += 1
    categories[category] += 1
    if expected is None:
        ok = actual is None or actual == "" or (isinstance(actual, float) and math.isnan(actual))
    elif isinstance(expected, bool):
        ok = (actual == "True" if isinstance(actual, str) else actual) == expected
    elif isinstance(expected, (int, float)):
        ok = actual not in (None, "") and math.isclose(float(actual), expected, rel_tol=1e-10, abs_tol=1e-8)
    elif isinstance(expected, dt.datetime):
        parsed = dt.datetime.fromisoformat(actual.replace("Z", "+00:00")) if actual else None
        # Source fields explicitly end in _utc; the saved raw vintage string
        # omits its offset, while cutoff fields serialize the +00:00 offset.
        if parsed is not None and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        ok = parsed == expected
    else:
        ok = actual == expected
    if not ok:
        failures.append({"category": category, "label": label, "actual": str(actual), "expected": str(expected)})


def read(name):
    with (OUT / "tables" / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def compare(category, row, expected, label):
    for field, value in expected.items():
        if field in row:
            check(category, f"{label}/{field}", row[field], value)


def cutoff(date, lag, hour):
    return dt.datetime.combine(date - dt.timedelta(days=lag), dt.time(hour), ZONE).astimezone(UTC)


with (ROOT / "results/base_case/tables/block_holidays.csv").open() as fh:
    holidays = {r["date"] for r in csv.DictReader(fh)}
con = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
price_rows = con.execute("""SELECT timestamp_utc,timestamp_ept,pnode_name,total_lmp_da,
 total_lmp_rt,congestion_price_da,congestion_price_rt FROM pjm_multi_node_hourly_lmps
 WHERE pnode_name IN ('DOM_RESID_AGG','DOMINION HUB')""").fetchall()
forecast_rows = con.execute("""SELECT evaluated_at_utc,forecast_hour_beginning_utc,
 forecast_area,forecast_load_mw FROM pjm_load_forecast_history
 WHERE forecast_area IN ('DOM','RTO')""").fetchall()
con.close()
prices = defaultdict(dict)
for utc, ept, node, da, rt, cda, crt in price_rows:
    check("source", f"unique {utc}/{node}", node not in prices[utc], True)
    prices[utc][node] = (da, rt, cda, crt)
    instant = dt.datetime.fromisoformat(utc).replace(tzinfo=UTC).astimezone(ZONE)
    check("source", f"EPT {utc}/{node}", ept, instant.strftime("%Y-%m-%d %H:%M:%S"))
forecasts = defaultdict(list)
for evaluation, delivery, area, mw in forecast_rows:
    e = dt.datetime.fromisoformat(evaluation).replace(tzinfo=UTC)
    d = dt.datetime.fromisoformat(delivery).replace(tzinfo=UTC)
    forecasts[d, area].append((e, mw))
for key, values in forecasts.items():
    values.sort()
    check("source", f"unique forecast vintages {key}", len({e for e, _ in values}), len(values))

hours = {}
bydate = defaultdict(list)
for utc, pair in prices.items():
    instant = dt.datetime.fromisoformat(utc).replace(tzinfo=UTC)
    local = instant.astimezone(ZONE)
    date = local.date()
    if local.weekday() >= 5 or str(date) in holidays or not 10 <= local.hour <= 15:
        continue
    check("support", f"price pair {utc}", set(pair), {"DOM_RESID_AGG", "DOMINION HUB"})
    sink, source = pair["DOM_RESID_AGG"], pair["DOMINION HUB"]
    row = {"utc": utc, "date": str(date), "year": date.year, "month": date.month,
           "hour": local.hour, "node": "DOM_RESID_AGG", "da": sink[0] - source[0],
           "rt": sink[1] - source[1], "congestion_da": sink[2] - source[2],
           "congestion_rt": sink[3] - source[3]}
    row["delta"] = row["rt"] - row["da"]
    for label, (lag, hour) in CUTOFFS.items():
        limit = cutoff(date, lag, hour)
        row[f"{label}_cutoff_utc"] = limit
        for area in ("DOM", "RTO"):
            vintages = forecasts[instant, area]
            ix = bisect.bisect_right(vintages, (limit, float("inf")))
            chosen = vintages[ix - 1] if ix else (None, None)
            row[f"{label}_{area}_evaluation_utc"] = chosen[0]
            row[f"{label}_{area}_mw"] = chosen[1]
            if chosen[0] is not None:
                check("chronology", f"evaluation <= cutoff {utc}/{label}/{area}", chosen[0] <= limit, True)
                check("chronology", f"evaluation < delivery {utc}/{label}/{area}", chosen[0] < instant, True)
    for flag, labels in (("forecast_hour_complete", ("latest", "older")),
                         ("morning_hour_complete", ("morning_early", "morning_late"))):
        row[flag] = all(row[f"{label}_{area}_mw"] is not None for label in labels for area in ("DOM", "RTO"))
    hours[utc] = row
    bydate[str(date)].append(row)

daily = {}
for date, rows in sorted(bydate.items()):
    check("support", f"six-hour day {date}", sorted(r["hour"] for r in rows), list(range(10, 16)))
    daily[date] = {"date": date, "year": rows[0]["year"], "month": rows[0]["month"],
                   "candidate_hours": 6, "gross": stats.mean(r["delta"] for r in rows)}
for date, row in daily.items():
    end = dt.date.fromisoformat(date) - dt.timedelta(days=7)
    prior = [r for d, r in daily.items() if end - dt.timedelta(days=28) < dt.date.fromisoformat(d) <= end]
    row.update(history_n=len(prior), history_max_date=max((r["date"] for r in prior), default=None),
               history_mean=stats.mean(r["gross"] for r in prior) if prior else None)
    row["history_available"] = len(prior) >= 10
    row["history_signal"] = row["history_available"] and row["history_mean"] > 1
    rows = bydate[date]
    row["complete_forecast_hours"] = sum(r["forecast_hour_complete"] for r in rows)
    row["complete_morning_hours"] = sum(r["morning_hour_complete"] for r in rows)
    for label in CUTOFFS:
        for area in ("DOM", "RTO"):
            values = [r[f"{label}_{area}_mw"] for r in rows if r[f"{label}_{area}_mw"] is not None]
            name = label if label in ("latest", "older") else label.removeprefix("morning_")
            row[f"{name}_{area}_mean"] = stats.mean(values) if values else None
    for label in ("latest", "older"):
        dom, rto = row[f"{label}_DOM_mean"], row[f"{label}_RTO_mean"]
        row[f"{label}_share"] = dom / rto if dom is not None and rto else None
    a, b = row["latest_share"], row["older_share"]
    row["share_change"] = a - b if a is not None and b is not None else None
    row["forecast_available"] = row["complete_forecast_hours"] == 6
    row["forecast_signal"] = row["forecast_available"] and row["share_change"] > 0
    means = [row[f"{name}_{area}_mean"] for name in ("late", "early") for area in ("DOM", "RTO")]
    row["morning_share_change"] = means[0] / means[1] - means[2] / means[3] if all(v is not None for v in means) else None
    row["morning_available"] = row["complete_morning_hours"] == 6
    row["morning_signal"] = row["morning_available"] and row["morning_share_change"] > 0

expected_hours, expected_days = {}, {}
for rule in RULES:
    for utc, original in hours.items():
        if original["month"] > 8:
            continue
        day = daily[original["date"]]
        flags = (True, day["history_signal"], day["forecast_signal"], day["morning_signal"])
        offered = flags[RULES.index(rule)]
        filled = offered and original["da"] <= 5
        row = {**original, **{k: v for k, v in day.items() if k not in ("gross", "candidate_hours")},
               "rule": rule, "offered": offered, "filled": filled, "bid_cap": 5.0}
        row.update({f"net_cost{cost}": original["delta"] - cost if filled else 0.0 for cost in (0, 1, 3)})
        expected_hours[rule, utc] = row
    for date, day in daily.items():
        if day["month"] > 8:
            continue
        rows = [expected_hours[rule, h["utc"]] for h in bydate[date]]
        expected_days[rule, date] = {
            "rule": rule, "date": date, "year": day["year"], "month": day["month"],
            "candidate_hours": 6, "offered_hours": sum(r["offered"] for r in rows),
            "filled_hours": sum(r["filled"] for r in rows),
            **{f"net_cost{cost}": sum(r[f"net_cost{cost}"] for r in rows) for cost in (0, 1, 3)},
            **{f: day[f] for f in ("history_available", "forecast_available", "morning_available")},
            "subperiod": "Jan-Apr" if day["month"] <= 4 else "May-Aug",
        }

saved_hours = read("signal_hours.csv")
check("support", "all signal-hour keys", {(r["rule"], r["utc"]) for r in saved_hours}, set(expected_hours))
check("support", "signal-hour rows", len(saved_hours), len(expected_hours))
for row in saved_hours:
    compare("hours", row, expected_hours[row["rule"], row["utc"]], f"{row['rule']}/{row['utc']}")
saved_days = read("signal_days.csv")
check("support", "all signal-day keys", {(r["rule"], r["date"]) for r in saved_days}, set(expected_days))
check("support", "signal-day rows", len(saved_days), len(expected_days))
for row in saved_days:
    compare("days", row, expected_days[row["rule"], row["date"]], f"{row['rule']}/{row['date']}")


def score(ds, hs, cost):
    ds = sorted(ds, key=lambda r: r["date"])
    field = f"net_cost{cost}"
    total = sum(r[field] for r in ds)
    n = sum(r["candidate_hours"] for r in ds)
    filled = [r for r in hs if r["filled"]]
    net = [r["delta"] - cost for r in filled]
    cumulative, high, drawdown = 0.0, 0.0, 0.0
    for day in ds:
        cumulative += day[field]
        high = max(high, cumulative)
        drawdown = max(drawdown, high - cumulative)
    groups = defaultdict(list)
    for day in ds:
        groups[(dt.date.fromisoformat(day["date"]) - ANCHOR).days // 7].append(day)
    best_week = max(sorted(groups), key=lambda w: sum(r[field] for r in groups[w]))
    remaining = [r for r in ds if (dt.date.fromisoformat(r["date"]) - ANCHOR).days // 7 != best_week]
    months = defaultdict(list)
    for day in ds:
        months[day["month"]].append(day)
    best_month = max(sorted(months), key=lambda m: sum(r[field] for r in months[m]))
    remaining_month = [r for r in ds if r["month"] != best_month]
    best_day = max(ds, key=lambda r: r[field])
    remaining_day = [r for r in ds if r["date"] != best_day["date"]]
    return {
        "candidate_hours": n, "offered_hours": sum(r["offered_hours"] for r in ds),
        "filled_hours": len(filled), "net_sum_1mw": total,
        "mean_per_candidate_mwh": total / n, "mean_per_filled_mwh": stats.mean(net) if net else None,
        "positive_filled_fraction": sum(v > 0 for v in net) / len(net) if net else None,
        "worst_filled_hour": min(net) if net else None, "worst_day_1mw": min(r[field] for r in ds),
        "max_drawdown_1mw": drawdown,
        **{f"missing_{name}_days": sum(not r[f"{name}_available"] for r in ds)
           for name in ("history", "forecast", "morning")},
        "without_best_week_mean": sum(r[field] for r in remaining) / sum(r["candidate_hours"] for r in remaining),
        "best_month": best_month,
        "without_best_month_mean": sum(r[field] for r in remaining_month) / sum(r["candidate_hours"] for r in remaining_month) if remaining_month else None,
        "best_day": best_day["date"], "best_day_net_1mw": best_day[field],
        "without_best_day_mean": sum(r[field] for r in remaining_day) / sum(r["candidate_hours"] for r in remaining_day),
    }


annual_rows = read("signal_scores.csv")
sub_rows = read("signal_subperiods.csv")
for name, rows in (("scores", annual_rows), ("subperiods", sub_rows)):
    for row in rows:
        rule, year, cost = row["rule"], int(row["year"]), int(row["assumed_cost"])
        ds = [r for r in expected_days.values() if r["rule"] == rule and r["year"] == year]
        hs = [r for r in expected_hours.values() if r["rule"] == rule and r["year"] == year]
        if "subperiod" in row:
            ds = [r for r in ds if r["subperiod"] == row["subperiod"]]
            hs = [r for r in hs if ("Jan-Apr" if r["month"] <= 4 else "May-Aug") == row["subperiod"]]
        compare(name, row, score(ds, hs, cost), f"{rule}/{year}/{cost}/{row.get('subperiod', '')}")
for row in read("signal_months.csv"):
    ds = [r for r in expected_days.values() if r["rule"] == row["rule"]
          and r["year"] == int(row["year"]) and r["month"] == int(row["month"])]
    cost = int(row["assumed_cost"])
    n = sum(r["candidate_hours"] for r in ds)
    total = sum(r[f"net_cost{cost}"] for r in ds)
    compare("months", row, {"candidate_hours": n, "filled_hours": sum(r["filled_hours"] for r in ds),
                            "net_sum_1mw": total, "mean_per_candidate_mwh": total / n}, str(row))
for row in read("signal_paired.csv"):
    rule, year, cost = row["rule"], int(row["year"]), int(row["assumed_cost"])
    dates = sorted(d for ru, d in expected_days if ru == rule and int(d[:4]) == year)
    field = f"net_cost{cost}"
    difference = sum(expected_days[rule, d][field] - expected_days[RULES[0], d][field] for d in dates)
    check("paired", f"{rule}/{year}/{cost}", row["mean_difference_per_candidate_mwh"], difference / (6 * len(dates)))


def independent_interval(ds, cost, length, other_rule=None):
    # Different RNG implementation from the analyzer; this is a sensitivity,
    # not a claim to reproduce its particular Monte Carlo endpoint draws.
    groups = defaultdict(lambda: [0.0, 0])
    for day in ds:
        key = (dt.date.fromisoformat(day["date"]) - ANCHOR).days // length
        value = day[f"net_cost{cost}"]
        if other_rule:
            value -= expected_days[other_rule, day["date"]][f"net_cost{cost}"]
        groups[key][0] += value
        groups[key][1] += 6
    values = [groups[k] for k in sorted(groups)]
    rng = random.Random(20261009)
    means = []
    for _ in range(1999):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(v[0] for v in sample) / sum(v[1] for v in sample))
    means.sort()
    def quantile(p):
        pos = (len(means) - 1) * p
        a = int(pos)
        return means[a] + (pos - a) * (means[min(a + 1, len(means) - 1)] - means[a])
    return [quantile(.025), quantile(.975)]


independent_ranges = []
for rule in RULES:
    for year in (2025, 2026):
        ds = [r for r in expected_days.values() if r["rule"] == rule and r["year"] == year]
        row = {"rule": rule, "year": year, "assumed_cost": 1}
        for length in (7, 14, 28):
            row[f"block{length}"] = independent_interval(ds, 1, length)
        independent_ranges.append(row)

result = json.loads((OUT / "signal_result.json").read_text())
for promotion in result["promotion"]:
    rule = promotion["rule"]
    one = [r for r in annual_rows if r["rule"] == rule and int(r["year"]) in (2025, 2026) and int(r["assumed_cost"]) == 1]
    three = [r for r in annual_rows if r["rule"] == rule and int(r["year"]) in (2025, 2026) and int(r["assumed_cost"]) == 3]
    sub = [r for r in sub_rows if r["rule"] == rule and int(r["year"]) in (2025, 2026) and int(r["assumed_cost"]) == 3]
    expected = {
        "filled_at_least_50_each_year": all(float(r["filled_hours"]) >= 50 for r in one),
        "positive_cost3_both_years": all(float(r["mean_per_candidate_mwh"]) > 0 for r in three),
        "positive_cost3_each_subperiod": all(float(r["mean_per_candidate_mwh"]) > 0 for r in sub),
        "positive_cost1_all_cluster_lower_ends": all(float(r[f"block{k}_low"]) > 0 for r in one for k in (7, 14, 28)),
        "positive_cost1_without_best_week": all(float(r["without_best_week_mean"]) > 0 for r in one),
    }
    for field, value in expected.items():
        check("promotion", f"{rule}/{field}", promotion["checks"][field], value)
    passed = all(expected.values())
    check("promotion", f"{rule}/passed", promotion["passed"], passed)
    untestable = rule == RULES[2] and all(not daily[d]["forecast_available"] for d in daily if int(d[:4]) in (2025, 2026) and int(d[5:7]) <= 8)
    check("promotion", f"{rule}/status", promotion["status"], "untestable" if untestable else ("passes_research_screen" if passed else "fails_research_screen"))

support = []
for year in (2024, 2025, 2026):
    ds = [r for r in daily.values() if r["year"] == year and r["month"] <= 8]
    support.append({"year": year, "candidate_days": len(ds),
                    "two_day_complete": sum(r["forecast_available"] for r in ds),
                    "morning_complete": sum(r["morning_available"] for r in ds),
                    "morning_signal_days": sum(r["morning_signal"] for r in ds)})
report = {
    "status": "pass" if not failures else "fail", "checks": checks, "categories": dict(categories),
    "failures": failures, "signal_hour_rows": len(saved_hours), "signal_day_rows": len(saved_days),
    "forecast_support": support, "independent_cost1_cluster_ranges": independent_ranges,
    "scope": "Independent standard-library SQL price/forecast reconstruction; frozen cap, lag, hurdle and cutoffs; latest eligible raw vintages; common six hours; zero no-bid/unfilled P&L; candidate-hour denominators; annual/subperiod/monthly/paired points; losses, drawdown, omission diagnostics and promotion logic. A separate Python-random whole-calendar-block sensitivity uses 1,999 draws.",
    "limits": ["NumPy bootstrap endpoints are not exactly reproduced; promotion endpoint logic is checked against saved ranges, and independent RNG ranges are reported separately.",
               "Evaluation cutoff checks do not authenticate public availability. Seven-day price availability is assumed.",
               "No actual order, clearing, historical eligibility, invoice, costs, fresh holdout, causal mechanism or future profitability is verified."],
}
(OUT / "signal_audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": checks, "failures": len(failures), "forecast_support": support}))
raise SystemExit(bool(failures))
