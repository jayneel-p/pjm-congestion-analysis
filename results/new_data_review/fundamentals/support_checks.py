from pathlib import Path
from collections import Counter
import pandas as pd,numpy as np,json
P=Path(__file__).resolve().parent
n=pd.read_csv(P/'tables/a_neighbors.csv',parse_dates=['target','control']);s={k:set(d.target) for k,d in n.groupby('specification')};common=set.intersection(*s.values());rng=np.random.default_rng(20261011);rows=[]
for spec,d in n.groupby('specification',sort=False):
 for support,dd in [('own',d),('common',d[d.target.isin(common)])]:
  ns=dd.groupby('target',sort=False).control.agg(list);tt=pd.DatetimeIndex(ns.index);cc=np.array([x for x in ns]);flat=pd.DatetimeIndex(cc.ravel())
  tw=(tt-pd.to_timedelta(tt.dayofweek,unit='D')).normalize();cw=(flat-pd.to_timedelta(flat.dayofweek,unit='D')).normalize()
  tu,ti=np.unique(tw,return_inverse=True);cu,ci=np.unique(cw,return_inverse=True);ci=ci.reshape(len(tt),3);ret=[]
  for _ in range(799):
   tcounts=rng.multinomial(len(tu),np.ones(len(tu))/len(tu))[ti];ccounts=rng.multinomial(len(cu),np.ones(len(cu))/len(cu))[ci];ret.append(tcounts[(ccounts.sum(axis=1)>0)].sum()/tcounts.sum())
  usage=Counter(dd.control)
  rows.append({'specification':spec,'support':support,'target_hours':len(tt),'target_dates':tt.normalize().nunique(),'target_weeks':len(tu),'control_dates':flat.normalize().nunique(),'control_weeks':len(cu),'unique_controls':len(usage),'max_control_reuse':max(usage.values()),'share_neighbors_top5pct_controls':sum(sorted(usage.values(),reverse=True)[:int(np.ceil(.05*len(usage)))])/len(dd),'bootstrap_min_retained_target_weight':min(ret),'bootstrap_p05_retained_target_weight':np.quantile(ret,.05),'bootstrap_median_retained_target_weight':np.median(ret)})
pd.DataFrame(rows).to_csv(P/'tables/a_support_dependence.csv',index=False)
months=pd.Series(pd.DatetimeIndex(sorted(common)).month).value_counts().sort_index().to_dict()
res={'a_common_target_months':months,'a_common_target_dates':len(set(x.date() for x in common)),'a_match_dependence':rows,'warning':'Bootstrap intervals condition on chosen neighbors and fixed support. Some sampled target weight is omitted when all selected controls have zero sampled weight.'}
(P/'support_checks.json').write_text(json.dumps(res,indent=2));print(pd.DataFrame(rows).to_string(index=False))
