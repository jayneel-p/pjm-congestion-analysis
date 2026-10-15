"""Independent direct-SQL point audit; does not import the research analyzer."""
import csv
import datetime as dt
import hashlib
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
NODES = ("ACCA", "BASIN", "BELLWOOD", "DOM_RESID_AGG")
HUB = "DOMINION HUB"
checks = 0
failures = []
categories = defaultdict(int)


def check(category, label, actual, expected):
    global checks
    checks += 1
    categories[category] += 1
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        ok = math.isclose(float(actual), expected, rel_tol=1e-10, abs_tol=1e-8)
    else:
        ok = actual == expected
    if not ok:
        failures.append({"category": category, "label": label,
                         "actual": str(actual), "expected": str(expected)})


def read(name):
    with (OUT / "tables" / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def tail(values, upper=False):
    # Integrate exactly 5% of equally weighted empirical atoms.
    ordered = sorted(values, reverse=upper)
    remaining = len(ordered) / 20
    mass = remaining
    total = 0.0
    for value in ordered:
        weight = min(1.0, remaining)
        total += weight * value
        remaining -= weight
        if remaining <= 1e-12:
            break
    return total / mass


def points(values):
    return {"mean": statistics.mean(values), "median": statistics.median(values),
            "positive_days": sum(v > 0 for v in values),
            "positive_fraction": sum(v > 0 for v in values) / len(values),
            "min_day": min(values), "max_day": max(values),
            "worst5_mean": tail(values), "best5_mean": tail(values, True)}


holidays = set()
with (ROOT / "results/base_case/tables/block_holidays.csv").open() as fh:
    holidays.update(r["date"] for r in csv.DictReader(fh))
con = sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
raw = con.execute("""
 SELECT timestamp_utc, timestamp_ept, pnode_id, pnode_name,
        total_lmp_da, total_lmp_rt, congestion_price_da, congestion_price_rt,
        row_is_current_da, row_is_current_rt
 FROM pjm_multi_node_hourly_lmps
 WHERE pnode_name IN ('ACCA','BASIN','BELLWOOD','DOM_RESID_AGG','DOMINION HUB')
""").fetchall()
con.close()
source = defaultdict(dict)
node_ids = {}
eastern = ZoneInfo("America/New_York")
for row in raw:
    key, node = row["timestamp_utc"], row["pnode_name"]
    check("source", f"unique {key}/{node}", node not in source[key], True)
    source[key][node] = row
    node_ids[node] = row["pnode_id"]
    converted = dt.datetime.fromisoformat(key).replace(tzinfo=dt.timezone.utc).astimezone(eastern)
    check("source", f"EPT {key}/{node}", row["timestamp_ept"], converted.strftime("%Y-%m-%d %H:%M:%S"))

expected_hours = {}
for utc, rows in source.items():
    instant = dt.datetime.fromisoformat(utc).replace(tzinfo=dt.timezone.utc).astimezone(eastern)
    date = instant.strftime("%Y-%m-%d")
    if instant.weekday() >= 5 or date in holidays or not 10 <= instant.hour <= 15:
        continue
    check("support", f"five common nodes {utc}", set(rows), set(NODES) | {HUB})
    hub = rows[HUB]
    for node in NODES:
        local = rows[node]
        da = local["total_lmp_da"] - hub["total_lmp_da"]
        rt = local["total_lmp_rt"] - hub["total_lmp_rt"]
        expected_hours[utc, node] = {
            "utc": utc, "node": node, "date": date, "year": instant.year,
            "month": instant.month, "hour": instant.hour, "da": da, "rt": rt,
            "congestion_da": local["congestion_price_da"] - hub["congestion_price_da"],
            "congestion_rt": local["congestion_price_rt"] - hub["congestion_price_rt"],
            "delta": rt - da,
        }

saved_hours = read("hours.csv")
check("support", "hour key set", {(r["utc"], r["node"]) for r in saved_hours}, set(expected_hours))
check("support", "hour row count", len(saved_hours), len(expected_hours))
for row in saved_hours:
    key = row["utc"], row["node"]
    if key not in expected_hours:
        continue
    for field, expected in expected_hours[key].items():
        check("hours", f"{key}/{field}", row[field], expected)

groups = defaultdict(list)
for row in expected_hours.values():
    groups[row["node"], row["date"]].append(row)
expected_days = {}
for key, rows in groups.items():
    check("support", f"six hours {key}", sorted(r["hour"] for r in rows), list(range(10, 16)))
    expected_days[key] = {
        "node": key[0], "date": key[1], "year": rows[0]["year"], "month": rows[0]["month"],
        "hours": len(rows), **{f: statistics.mean(r[f] for r in rows) for f in ("delta", "da", "rt")},
    }
saved_days = read("days.csv")
check("support", "day keys", {(r["node"], r["date"]) for r in saved_days}, set(expected_days))
check("support", "day rows", len(saved_days), len(expected_days))
for row in saved_days:
    for field, expected in expected_days[row["node"], row["date"]].items():
        check("days", f"{row['node']}/{row['date']}/{field}", row[field], expected)

for row in read("annual.csv"):
    subset = [r for r in expected_days.values() if r["node"] == row["node"]
              and r["year"] == int(row["year"]) and r["month"] <= 8]
    expected = points([r["delta"] for r in subset])
    expected.update(days=len(subset), hours=sum(r["hours"] for r in subset))
    for field, value in expected.items():
        check("annual", f"{row['node']}/{row['year']}/{field}", row[field], value)
check("support", "annual rows", len(read("annual.csv")), 12)
for row in read("months.csv"):
    subset = [r for r in expected_days.values() if r["node"] == row["node"]
              and r["year"] == int(row["year"]) and r["month"] == int(row["month"])]
    values = [r["delta"] for r in subset]
    for field, value in {"days": len(subset), "mean": statistics.mean(values),
                         "median": statistics.median(values)}.items():
        check("months", f"{row['node']}/{row['year']}-{row['month']}/{field}", row[field], value)

agg2026 = sorted((r for r in expected_days.values() if r["node"] == "DOM_RESID_AGG"
                  and r["year"] == 2026 and r["month"] <= 8), key=lambda r: r["date"])
values = [r["delta"] for r in agg2026]
best = max(agg2026, key=lambda r: r["delta"])
worst = min(agg2026, key=lambda r: r["delta"])
expected_result = {
    "mean": statistics.mean(values), "median": statistics.median(values),
    "positive_days": sum(v > 0 for v in values), "days": len(values),
    "best5_contribution": tail(values, True) * .05,
    "remaining95_contribution": statistics.mean(values) - tail(values, True) * .05,
    "may_contribution": sum(r["delta"] for r in agg2026 if r["month"] == 5) / len(values),
    "without_may_mean": statistics.mean(r["delta"] for r in agg2026 if r["month"] != 5),
    "worst_day": worst["date"], "worst_day_mean": worst["delta"],
    "best_day": best["date"], "best_day_mean": best["delta"], "worst5_daily_mean": tail(values),
}
result = json.loads((OUT / "result.json").read_text())
for field, expected in expected_result.items():
    check("result", field, result[field], expected)
for node in NODES[:3]:
    y = [expected_days[node, r["date"]]["delta"] for r in agg2026]
    xm, ym = statistics.mean(values), statistics.mean(y)
    corr = sum((x - xm) * (v - ym) for x, v in zip(values, y)) / math.sqrt(
        sum((x - xm) ** 2 for x in values) * sum((v - ym) ** 2 for v in y))
    check("result", f"correlation {node}", result["correlations"][node], corr)

agg_hours = {key: row for key, row in expected_hours.items() if row["node"] == "DOM_RESID_AGG"}
bid_rows = read("utc_bid_hours.csv")
check("support", "UTC bid hours", {(r["utc"], r["node"]) for r in bid_rows}, set(agg_hours))
check("support", "UTC bid row count", len(bid_rows), len(agg_hours))
for row in bid_rows:
    expected = agg_hours[row["utc"], row["node"]]
    for field, value in expected.items():
        check("utc_hours", f"{row['utc']}/{field}", row[field], value)
    check("utc_hours", f"cap {row['utc']}", row["bid_cap"], 5.0)
    check("utc_hours", f"accept {row['utc']}", row["would_clear_under_price_only_rule"] == "True", expected["da"] <= 5.0)
bid_summary = read("utc_bid_sensitivity.csv")
check("support", "UTC cost/year keys", {(int(r["year"]), float(r["assumed_cost"])) for r in bid_summary},
      {(y, c) for y in (2024, 2025, 2026) for c in (0.0, 1.0, 3.0)})
check("support", "UTC sensitivity rows", len(bid_summary), 9)
for row in bid_summary:
    offered = [r for r in agg_hours.values() if r["year"] == int(row["year"]) and r["month"] <= 8]
    accepted = [r for r in offered if r["da"] <= 5.0]
    cost = float(row["assumed_cost"])
    net = [r["delta"] - cost for r in accepted]
    expected = {"bid_cap": 5.0, "offered_hours": len(offered), "accepted_hours": len(accepted),
                "accepted_fraction": len(accepted) / len(offered),
                "mean_per_accepted_mwh": statistics.mean(net),
                "mean_per_offered_mwh": sum(net) / len(offered),
                "positive_accepted_fraction": sum(v > 0 for v in net) / len(net),
                "worst_accepted_hour": min(net)}
    for field, value in expected.items():
        check("utc_costs", f"{row['year']}/cost{cost}/{field}", row[field], value)

aggregate_days = [r for r in expected_days.values() if r["node"] == "DOM_RESID_AGG"]
expected_screen = {}
for row in aggregate_days:
    if row["year"] not in (2025, 2026) or row["month"] > 8:
        continue
    delivery = dt.date.fromisoformat(row["date"])
    cutoff = delivery - dt.timedelta(days=7)
    history = [r for r in aggregate_days if cutoff - dt.timedelta(days=28)
               < dt.date.fromisoformat(r["date"]) <= cutoff]
    if len(history) < 10:
        continue
    history_mean = statistics.mean(r["delta"] for r in history)
    expected_screen[row["date"]] = {
        "date": row["date"], "year": row["year"], "delta": row["delta"],
        "history_n": len(history), "history_max_date": max(r["date"] for r in history),
        "history_mean": history_mean, "take_long": history_mean > 1.0,
    }
screen_rows = read("price_screen.csv")
check("support", "screen dates", {r["date"] for r in screen_rows}, set(expected_screen))
check("support", "screen rows", len(screen_rows), len(expected_screen))
for row in screen_rows:
    for field, value in expected_screen[row["date"]].items():
        actual = row[field] == "True" if isinstance(value, bool) else row[field]
        check("screen", f"{row['date']}/{field}", actual, value)
    check("screen", f"no future leakage {row['date']}",
          dt.date.fromisoformat(row["history_max_date"]) <= dt.date.fromisoformat(row["date"]) - dt.timedelta(days=7), True)
for row in read("price_screen_scores.csv"):
    eligible = [r for r in expected_screen.values() if r["year"] == int(row["year"])]
    selected = eligible if row["rule"] == "Always long" else [r for r in eligible if r["take_long"]]
    values = [r["delta"] for r in selected]
    for field, value in {"eligible_days": len(eligible), "selected_days": len(selected),
                         "gross_mean": statistics.mean(values), "mean_after_assumed_cost1": statistics.mean(values) - 1,
                         "median": statistics.median(values)}.items():
        check("screen_scores", f"{row['year']}/{row['rule']}/{field}", row[field], value)

eligibility = json.loads((OUT / "eligibility.json").read_text())
for name, publication in eligibility["publications"].items():
    for node, target in publication["targets"].items():
        check("provenance", f"{name}/{node}/canonical ID", target["queried_pnode_id"], node_ids[node])
    metadata = publication["source"]
    data = (OUT / metadata["snapshot"]).read_bytes()
    check("provenance", f"{name}/bytes", len(data), metadata["bytes"])
    check("provenance", f"{name}/sha256", hashlib.sha256(data).hexdigest(), metadata["sha256"])

report = {
    "status": "pass" if not failures else "fail", "checks": checks,
    "categories": dict(categories), "failures": failures,
    "source_rows": len(raw), "hour_rows": len(expected_hours), "day_rows": len(expected_days),
    "annual_rows": len(read("annual.csv")), "monthly_rows": len(read("months.csv")),
    "utc_bid_rows": len(bid_rows), "screen_rows": len(screen_rows),
    "scope": "Independent standard-library direct-SQL reconstruction, without importing analyze.py: UTC/entity pairing and EPT labels, common six-hour support, total/congestion spreads, daily/annual/monthly points, exact 5%-mass tails and correlations, preset +5 cap and invented 0/1/3 costs, delayed screen membership and no future dates. Eligibility snapshot hashes and canonical IDs checked.",
    "not_checked": [
        "Bootstrap endpoints are preserved but not recalculated.",
        "Endpoint-list interpretation is reproduced separately by eligibility.py; this audit checks its source hashes and canonical IDs only.",
        "No historical eligibility, permitted pair, actual bidding or clearing, five-minute invoice, observed costs, publication vintage, forecast calibration or future profitability is verified.",
        "No fresh holdout, causal attribution, current quote or Zotero save is established.",
    ],
}
(OUT / "numeric_check.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": checks, "failures": len(failures),
                  "hour_rows": len(expected_hours), "day_rows": len(expected_days), "screen_rows": len(screen_rows)}))
raise SystemExit(bool(failures))
