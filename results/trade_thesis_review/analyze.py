"""Describe failures in saved trade evidence; see methods.md. No estimator fits."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
(OUT / "tables").mkdir(exist_ok=True)
(OUT / "figures").mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 12, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 150})


def save(fig, name):
    fig.savefig(OUT / "figures" / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


selected_path = ROOT / "results/new_data_review/decisions/tables/selected_2026.csv"
pred_path = ROOT / "results/new_data_review/decisions/tables/predictions.csv"
block_path = ROOT / "results/new_data_review/trading/tables/block_hours.csv"
c_path = ROOT / "results/base_case/tables/c_block_monthly.csv"
p = pd.read_csv(selected_path)
p = p[p.gate.isin(["A", "C"])].copy()
p["month"] = p.date.str[:7]
p["error"] = p.actual - p.prediction
m = p.groupby(["gate", "month"], as_index=False).agg(
    n=("date", "size"), prediction=("prediction", "mean"),
    actual=("actual", "mean"), mean_error=("error", "mean"),
    below05=("below05", "sum"), above95=("above95", "sum"),
    covered=("coverage90", "sum"))
m.to_csv(OUT / "tables/forecast_months.csv", index=False)
tail_rows = []
for g, x in p.groupby("gate"):
    tail_rows.append({"gate": g, "n": len(x), "below05": int(x.below05.sum()),
                      "above95": int(x.above95.sum()), "covered": int(x.coverage90.sum()),
                      "below_fraction": x.below05.mean(), "above_fraction": x.above95.mean(),
                      "coverage90": x.coverage90.mean()})
tails = pd.DataFrame(tail_rows)
tails.to_csv(OUT / "tables/forecast_tails.csv", index=False)

fig, axes = plt.subplots(1, 2, figsize=(13, 4.7), constrained_layout=True)
for ax, g in zip(axes, ["A", "C"]):
    x = m[m.gate.eq(g)]
    ax.plot(range(8), x.prediction, marker="o", label="Mean daily prediction", color="#bb6b20")
    ax.plot(range(8), x.actual, marker="o", label="Mean daily realization", color="#166781")
    ax.set_xticks(range(8), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"])
    ax.set_title({"A": "A: BGE residual − Western, DA peak",
                  "C": "C: ComEd residual − Western, DA off-peak"}[g], fontsize=13)
    ax.set_ylabel("Research spread ($/MWh)")
    ax.axhline(0, color="#777777", lw=.8)
    ax.legend(fontsize=10)
fig.suptitle("2026 demand-model scores hide changes through the year", fontsize=17)
save(fig, "forecast_months")

fig, ax = plt.subplots(figsize=(8.5, 4.6), constrained_layout=True)
z = np.arange(2)
ax.bar(z-.18, 100*tails.below_fraction, .36, label="Below forecast 5th percentile", color="#166781")
ax.bar(z+.18, 100*tails.above_fraction, .36, label="Above forecast 95th percentile", color="#bb6b20")
for j, r in enumerate(tails.itertuples()):
    for dx, value, count in [(-.18, r.below_fraction, r.below05), (.18, r.above_fraction, r.above95)]:
        ax.text(j+dx, 100*value+.4, f"{100*value:.1f}% ({count}/{r.n})", ha="center", fontsize=11)
ax.axhline(5, color="#555555", linestyle="--", label="Nominal 5% on each side")
ax.set_xticks(z, ["A: low misses hurt a long", "C: high misses hurt a short"])
ax.set_ylabel("Fraction of evaluated days (%)")
ax.set_ylim(0, 19)
ax.set_title("Forecast ranges miss too often on the proposed losing side")
ax.legend(fontsize=10, loc="upper right")
save(fig, "forecast_tails")

all_p = pd.read_csv(pred_path)
rmse_rows = []
for g in ["A", "C"]:
    for period in ["Jan–Aug", "Jul–Aug"]:
        x = all_p[(all_p.gate.eq(g)) & (all_p.year.eq(2026))]
        if period == "Jul–Aug":
            x = x[x.date.str[:7].isin(["2026-07", "2026-08"])]
        for model, y in x.groupby("model"):
            rmse_rows.append({"gate": g, "period": period, "model": model,
                              "n": len(y), "rmse": np.sqrt(np.mean((y.actual-y.prediction)**2))})
rmse = pd.DataFrame(rmse_rows)
rmse.to_csv(OUT / "tables/forecast_rmse.csv", index=False)
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), constrained_layout=True)
for ax, g in zip(axes, ["A", "C"]):
    for dx, model, label, color in [(-.2, "recent", "Recent prices", "#166781"),
                                  (.2, "demand", "Demand model", "#bb6b20")]:
        x = rmse[rmse.gate.eq(g) & rmse.model.eq(model)].set_index("period").loc[["Jan–Aug", "Jul–Aug"]]
        ax.bar(np.arange(2)+dx, x.rmse, .4, label=label, color=color)
        for i, r in enumerate(x.itertuples()):
            ax.text(i+dx, r.rmse+.6, f"{r.rmse:.2f}", ha="center", fontsize=11)
    ax.set_xticks(range(2), ["Jan–Aug 2026", "Jul–Aug 2026"])
    ax.set_ylim(0, 75)
    ax.set_ylabel("Daily-block RMSE ($/MWh)")
    ax.set_title(g)
    ax.legend(fontsize=10)
fig.suptitle("The overall demand-model advantage reverses in July–August", fontsize=16)
fig.supxlabel("Retrospective stability diagnostic; no model selection or new forecast")
save(fig, "forecast_rmse")

b = pd.read_csv(block_path)
b = b[b.gate.isin(["B", "B-local"]) & b.year.eq(2026) & b.month.le(8) & b.block.eq("peak")]
b_rows = []
for g, x in b.groupby("gate"):
    for support, y in [("Recorded B hours", x[x.event_recorded.eq(1)]), ("Every peak hour", x)]:
        assert np.allclose(y.rt_minus_da, y.total_rt-y.total_da)
        b_rows.append({"gate": g, "support": support, "n": len(y),
                       "mean": y.rt_minus_da.mean(), "median": y.rt_minus_da.median(),
                       "positive_fraction": y.rt_minus_da.gt(0).mean(),
                       "mean_da": y.total_da.mean(), "mean_rt": y.total_rt.mean()})
b_out = pd.DataFrame(b_rows)
b_out.to_csv(OUT / "tables/b_support.csv", index=False)
fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
for dx, support, color in [(-.2, "Recorded B hours", "#bb6b20"), (.2, "Every peak hour", "#166781")]:
    y = b_out[b_out.support.eq(support)].set_index("gate").loc[["B-local", "B"]]
    ax.bar(np.arange(2)+dx, y["mean"], .4, label=f"{support}: {int(y.iloc[0]['n']):,} hours", color=color)
    for i, r in enumerate(y.itertuples()):
        ax.text(i+dx, r.mean+(1 if r.mean>=0 else -1), f"{r.mean:+.2f}", ha="center", va="bottom" if r.mean>=0 else "top")
ax.set_xticks(range(2), ["ACCA − Dominion Hub", "Dominion Hub − Western Hub"])
ax.axhline(0, color="#555555", lw=.8)
ax.set_ylim(-42, 26)
ax.set_ylabel("Mean RT spread minus DA spread ($/MWh)")
ax.set_title("B: selecting recorded hours changes the price conclusion")
ax.legend(fontsize=11)
fig.supxlabel("January–August 2026 historical price differences; no executable trade or profit")
save(fig, "b_support")

c = pd.read_csv(c_path)
c = c[c.block.eq("offpeak") & c.month.between("2026-01", "2026-08")].copy()
c["hypothetical_entry"] = -20.
c["hypothetical_cost"] = 1.
c["hypothetical_short_outcome"] = -21.-c.hour_weighted_mean
c.to_csv(OUT / "tables/c_quote_stress.csv", index=False)
early = c.month.le("2026-02")
concentration = {"hours": int(c.physical_hours.sum()),
                 "negative_months": int(c.hour_weighted_mean.lt(0).sum()),
                 "losing_months_at_assumed_quote": int(c.hypothetical_short_outcome.lt(0).sum()),
                 "full_mean": float(np.average(c.hour_weighted_mean, weights=c.physical_hours)),
                 "jan_feb_hour_fraction": float(c.loc[early, "physical_hours"].sum()/c.physical_hours.sum()),
                 "jan_feb_negative_spread_sum_fraction": float((c.loc[early, "hour_weighted_mean"]*c.loc[early, "physical_hours"]).sum()/(c.hour_weighted_mean*c.physical_hours).sum()),
                 "mar_aug_mean": float(np.average(c.loc[~early,"hour_weighted_mean"], weights=c.loc[~early,"physical_hours"]))}
fig, ax = plt.subplots(figsize=(10.5, 4.8), constrained_layout=True)
ax.bar(range(8), c.hypothetical_short_outcome, color=np.where(c.hypothetical_short_outcome.ge(0), "#166781", "#bb6b20"))
for i, v in enumerate(c.hypothetical_short_outcome):
    ax.text(i, v+(1 if v>=0 else -1), f"{v:+.2f}", ha="center", va="bottom" if v>=0 else "top")
ax.set_xticks(range(8), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"])
ax.set_ylabel("Hypothetical short arithmetic ($/MWh)")
ax.set_title("C: ComEd is cheaper in all eight months; the assumed short loses in five")
ax.axhline(0, color="#555555", lw=.8)
ax.set_ylim(-19, 55)
fig.supxlabel("Invented entry −20 and cost 1 dollars/MWh; research averages, not official settlements")
save(fig, "c_quote_stress")

originals = ["results/base_case/report.html", "results/short_case/report.html",
             "results/short_case/presentation.html", "results/assessment_deck/assessment.tex"]
manifest = {"date": "2026-10-09", "scope": "Saved-evidence adversarial review; no new fitted models or trades",
            "input_hashes": {str(q.relative_to(ROOT)):digest(q) for q in [selected_path,pred_path,block_path,c_path]},
            "original_deliverable_hashes": {q:digest(ROOT/q) for q in originals},
            "c_concentration": concentration,
            "figures": sorted(q.name for q in (OUT/"figures").glob("*.png"))}
(OUT/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
print(json.dumps({"forecast_days": len(p), "figures": len(manifest["figures"]), "c_concentration": concentration}, indent=2))
