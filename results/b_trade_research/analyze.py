"""Reprice B trade alternatives on common UTC/node support; see methods.md."""
import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
for sub in ["tables", "figures"]:
    (OUT/sub).mkdir(exist_ok=True)
NODES = ["ACCA", "BASIN", "BELLWOOD", "DOM_RESID_AGG"]
plt.rcParams.update({"font.size": 12, "axes.spines.top":False, "axes.spines.right":False})

def tail(x, upper=False):
    x=np.sort(np.asarray(x,dtype=float))
    if upper:x=x[::-1]
    mass=.05*len(x); k=int(np.floor(mass))
    return float((x[:k].sum()+(mass-k)*x[k])/mass)

def interval(x, days=7):
    labels=((pd.to_datetime(x.date)-pd.Timestamp("2024-01-01")).dt.days//days).to_numpy()
    _,codes=np.unique(labels,return_inverse=True)
    sums=np.bincount(codes,weights=x.delta); counts=np.bincount(codes)
    rng=np.random.default_rng(20261009+days)
    w=rng.multinomial(len(counts),np.ones(len(counts))/len(counts),size=799)
    return np.quantile((w@sums)/(w@counts),[.025,.975])

def save(fig,name):
    fig.savefig(OUT/"figures"/f"{name}.png",dpi=150,bbox_inches="tight")
    plt.close(fig)

c=sqlite3.connect(f"file:{ROOT/'data/pjm.sqlite'}?mode=ro",uri=True)
p=pd.read_sql_query("""SELECT timestamp_utc,timestamp_ept,pnode_id,pnode_name,
total_lmp_da,total_lmp_rt,congestion_price_da,congestion_price_rt
FROM pjm_multi_node_hourly_lmps WHERE pnode_name IN
('ACCA','BASIN','BELLWOOD','DOM_RESID_AGG','DOMINION HUB')""",c)
c.close()
assert not p.duplicated(["timestamp_utc","pnode_name"]).any()
w=p.pivot(index="timestamp_utc",columns="pnode_name")
ept=pd.to_datetime(w.index,utc=True).tz_convert("America/New_York")
holidays=pd.read_csv(ROOT/"results/base_case/tables/block_holidays.csv")
hcol="date" if "date" in holidays else holidays.columns[0]
sel=(ept.dayofweek<5)&(ept.hour>=10)&(ept.hour<=15)&~ept.strftime("%Y-%m-%d").isin(holidays[hcol])
frames=[]
for node in NODES:
    x=pd.DataFrame({"utc":w.index,"date":ept.strftime("%Y-%m-%d"),"year":ept.year,
                    "month":ept.month,"hour":ept.hour,"node":node})
    for market in ["da","rt"]:
        x[market]=(w[f"total_lmp_{market}"][node]-w[f"total_lmp_{market}"]["DOMINION HUB"]).to_numpy()
        x[f"congestion_{market}"]=(w[f"congestion_price_{market}"][node]-w[f"congestion_price_{market}"]["DOMINION HUB"]).to_numpy()
    x["delta"]=x.rt-x.da
    frames.append(x.loc[sel].copy())
hours=pd.concat(frames,ignore_index=True)
assert not hours[["da","rt","delta"]].isna().any().any()
assert hours.groupby(["node","date"]).size().eq(6).all()
hours.to_csv(OUT/"tables/hours.csv",index=False)
daily=hours.groupby(["node","date","year","month"],as_index=False).agg(delta=("delta","mean"),da=("da","mean"),rt=("rt","mean"),hours=("hour","size"))
daily.to_csv(OUT/"tables/days.csv",index=False)
annual=[]
for (node,year),x in daily[daily.month.le(8)].groupby(["node","year"]):
    lo,hi=interval(x); f_lo,f_hi=interval(x,14)
    annual.append({"node":node,"year":year,"days":len(x),"hours":int(x.hours.sum()),
                   "mean":x.delta.mean(),"median":x.delta.median(),"positive_days":int(x.delta.gt(0).sum()),
                   "positive_fraction":x.delta.gt(0).mean(),"min_day":x.delta.min(),"max_day":x.delta.max(),
                   "worst5_mean":tail(x.delta),"best5_mean":tail(x.delta,True),
                   "week_low":lo,"week_high":hi,"fortnight_low":f_lo,"fortnight_high":f_hi})
annual=pd.DataFrame(annual)
annual.to_csv(OUT/"tables/annual.csv",index=False)
monthly=daily.groupby(["node","year","month"],as_index=False).agg(days=("date","size"),mean=("delta","mean"),median=("delta","median"))
monthly.to_csv(OUT/"tables/months.csv",index=False)

# Preset historical bid illustration, distinct from an always-clearing benchmark.
agg=hours[hours.node.eq("DOM_RESID_AGG")].copy()
agg["bid_cap"]=5.
agg["would_clear_under_price_only_rule"]=agg.da.le(5)
agg.to_csv(OUT/"tables/utc_bid_hours.csv",index=False)
bid=[]
for year,x in agg[agg.month.le(8)].groupby("year"):
    z=x[x.would_clear_under_price_only_rule]
    for cost in [0.,1.,3.]:
        v=z.delta-cost
        bid.append({"year":year,"bid_cap":5.,"assumed_cost":cost,"offered_hours":len(x),
                    "accepted_hours":len(z),"accepted_fraction":len(z)/len(x),
                    "mean_per_accepted_mwh":v.mean(),"mean_per_offered_mwh":v.sum()/len(x),
                    "positive_accepted_fraction":v.gt(0).mean(),"worst_accepted_hour":v.min()})
bid=pd.DataFrame(bid)
bid.to_csv(OUT/"tables/utc_bid_sensitivity.csv",index=False)

# A deliberately simple past-price screen; no realized binding chooses entries.
signals=[]
for r in daily[daily.node.eq("DOM_RESID_AGG") & daily.year.isin([2025,2026]) & daily.month.le(8)].itertuples():
    cutoff=pd.Timestamp(r.date)-pd.Timedelta(days=7)
    earlier=daily[(daily.node==r.node)&(pd.to_datetime(daily.date)<=cutoff)&(pd.to_datetime(daily.date)>cutoff-pd.Timedelta(days=28))]
    if len(earlier)<10:continue
    value=earlier.delta.mean()
    signals.append({"date":r.date,"year":r.year,"delta":r.delta,"history_n":len(earlier),
                    "history_max_date":earlier.date.max(),"history_mean":value,"take_long":value>1})
signals=pd.DataFrame(signals)
signals.to_csv(OUT/"tables/price_screen.csv",index=False)
screen=[]
for year,x in signals.groupby("year"):
    for rule,z in [("Always long",x),("Prior mean above 1",x[x.take_long])]:
        lo,hi=interval(z)
        screen.append({"year":year,"rule":rule,"eligible_days":len(x),"selected_days":len(z),
                       "gross_mean":z.delta.mean(),"mean_after_assumed_cost1":z.delta.mean()-1,
                       "week_low":lo,"week_high":hi,"median":z.delta.median()})
screen=pd.DataFrame(screen)
screen.to_csv(OUT/"tables/price_screen_scores.csv",index=False)

z=daily[daily.node.eq("DOM_RESID_AGG") & daily.year.eq(2026)&daily.month.le(8)]
may=z.month.eq(5)
stats={"mean":z.delta.mean(),"median":z.delta.median(),"positive_days":int(z.delta.gt(0).sum()),
       "days":len(z),"best5_contribution":.05*tail(z.delta,True),
       "remaining95_contribution":z.delta.mean()-.05*tail(z.delta,True),
       "may_contribution":z.loc[may,"delta"].sum()/len(z),
       "without_may_mean":z.loc[~may,"delta"].mean(),
       "worst_day":z.loc[z.delta.idxmin(),"date"],"worst_day_mean":z.delta.min(),
       "best_day":z.loc[z.delta.idxmax(),"date"],"best_day_mean":z.delta.max(),
       "worst5_daily_mean":tail(z.delta),"correlations":{}}
for node in NODES[:3]:
    y=daily[daily.node.eq(node)&daily.year.eq(2026)&daily.month.le(8)].set_index("date")
    stats["correlations"][node]=float(z.set_index("date").delta.corr(y.delta))
(OUT/"result.json").write_text(json.dumps(stats,indent=2)+"\n")

fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
for node,color in zip(NODES,["#146287","#d18432","#6b668f","#a83c48"]):
    x=annual[annual.node.eq(node)]
    axes[0].plot(x.year,x["mean"],marker="o",label=node,color=color)
axes[0].axhline(0,color="#777",lw=.8)
axes[0].set_xticks([2024,2025,2026]);axes[0].set_title("January–August: fixed 10:00–16:00 EPT")
axes[0].set_ylabel("Mean RT basis minus DA basis ($/MWh)");axes[0].legend(fontsize=10)
x=monthly[monthly.node.eq("DOM_RESID_AGG") & monthly.year.eq(2026)]
axes[1].bar(x.month,x["mean"],color=np.where(x["mean"]>=0,"#146287","#a83c48"))
axes[1].axhline(0,color="#777",lw=.8);axes[1].set_xticks(range(1,9),["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug"])
axes[1].set_title("Eligible aggregate: 2026 monthly means");axes[1].set_ylabel("RT basis minus DA basis ($/MWh)")
fig.suptitle("The eligible aggregate is a separate, unstable exposure",fontsize=17)
save(fig,"exposures")

fig,axes=plt.subplots(1,2,figsize=(12.5,4.8),constrained_layout=True)
for year,color in [(2024,"#777777"),(2025,"#d18432"),(2026,"#146287")]:
    x=np.sort(daily[(daily.node=="DOM_RESID_AGG")&(daily.year==year)&daily.month.le(8)].delta)
    axes[0].step(x,np.arange(1,len(x)+1)/len(x),where="post",label=str(year),color=color)
axes[0].set_xscale("symlog",linthresh=2);axes[0].set_xlabel("Daily six-hour mean RT-minus-DA basis ($/MWh)")
axes[0].set_ylabel("Fraction of days at or below value");axes[0].legend();axes[0].axvline(0,color="#777",lw=.8)
axes[0].set_title("Negative typical days and large tails")
vals=[stats["best5_contribution"],stats["remaining95_contribution"],stats["mean"]]
axes[1].bar(range(3),vals,color=["#146287","#a83c48","#6b668f"])
for i,v in enumerate(vals):axes[1].text(i,v+(0.4 if v>=0 else -.4),f"{v:+.2f}",ha="center",va="bottom" if v>=0 else "top")
axes[1].set_xticks(range(3),["Best 5%\ncontribution","Remaining 95%\ncontribution","Full mean"])
axes[1].set_ylabel("Contribution to 2026 mean ($/MWh)");axes[1].axhline(0,color="#777",lw=.8)
axes[1].set_ylim(-7,20);axes[1].set_title("A small favorable tail produces the mean")
save(fig,"tails")

fig,axes=plt.subplots(1,2,figsize=(12.5,4.7),constrained_layout=True)
for dx,cost,color in [(-.24,0.,"#146287"),(0,1.,"#d18432"),(.24,3.,"#a83c48")]:
    x=bid[bid.assumed_cost.eq(cost)]
    axes[0].bar(np.arange(3)+dx,x.mean_per_accepted_mwh,.24,label=f"Assumed cost {cost:g}",color=color)
axes[0].set_xticks(range(3),["2024","2025","2026"]);axes[0].axhline(0,color="#777",lw=.8)
axes[0].set_title("Illustrative UTC bid cap: +5 dollars/MWh");axes[0].set_ylabel("Mean per accepted MWh ($)");axes[0].legend(fontsize=10)
for dx,rule,color in [(-.18,"Always long","#146287"),(.18,"Prior mean above 1","#d18432")]:
    x=screen[screen.rule.eq(rule)]
    axes[1].bar(np.arange(2)+dx,x.mean_after_assumed_cost1,.36,label=rule,color=color)
    for i,r in enumerate(x.itertuples()):axes[1].text(i+dx,r.mean_after_assumed_cost1+.4,f"{r.selected_days} days",ha="center",fontsize=10)
axes[1].set_xticks(range(2),["2025","2026"]);axes[1].axhline(0,color="#777",lw=.8)
axes[1].set_ylabel("Mean after invented cost 1 ($/MWh)");axes[1].legend(fontsize=10)
axes[1].set_title("Delayed-price screen; no binding selects entries")
fig.supxlabel("Historical price arithmetic, assumed full clearing; not a settlement or execution backtest")
save(fig,"entry_diagnostics")
print(json.dumps({"annual":annual[annual.node.eq("DOM_RESID_AGG")].to_dict("records"),"utc_bid":bid.to_dict("records"),"screen":screen.to_dict("records")},indent=2))
