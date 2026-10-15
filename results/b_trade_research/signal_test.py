"""Frozen B rule comparisons; specification: signal_methods.md."""
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RULES = ["Cap only", "Past prices plus cap", "Two-day forecast share plus cap", "Morning forecast share plus cap"]
ANCHOR = pd.Timestamp("2024-01-01")
DRAWS = 1999

hours = pd.read_csv(OUT / "tables/hours.csv")
hours = hours[hours.node.eq("DOM_RESID_AGG")].copy()
hours["date_dt"] = pd.to_datetime(hours.date)
hours["delivery_utc"] = pd.to_datetime(hours.utc, utc=True)
assert not hours.duplicated("utc").any()
assert hours.groupby("date").size().eq(6).all()

# Record the exact two information cutoffs for each physical delivery hour.
for lag, label in [(1, "latest"), (2, "older")]:
    local = (hours.date_dt - pd.Timedelta(days=lag) + pd.Timedelta(hours=9))
    hours[f"{label}_cutoff_utc"] = local.dt.tz_localize("America/New_York").dt.tz_convert("UTC")
for hour, label in [(6, "morning_early"), (10, "morning_late")]:
    local = hours.date_dt - pd.Timedelta(days=1) + pd.Timedelta(hours=hour)
    hours[f"{label}_cutoff_utc"] = local.dt.tz_localize("America/New_York").dt.tz_convert("UTC")

with sqlite3.connect(f"file:{ROOT / 'data/pjm.sqlite'}?mode=ro", uri=True) as con:
    forecasts = pd.read_sql_query("""SELECT evaluated_at_utc,
        forecast_hour_beginning_utc, forecast_area, forecast_load_mw
        FROM pjm_load_forecast_history WHERE forecast_area IN ('DOM','RTO')""", con)
forecasts["delivery_utc"] = pd.to_datetime(forecasts.forecast_hour_beginning_utc, utc=True)
forecasts["evaluation_utc"] = pd.to_datetime(forecasts.evaluated_at_utc, utc=True)
labels = ["latest", "older", "morning_early", "morning_late"]
joined = forecasts.merge(hours[["delivery_utc"] + [f"{x}_cutoff_utc" for x in labels]],
                         on="delivery_utc", how="inner", validate="many_to_one")
for label in labels:
    chosen = joined[joined.evaluation_utc.le(joined[f"{label}_cutoff_utc"])].copy()
    chosen = chosen.sort_values("evaluation_utc").drop_duplicates(["delivery_utc", "forecast_area"], keep="last")
    for area in ["DOM", "RTO"]:
        a = chosen[chosen.forecast_area.eq(area)].set_index("delivery_utc")
        hours[f"{label}_{area}_mw"] = hours.delivery_utc.map(a.forecast_load_mw)
        hours[f"{label}_{area}_evaluation_utc"] = hours.delivery_utc.map(a.evaluated_at_utc.astype(object))

daily = hours.groupby(["date", "year", "month"], as_index=False).agg(
    gross=("delta", "mean"), candidate_hours=("utc", "size"))
daily["date_dt"] = pd.to_datetime(daily.date)
history_rows = []
for r in daily.itertuples():
    end = r.date_dt - pd.Timedelta(days=7)
    prior = daily[daily.date_dt.le(end) & daily.date_dt.gt(end - pd.Timedelta(days=28))]
    history_rows.append({"date": r.date, "history_n": len(prior),
                         "history_max_date": prior.date.max() if len(prior) else None,
                         "history_mean": prior.gross.mean()})
hist = pd.DataFrame(history_rows)
daily = daily.merge(hist, on="date", validate="one_to_one")
cols = [f"{label}_{area}_mw" for label in ["latest", "older"] for area in ["DOM", "RTO"]]
hours["forecast_hour_complete"] = hours[cols].notna().all(axis=1)
fday = hours.groupby("date", as_index=False).agg(
    complete_forecast_hours=("forecast_hour_complete", "sum"),
    latest_DOM_mean=("latest_DOM_mw", "mean"), latest_RTO_mean=("latest_RTO_mw", "mean"),
    older_DOM_mean=("older_DOM_mw", "mean"), older_RTO_mean=("older_RTO_mw", "mean"))
fday["latest_share"] = fday.latest_DOM_mean / fday.latest_RTO_mean
fday["older_share"] = fday.older_DOM_mean / fday.older_RTO_mean
fday["share_change"] = fday.latest_share - fday.older_share
daily = daily.merge(fday, on="date", validate="one_to_one")
morning_cols = [f"{label}_{area}_mw" for label in ["morning_early", "morning_late"] for area in ["DOM", "RTO"]]
hours["morning_hour_complete"] = hours[morning_cols].notna().all(axis=1)
morning = hours.groupby("date", as_index=False).agg(
    complete_morning_hours=("morning_hour_complete", "sum"),
    early_DOM_mean=("morning_early_DOM_mw", "mean"), early_RTO_mean=("morning_early_RTO_mw", "mean"),
    late_DOM_mean=("morning_late_DOM_mw", "mean"), late_RTO_mean=("morning_late_RTO_mw", "mean"))
morning["morning_share_change"] = morning.late_DOM_mean / morning.late_RTO_mean - morning.early_DOM_mean / morning.early_RTO_mean
daily = daily.merge(morning, on="date", validate="one_to_one")
daily["history_available"] = daily.history_n.ge(10)
daily["forecast_available"] = daily.complete_forecast_hours.eq(6)
daily["morning_available"] = daily.complete_morning_hours.eq(6)
daily["history_signal"] = daily.history_available & daily.history_mean.gt(1)
daily["forecast_signal"] = daily.forecast_available & daily.share_change.gt(0)
daily["morning_signal"] = daily.morning_available & daily.morning_share_change.gt(0)
hours = hours.merge(daily.drop(columns=["year", "month", "gross", "candidate_hours", "date_dt"]),
                    on="date", validate="many_to_one")
hours = hours[hours.month.le(8)].copy()

def cluster_interval(dates, values, counts, length):
    groups = ((pd.to_datetime(dates) - ANCHOR).dt.days // length).to_numpy()
    u, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=np.asarray(values), minlength=len(u))
    sizes = np.bincount(inv, weights=np.asarray(counts), minlength=len(u))
    rng = np.random.default_rng(20261009)
    draws = rng.integers(0, len(u), (DRAWS, len(u)))
    means = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    return np.quantile(means, [.025, .975])

long = []
for rule, flag in zip(RULES, [pd.Series(True, index=hours.index), hours.history_signal, hours.forecast_signal, hours.morning_signal]):
    z = hours.copy()
    z["rule"] = rule
    z["offered"] = flag.to_numpy()
    z["filled"] = z.offered & z.da.le(5)
    z["bid_cap"] = 5.
    for cost in [0, 1, 3]:
        z[f"net_cost{cost}"] = np.where(z.filled, z.delta - cost, 0.)
    long.append(z)
long = pd.concat(long, ignore_index=True)
long.drop(columns=["date_dt", "delivery_utc"]).to_csv(OUT / "tables/signal_hours.csv", index=False)

days = long.groupby(["rule", "date", "year", "month"], as_index=False).agg(
    candidate_hours=("utc", "size"), offered_hours=("offered", "sum"), filled_hours=("filled", "sum"),
    net_cost0=("net_cost0", "sum"), net_cost1=("net_cost1", "sum"), net_cost3=("net_cost3", "sum"),
    history_available=("history_available", "all"), forecast_available=("forecast_available", "all"), morning_available=("morning_available", "all"))
days["subperiod"] = np.where(days.month.le(4), "Jan-Apr", "May-Aug")
days.to_csv(OUT / "tables/signal_days.csv", index=False)

def scores(z, h, cost, intervals=False):
    col = f"net_cost{cost}"
    n = int(z.candidate_hours.sum())
    total = float(z[col].sum())
    filled = h[h.filled]
    net_filled = filled.delta - cost
    path = np.r_[0., z.sort_values("date")[col].cumsum().to_numpy()]
    ans = {"candidate_hours": n, "offered_hours": int(z.offered_hours.sum()),
           "filled_hours": int(z.filled_hours.sum()), "net_sum_1mw": total,
           "mean_per_candidate_mwh": total / n,
           "mean_per_filled_mwh": total / len(filled) if len(filled) else None,
           "positive_filled_fraction": float(net_filled.gt(0).mean()) if len(filled) else None,
           "worst_filled_hour": float(net_filled.min()) if len(filled) else None,
           "worst_day_1mw": float(z[col].min()),
           "max_drawdown_1mw": float((np.maximum.accumulate(path) - path).max()),
           "missing_history_days": int((~z.history_available).sum()),
           "missing_forecast_days": int((~z.forecast_available).sum()),
           "missing_morning_days": int((~z.morning_available).sum())}
    week = (pd.to_datetime(z.date) - ANCHOR).dt.days // 7
    weekly = z.groupby(week)[[col, "candidate_hours"]].sum()
    best_week = weekly[col].idxmax()
    remaining = z.loc[week.ne(best_week)]
    ans["without_best_week_mean"] = float(remaining[col].sum() / remaining.candidate_hours.sum())
    monthly = z.groupby("month")[[col, "candidate_hours"]].sum()
    best_month = monthly[col].idxmax()
    remaining_month = z[z.month.ne(best_month)]
    ans["best_month"] = int(best_month)
    ans["without_best_month_mean"] = float(remaining_month[col].sum() / remaining_month.candidate_hours.sum()) if len(remaining_month) else None
    best_day = z.loc[z[col].idxmax()]
    remaining_day = z[z.date.ne(best_day.date)]
    ans["best_day"] = best_day.date
    ans["best_day_net_1mw"] = float(best_day[col])
    ans["without_best_day_mean"] = float(remaining_day[col].sum() / remaining_day.candidate_hours.sum())
    if intervals:
        for length in [7, 14, 28]:
            lo, hi = cluster_interval(z.date, z[col], z.candidate_hours, length)
            ans[f"block{length}_low"] = float(lo)
            ans[f"block{length}_high"] = float(hi)
    return ans

annual, subs, months = [], [], []
for (rule, year), z in days.groupby(["rule", "year"], sort=False):
    h = long[long.rule.eq(rule) & long.year.eq(year)]
    for cost in [0, 1, 3]:
        annual.append({"rule": rule, "year": year, "assumed_cost": cost, **scores(z, h, cost, True)})
        for period, d in z.groupby("subperiod"):
            hh = h[h.month.le(4) if period == "Jan-Apr" else h.month.ge(5)]
            subs.append({"rule": rule, "year": year, "subperiod": period, "assumed_cost": cost, **scores(d, hh, cost)})
        for month, d in z.groupby("month"):
            months.append({"rule": rule, "year": year, "month": month, "assumed_cost": cost,
                           "candidate_hours": int(d.candidate_hours.sum()), "filled_hours": int(d.filled_hours.sum()),
                           "net_sum_1mw": float(d[f"net_cost{cost}"].sum()),
                           "mean_per_candidate_mwh": float(d[f"net_cost{cost}"].sum() / d.candidate_hours.sum())})
annual = pd.DataFrame(annual)
subs = pd.DataFrame(subs)
months = pd.DataFrame(months)
annual.to_csv(OUT / "tables/signal_scores.csv", index=False)
subs.to_csv(OUT / "tables/signal_subperiods.csv", index=False)
months.to_csv(OUT / "tables/signal_months.csv", index=False)

paired = []
for year in [2025, 2026]:
    base = days[days.rule.eq(RULES[0]) & days.year.eq(year)].set_index("date")
    for rule in RULES[1:]:
        z = days[days.rule.eq(rule) & days.year.eq(year)].set_index("date")
        assert z.index.equals(base.index)
        for cost in [1, 3]:
            diff = z[f"net_cost{cost}"] - base[f"net_cost{cost}"]
            row = {"rule": rule, "year": year, "assumed_cost": cost,
                   "mean_difference_per_candidate_mwh": float(diff.sum() / base.candidate_hours.sum())}
            for length in [7, 14, 28]:
                lo, hi = cluster_interval(pd.Series(z.index), diff.to_numpy(), z.candidate_hours.to_numpy(), length)
                row[f"block{length}_low"] = float(lo)
                row[f"block{length}_high"] = float(hi)
            paired.append(row)
pd.DataFrame(paired).to_csv(OUT / "tables/signal_paired.csv", index=False)

promotion = []
for rule in RULES:
    s = annual[annual.rule.eq(rule) & annual.year.isin([2025, 2026])]
    cost1 = s[s.assumed_cost.eq(1)]
    cost3 = s[s.assumed_cost.eq(3)]
    periods = subs[subs.rule.eq(rule) & subs.year.isin([2025, 2026]) & subs.assumed_cost.eq(3)]
    checks = {"filled_at_least_50_each_year": bool(cost1.filled_hours.ge(50).all()),
              "positive_cost3_both_years": bool(cost3.mean_per_candidate_mwh.gt(0).all()),
              "positive_cost3_each_subperiod": bool(periods.mean_per_candidate_mwh.gt(0).all()),
              "positive_cost1_all_cluster_lower_ends": bool(cost1[[f"block{k}_low" for k in [7, 14, 28]]].gt(0).all().all()),
              "positive_cost1_without_best_week": bool(cost1.without_best_week_mean.gt(0).all())}
    available = not (rule == RULES[2] and cost1.missing_forecast_days.sum() ==
                     days[days.rule.eq(rule) & days.year.isin([2025, 2026])].shape[0])
    promotion.append({"rule": rule, "status": "untestable" if not available else ("passes_research_screen" if all(checks.values()) else "fails_research_screen"),
                      "passed": all(checks.values()), "checks": checks})
result = {"date": "2026-10-09", "promotion": promotion,
          "physical_hypotheses": "Untested: local geographic load, relevant availability and solar commitment inputs absent.",
          "forecast_share_scope": "Regional demand predictor; not within-Dominion misallocation or a causal estimate.",
          "diagnostic_addition": "Monthly and leave-best-day/month views added after independent preliminary tail findings; no rule is selected or tuned using them.",
          "limits": "Previously explored years, assumed publication/price availability, invented costs, price-only full fills/current endpoint eligibility, no official invoice or untouched holdout."}
(OUT / "signal_result.json").write_text(json.dumps(result, indent=2) + "\n")

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
colors = ["#146287", "#d18432", "#888888", "#a83c48"]
plot_rules = [RULES[0], RULES[1], RULES[3]]
for j, rule in enumerate(plot_rules):
    z = annual[annual.rule.eq(rule) & annual.year.isin([2025, 2026]) & annual.assumed_cost.eq(1)]
    xx = np.arange(2) + (j - 1) * .24
    axes[0].bar(xx, z.mean_per_candidate_mwh, .22, color=colors[RULES.index(rule)], label=rule)
    axes[0].vlines(xx, z.block7_low, z.block7_high, color="#333", linewidth=1.2)
    for p, v in zip(xx, z.mean_per_candidate_mwh):
        axes[0].text(p, v + .07, f"{v:+.2f}", ha="center", fontsize=10)
axes[0].set_xticks([0, 1], ["2025", "2026"])
axes[0].set_ylabel("Net dollars per candidate MWh; no-position hours = zero")
axes[0].set_title("Assumed cost $1; lines resample calendar weeks")
axes[0].legend(fontsize=9)
for j, rule in enumerate(plot_rules):
    z = annual[annual.rule.eq(rule) & annual.year.isin([2025, 2026]) & annual.assumed_cost.eq(3)]
    axes[1].bar(np.arange(2) + (j - 1) * .24, z.mean_per_candidate_mwh, .22, color=colors[RULES.index(rule)], label=rule)
axes[1].set_xticks([0, 1], ["2025", "2026"])
axes[1].set_ylabel("Net dollars per candidate MWh")
axes[1].set_title("Assumed cost $3: test whether a small edge survives")
for ax in axes: ax.axhline(0, color="#555", linewidth=.8)
fig.suptitle("B: frozen bid rules must survive costs and related days", fontsize=16)
fig.supxlabel("January–August weekdays, 10:00–16:00 EPT; price-only full clearing, not actual profits")
fig.savefig(OUT / "figures/signal_rules.png", dpi=150, bbox_inches="tight")
plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.7), constrained_layout=True)
z = months[months.rule.eq(RULES[0]) & months.year.eq(2026) & months.assumed_cost.eq(1)]
axes[0].bar(z.month, z.mean_per_candidate_mwh, color=np.where(z.mean_per_candidate_mwh.ge(0), colors[0], colors[3]))
axes[0].set_xticks(range(1, 9), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"])
axes[0].set_ylabel("Net dollars per candidate MWh")
axes[0].set_title("Cap-only 2026: most months are weak or negative")
r = annual[annual.rule.eq(RULES[0]) & annual.year.eq(2026) & annual.assumed_cost.eq(1)].iloc[0]
v = [r.mean_per_candidate_mwh, r.without_best_day_mean, r.without_best_week_mean, r.without_best_month_mean]
axes[1].bar(range(4), v, color=[colors[0]] + [colors[3]] * 3)
axes[1].set_xticks(range(4), ["All days", "Without\nbest day", "Without\nbest week", "Without\nbest month"])
for j, x in enumerate(v): axes[1].text(j, x + (.03 if x >= 0 else -.03), f"{x:+.2f}", ha="center", va="bottom" if x >= 0 else "top")
axes[1].set_ylabel("Net dollars per remaining candidate MWh")
axes[1].set_title("Tail sensitivity; primary results retain every extreme")
axes[1].set_ylim(min(v) - .12, max(v) + .13)
for ax in axes: ax.axhline(0, color="#555", linewidth=.8)
fig.supxlabel("Assumed cost $1/MWh; 1 MW accounting unit; omissions are diagnostics, not alternate strategies")
fig.savefig(OUT / "figures/signal_fragility.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(json.dumps(result, indent=2))
print(annual[annual.year.isin([2025, 2026]) & annual.assumed_cost.isin([1, 3])][
    ["rule", "year", "assumed_cost", "filled_hours", "mean_per_candidate_mwh", "mean_per_filled_mwh", "block7_low", "block7_high", "without_best_week_mean"]].to_string(index=False))
