"""Independent point checks from saved neighbor keys and direct SQL, no analyzer import."""
import sqlite3,csv,json,math
from pathlib import Path
from collections import defaultdict
P=Path(__file__).resolve().parent
R=P.parents[2]
c=sqlite3.connect(f'file:{R}/data/pjm.sqlite?mode=ro',uri=True)
a={t:float(v) for t,v in c.execute("select timestamp,event_recorded from hourly_analysis where flowgate='Flowgate A' and dst_transition_date=0")}
price=defaultdict(dict)
for t,node,v in c.execute("select timestamp_ept,pnode_name,total_lmp_da from pjm_multi_node_hourly_lmps where pnode_name in ('BGE_RESID_AGG','WESTERN HUB')"):
 price[t][node]=v
sp={t:d['BGE_RESID_AGG']-d['WESTERN HUB'] for t,d in price.items()}
pairs=defaultdict(lambda:defaultdict(list))
for r in csv.DictReader(open(P/'tables/a_neighbors.csv')):pairs[r['specification']][r['target']].append(r['control'])
common=set.intersection(*[set(v) for v in pairs.values()])
expected=list(csv.DictReader(open(P/'tables/a_nested_matches.csv')))
checks=[]
for r in expected:
 if r['outcome'] not in ['A','A_total_da']:continue
 ps=pairs[r['specification']];ts=set(ps) if r['support']=='own' else common
 vals=a if r['outcome']=='A' else sp
 target=sum(vals[t] for t in ts)/len(ts)
 control=sum(sum(vals[x] for x in ps[t])/3 for t in ts)/len(ts)
 for k,v in [('target_hours',len(ts)),('target_mean',target),('control_mean',control),('difference',target-control)]:
  err=abs(v-float(r[k]));checks.append({'specification':r['specification'],'support':r['support'],'outcome':r['outcome'],'field':k,'reconstructed':v,'saved':float(r[k]),'absolute_error':err})
assert max(x['absolute_error'] for x in checks)<1e-10
out={'scope':'A neighbor/support/mean differences independently reconstructed from direct SQLite and saved keys. Not an independent bootstrap audit.','point_checks':len(checks),'maximum_absolute_error':max(x['absolute_error'] for x in checks),'common_target_hours':len(common),'checks':checks}
(P/'numeric_audit.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:v for k,v in out.items() if k!='checks'},indent=2))
