from pathlib import Path
import pandas as pd,numpy as np,json
P=Path(__file__).resolve().parent;b=pd.read_pickle(P/'operating_panel.pkl');n=pd.read_csv(P/'tables/a_neighbors.csv',parse_dates=['target','control']);s={k:set(d.target) for k,d in n.groupby('specification')};common=set.intersection(*s.values());rng=np.random.default_rng(20261013);rows=[]
for spec,d in n.groupby('specification',sort=False):
 d=d[d.target.isin(common)];ns=d.groupby('target',sort=False).control.agg(list);tt=pd.DatetimeIndex(ns.index);cc=np.array([x for x in ns]);flat=pd.DatetimeIndex(cc.ravel());tw=(tt-pd.to_timedelta(tt.dayofweek,unit='D')).normalize();cw=(flat-pd.to_timedelta(flat.dayofweek,unit='D')).normalize();tu,ti=np.unique(tw,return_inverse=True);cu,ci=np.unique(cw,return_inverse=True);ci=ci.reshape(len(tt),3)
 cols=['A','A_total_da'];tv=b.loc[tt,cols].to_numpy();cv=b.loc[flat,cols].to_numpy().reshape(len(tt),3,2);boot=[]
 for _ in range(799):
  wt=rng.exponential(size=len(tu))[ti];wc=rng.exponential(size=len(cu))[ci];control=(cv*wc[:,:,None]).sum(axis=1)/wc.sum(axis=1)[:,None];boot.append(np.average(tv-control,axis=0,weights=wt))
 boot=np.array(boot)
 for j,col in enumerate(cols):rows.append({'specification':spec,'support':'common 286 hours','outcome':col,'method':'positive exponential calendar-week weights','point_difference':(tv-cv.mean(axis=1)).mean(axis=0)[j],'sensitivity_lo':np.quantile(boot[:,j],.025),'sensitivity_hi':np.quantile(boot[:,j],.975),'retained_target_fraction_each_draw':1})
pd.DataFrame(rows).to_csv(P/'tables/a_positive_week_sensitivity.csv',index=False);print(pd.DataFrame(rows).to_string(index=False))
