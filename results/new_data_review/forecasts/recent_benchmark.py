"""Delayed trailing occurrence benchmark; source publication remains unverified."""
from pathlib import Path
import json,sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;TAB=OUT/'tables';FIG=OUT/'figures'
c=sqlite3.connect('file:'+str(ROOT/'data/pjm.sqlite')+'?mode=ro',uri=True)
h=pd.read_sql_query('select timestamp,flowgate,event_recorded from hourly_analysis where dst_transition_date=0',c);c.close();h['timestamp']=pd.to_datetime(h.timestamp)
p=pd.read_csv(TAB/'predictions.csv.gz',parse_dates=['timestamp']);p=p[p.target.eq('event_recorded')].copy();p['cutoff_naive']=p.timestamp.dt.normalize()-pd.Timedelta(days=1)+pd.Timedelta(hours=9);p['history_end_exclusive']=p.cutoff_naive-pd.Timedelta(days=7);p['history_start_inclusive']=p.history_end_exclusive-pd.Timedelta(days=28)
rows=[];scores=[];reliability=[];audit=[]
for gate,g in h.groupby('flowgate'):
 values=g.set_index('timestamp').event_recorded.sort_index();values=values.reindex(pd.date_range(values.index.min(),values.index.max(),freq='h'));rolling_sum=values.rolling('28D',closed='left').sum();rolling_count=values.rolling('28D',closed='left').count();part=p[p.gate.eq(gate[-1])].copy();part['recent_prediction']=(rolling_sum/rolling_count).reindex(part.history_end_exclusive).to_numpy();part['history_n']=rolling_count.reindex(part.history_end_exclusive).to_numpy();assert part.recent_prediction.notna().all();assert part.history_end_exclusive.le(part.cutoff_naive-pd.Timedelta(days=7)).all()
 original=g.set_index('timestamp').event_recorded.sort_index();starts=original.index.searchsorted(part.history_start_inclusive,side='left');ends=original.index.searchsorted(part.history_end_exclusive,side='left');prefix=np.r_[0,original.to_numpy().cumsum()];expected_n=ends-starts;expected_prediction=(prefix[ends]-prefix[starts])/expected_n
 assert np.allclose(part.history_n,expected_n);assert np.allclose(part.recent_prediction,expected_prediction);audit.append({'check':gate+' delayed recent occurrence independently reconstructed by prefix sums','scalars':int(2*len(part)),'status':'pass'})
 rows.append(part)
 for y,t in part.groupby('year'):
  weeks=pd.Categorical(t.timestamp.dt.to_period('W-SUN').astype(str));n=len(weeks.categories);rng=np.random.default_rng(20261009);draws=rng.multinomial(n,np.full(n,1/n),size=599);counts=np.bincount(weeks.codes,minlength=n)
  for label in ['calendar','forecast','recent']:
   prediction=t[label+'_prediction'].to_numpy();e=t.actual.to_numpy()-prediction;d=e**2-(t.actual-t.recent_prediction).to_numpy()**2;total=np.bincount(weeks.codes,weights=d,minlength=n);boot=(draws@total)/(draws@counts)
   scores.append({'gate':gate[-1],'year':y,'model':label,'n':len(t),'actual_mean':t.actual.mean(),'predicted_mean':prediction.mean(),'brier':np.mean(e**2),'minus_recent_brier':d.mean(),'week_ci_low':np.quantile(boot,.025),'week_ci_high':np.quantile(boot,.975),'history_min_n':t.history_n.min(),'history_max_n':t.history_n.max()})
   r=pd.DataFrame({'prediction':prediction,'actual':t.actual.to_numpy()});r['bin']=pd.qcut(r.prediction.rank(method='first'),10,labels=False)
   for b,u in r.groupby('bin'):reliability.append({'year':y,'gate':gate[-1],'model':label,'bin':b,'n':len(u),'mean_prediction':u.prediction.mean(),'recorded_fraction':u.actual.mean()})
pd.concat(rows).to_csv(TAB/'recent_benchmark_predictions.csv.gz',index=False);s=pd.DataFrame(scores);s.to_csv(TAB/'recent_benchmark_scores.csv',index=False);pd.DataFrame(reliability).to_csv(TAB/'recent_reliability.csv',index=False)
plt.rcParams.update({'font.size':12,'axes.titlesize':14,'figure.dpi':150,'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False});fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained');colors={'calendar':'#aaaaaa','forecast':'#007c91','recent':'#a76a2b'}
for ax,y in zip(axs,[2025,2026]):
 x=np.arange(3)
 for j,label in enumerate(['calendar','forecast','recent']):
  r=s[s.year.eq(y)&s.model.eq(label)].set_index('gate').loc[['A','B','C']];ax.bar(x+(j-1)*.24,r.brier,.23,label=label.title(),color=colors[label])
 ax.set_xticks(x,['A','B','C']);ax.set_ylabel('Brier score (lower is better)');ax.set_title(str(y));ax.legend(frameon=False)
fig.suptitle('Recent binding history is a necessary benchmark for changing regimes',fontsize=16);fig.supxlabel('Recent: trailing 28 days ending seven days before cutoff; anonymous-source publication unverified',fontsize=10);fig.savefig(FIG/'recent_occurrence_benchmark.png');plt.close(fig)
r=json.loads((OUT/'result.json').read_text());r['recent_occurrence_benchmark']=json.loads(s.to_json(orient='records'));r['figures']=[str(f.relative_to(ROOT)) for f in sorted(FIG.glob('*.png'))];(OUT/'result.json').write_text(json.dumps(r,indent=2));print(s.round(5).to_string(index=False))

checkpath=OUT/'numeric_check.json'
checkresult=json.loads(checkpath.read_text());checkresult['recent_benchmark_checks']=audit;checkresult['recent_benchmark_scalar_checks']=sum(x['scalars'] for x in audit);checkpath.write_text(json.dumps(checkresult,indent=2))
