"""Independent SQL/point audit and joint-week watchlist uncertainty; see methods.md."""
from pathlib import Path
import json,sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;TAB=OUT/'tables';FIG=OUT/'figures';ZONE='America/New_York'
DST=['2024-03-10','2024-11-03','2025-03-09','2025-11-02','2026-03-08'];AREA={'RTO':'PJM RTO Total','MIDATL':'Mid-Atlantic Region','DOM':'DOM Zone','COMED':'COMED Zone'}
NODES={'A':('BGE_RESID_AGG','WESTERN HUB'),'B_hub':('DOMINION HUB','WESTERN HUB'),'B_local':('DOM_RESID_AGG','DOMINION HUB'),'C':('COMED_RESID_AGG','WESTERN HUB')};checks=[]
def check(label,x,y):
 x=np.asarray(x);y=np.asarray(y); assert np.allclose(x,y,rtol=1e-9,atol=1e-8,equal_nan=True),label
 checks.append({'check':label,'scalars':int(x.size),'status':'pass'})
c=sqlite3.connect('file:'+str(ROOT/'data/pjm.sqlite')+'?mode=ro',uri=True);c.execute('BEGIN')
fc=pd.read_sql_query('select evaluated_at_utc,forecast_hour_beginning_utc,forecast_area,forecast_load_mw from pjm_load_forecast_history',c)
fc['u']=pd.to_datetime(fc.forecast_hour_beginning_utc,utc=True);fc['e']=pd.to_datetime(fc.evaluated_at_utc,utc=True);fc['timestamp']=fc.u.dt.tz_convert(ZONE).dt.tz_localize(None)
fc['cutoff']=(fc.timestamp.dt.normalize()-pd.Timedelta(days=1)+pd.Timedelta(hours=9)).dt.tz_localize(ZONE).dt.tz_convert('UTC')
src=fc[(fc.timestamp.ge('2024-01-01'))&(fc.timestamp.lt('2026-09-01'))&(fc.e.le(fc.cutoff))].sort_values('e').groupby(['u','forecast_area'],sort=True).tail(1).set_index(['u','forecast_area']).sort_index()
saved=pd.read_csv(TAB/'selected_vintages.csv.gz');saved['u']=pd.to_datetime(saved.forecast_hour_beginning_utc,utc=True);saved=saved.set_index(['u','forecast_area']).sort_index()
assert src.index.equals(saved.index);check('Selected forecast MW matches latest eligible source key',saved.forecast_load_mw,src.forecast_load_mw)
assert (pd.to_datetime(saved.evaluated_at_utc,utc=True).to_numpy()==src.e.to_numpy()).all();checks.append({'check':'Every selected vintage is latest before prior-day 09:00; no later evaluation enters','scalars':len(saved),'status':'pass'})
actual=pd.read_sql_query('select opr_date,opr_hour,region_zone,load_value from load',c);actual['timestamp']=pd.to_datetime(actual.opr_date)+pd.to_timedelta(actual.opr_hour-1,unit='h');actual=actual.pivot(index='timestamp',columns='region_zone',values='load_value')
errors=pd.read_csv(TAB/'load_errors.csv.gz',parse_dates=['timestamp']);acc=pd.read_csv(TAB/'forecast_accuracy.csv')
for area,entity in AREA.items():
 g=errors[errors.forecast_area.eq(area)].set_index('timestamp');check(area+' actual load exact entity',g.actual,actual[entity].reindex(g.index));check(area+' forecast errors',g.error_actual_minus_forecast,g.actual-g.forecast_load_mw)
 for y,g in g.groupby(g.index.year):
  g=g.dropna(subset=['actual','forecast_load_mw','week_earlier_actual'])
  for label,col in [('archived_forecast','forecast_load_mw'),('week_earlier_actual','week_earlier_actual')]:
   e=g.actual-g[col];r=acc[acc.area.eq(area)&acc.year.eq(y)&acc.model.eq(label)].iloc[0]
   check(f'{area} {y} {label} errors summary',[r.n,r['mean'],r.mae,r.rmse,r.p05,r['median'],r.p95],[len(g),e.mean(),e.abs().mean(),np.sqrt((e**2).mean()),e.quantile(.05),e.quantile(.5),e.quantile(.95)])
pr=pd.read_sql_query('select timestamp_utc,pnode_name,total_lmp_da,congestion_price_da,total_lmp_rt,congestion_price_rt from pjm_multi_node_hourly_lmps',c);pr['timestamp']=pd.to_datetime(pr.timestamp_utc,utc=True).dt.tz_convert(ZONE).dt.tz_localize(None);pr=pr[~pr.timestamp.dt.strftime('%Y-%m-%d').isin(DST)]
pw=pr.pivot(index='timestamp',columns='pnode_name',values=['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt']);sp=pd.DataFrame(index=pw.index)
for key,(l,r) in NODES.items():
 for field in ['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt']: sp[key+'__'+field]=pw[field,l]-pw[field,r]
panel=pd.read_sql_query('select timestamp,flowgate,event_recorded,year,month,hour,weekend from hourly_analysis where dst_transition_date=0',c);c.close();panel['timestamp']=pd.to_datetime(panel.timestamp)
sf=src.reset_index();sf=sf[~sf.timestamp.dt.strftime('%Y-%m-%d').isin(DST)];forecasts=sf.pivot(index='timestamp',columns='forecast_area',values='forecast_load_mw');base=panel.merge(forecasts,on='timestamp',validate='many_to_one').merge(sp,on='timestamp',validate='many_to_one').dropna(subset=list(AREA));base['week']=base.timestamp.dt.to_period('W-SUN').astype(str)
pred=pd.read_csv(TAB/'predictions.csv.gz',parse_dates=['timestamp']);scores=pd.read_csv(TAB/'model_scores.csv');paired=pd.read_csv(TAB/'paired_score_differences.csv')
for (y,gate,target),p in pred.groupby(['year','gate','target']):
 if target=='event_recorded':v=base[base.flowgate.eq('Flowgate '+gate)].set_index('timestamp').event_recorded.reindex(p.timestamp)
 else:v=sp[target].reindex(p.timestamp)
 check(f'{gate} {y} {target} observed target matches SQL',p.actual,v)
 for label in ['calendar','forecast']:
  q=p[label+'_prediction'];e=p.actual-q;r=scores[scores.year.eq(y)&scores.gate.eq(gate)&scores.target.eq(target)&scores.model.eq(label)].iloc[0]
  check(f'{gate} {y} {target} {label} score recomputation',[r.actual_mean,r.predicted_mean,r.mae,r.rmse],[p.actual.mean(),q.mean(),e.abs().mean(),np.sqrt((e**2).mean())])
  if target=='event_recorded':check(f'{gate} {y} {label} Brier',r.brier,np.mean(e**2))
 d=(p.actual-p.forecast_prediction)**2-(p.actual-p.calendar_prediction)**2;r=paired[paired.year.eq(y)&paired.gate.eq(gate)&paired.target.eq(target)].iloc[0];check(f'{gate} {y} {target} paired MSE/Brier difference',r.forecast_minus_calendar,d.mean())
wh=pd.read_csv(TAB/'watch_hours.csv.gz',parse_dates=['timestamp']);watch=pd.read_csv(TAB/'watchlist.csv');audit=[];supported_frames=[];cdf=[]

def joint_boot(frame,targets,blocks):
 # Every draw gives the same block weight to targets and every reused control.
 cats=pd.Categorical(blocks);frame=frame.copy();frame['cluster']=cats.codes;cells=sorted(frame.calendar_cell.unique());nweek=len(cats.categories);nc=len(cells)
 rng=np.random.default_rng(20261009);draw=rng.multinomial(nweek,np.full(nweek,1/nweek),size=599)
 def matrix(iswatch,field=None):
  g=frame[frame.watch.eq(iswatch)];a=np.zeros((nweek,nc));values=np.ones(len(g)) if field is None else g[field].to_numpy()
  np.add.at(a,(g.cluster.to_numpy(),pd.Categorical(g.calendar_cell,categories=cells).codes),values);return a
 wc=draw@matrix(True);cc=draw@matrix(False);valid=cc>0;den=(wc*valid).sum(axis=1);out={}
 for target in targets:
  ws=draw@matrix(True,target);cs=draw@matrix(False,target);cm=np.divide(cs,cc,out=np.zeros_like(cs),where=valid)
  delta=((ws-wc*cm)*valid).sum(axis=1)/den
  out[target]=(np.quantile(delta,.025),np.quantile(delta,.975))
 return out,{'minimum_target_mass_retained':float((den/wc.sum(axis=1)).min()),'median_target_mass_retained':float(np.median(den/wc.sum(axis=1))),'clusters':nweek}
for y in [2025,2026]:
 for gate in ['A','C']:
  pressure='RTO' if gate=='A' else 'MIDATL';tr=base[base.timestamp.lt(f'{y-1}-12-25')&base.flowgate.eq('Flowgate '+gate)].copy();te=base[base.year.eq(y)&base.flowgate.eq('Flowgate '+gate)].copy();cells=['month','hour','weekend'];targets=['event_recorded']+[gate+'__'+f for f in ['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt']]
  centers=tr.groupby(cells)[pressure].median();tr=tr.join(centers.rename('center'),on=cells);te=te.join(centers.rename('center'),on=cells);threshold=(tr[pressure]-tr.center).quantile(.75);te['anomaly']=te[pressure]-te.center;te['watch']=te.anomaly.gt(threshold);te['calendar_cell']=te[cells].astype(str).agg('_'.join,axis=1)
  ctrl=te[~te.watch].groupby('calendar_cell');counts=ctrl.size();supported_cells=counts[counts.ge(3)].index;te=te[te.calendar_cell.isin(supported_cells)].copy();targets_saved=wh[wh.year.eq(y)&wh.gate.eq(gate)].set_index('timestamp');targets_new=te[te.watch].set_index('timestamp').sort_index();assert targets_saved.index.sort_values().equals(targets_new.index)
  check(f'{gate} {y} watch threshold',targets_saved.threshold_mw,threshold)
  means=te[~te.watch].groupby('calendar_cell')[targets].mean();t=targets_new.join(means,on='calendar_cell',rsuffix='__control').sort_index();s=targets_saved.sort_index()
  for target in targets:check(f'{gate} {y} {target} watch targets and full control means',s[[target,target+'__control']],t[[target,target+'__control']])
  wk,wa=joint_boot(te,targets,te.week);bi,ba=joint_boot(te,targets,((te.timestamp-pd.Timestamp('2024-01-01')).dt.days//14).astype(str))
  audit.append({'year':y,'gate':gate,'week':wa,'fortnight':ba,'joint_target_control_resampling':True})
  te['watch_gate']=gate;te['watch_test_year']=y;supported_frames.append(te[['timestamp','watch_gate','watch_test_year','calendar_cell','watch','week',*targets]])
  for target in targets:
   mask=watch.year.eq(y)&watch.gate.eq(gate)&watch.target.eq(target);watch.loc[mask,['week_ci_low','week_ci_high']]=wk[target];watch.loc[mask,['fortnight_ci_low','fortnight_ci_high']]=bi[target]
  # Weight each individual control by the number of targets sharing its calendar cell.
  nt=t.groupby('calendar_cell').size();non=te[~te.watch].copy();non['weight']=non.calendar_cell.map(nt).fillna(0)/non.calendar_cell.map(counts);non=non[non.weight.gt(0)]
  field=gate+'__total_lmp_da'
  for label,g,value,weight in [('Watch hour',t,field,np.ones(len(t))),('Calendar control hour',non,field,non.weight.to_numpy())]:
   order=np.argsort(g[value].to_numpy());x=g[value].to_numpy()[order];w=np.asarray(weight)[order]
   cdf.extend({'year':y,'gate':gate,'sample':label,'spread':xx,'weight':ww,'cdf':zz} for xx,ww,zz in zip(x,w,np.cumsum(w)/sum(w)))
watch.to_csv(TAB/'watchlist.csv',index=False);pd.concat(supported_frames).to_csv(TAB/'watch_support.csv.gz',index=False);pd.DataFrame(cdf).to_csv(TAB/'watch_cdf.csv.gz',index=False)
plt.rcParams.update({'font.size':12,'axes.titlesize':14,'figure.dpi':150,'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
colors={2025:'#287d8e',2026:'#c66b32'};fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
for ax,kind,title,scale in [(axs[0],'event_recorded','Binding-hour fraction',100),(axs[1],'total_lmp_da','Named DA total spread',1)]:
 g=watch[watch.target.eq(kind)] if kind=='event_recorded' else watch[watch.target.str.endswith(kind)];labels=[]
 for k,(_,r) in enumerate(g.iterrows()):
  ax.errorbar(r.difference*scale,k,xerr=np.array([[(r.difference-r.week_ci_low)*scale],[(r.week_ci_high-r.difference)*scale]]),fmt='o',color=colors[r.year],capsize=3);labels.append(f'{r.gate} {r.year}  n={r.supported_watch_hours:,}')
 ax.axvline(0,color='#777',lw=1);ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_title(title);ax.set_xlabel('Watch minus same-calendar nonwatch\n'+('Percentage points' if scale==100 else '$/MWh'))
fig.suptitle('High forecast demand marks price exposure more clearly than A occurrence',fontsize=16);fig.savefig(FIG/'forecast_watchlist.png');plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(13.3,5),layout='constrained');cd=pd.DataFrame(cdf);zoom=[]
for ax,gate in zip(axs,['A','C']):
 g=cd[cd.gate.eq(gate)&cd.year.eq(2026)];w=g[g['sample'].eq('Watch hour')];lo,hi=np.quantile(w.spread,[.01,.99])
 for label,color in [('Watch hour','#007c91'),('Calendar control hour','#999999')]:
  f=g[g['sample'].eq(label)];ax.step(f.spread,f.cdf,where='post',label=label,color=color,lw=1.8)
  zoom.append({'gate':gate,'sample':label,'display_low':lo,'display_high':hi,'weight_below':f.loc[f.spread.lt(lo),'weight'].sum()/f.weight.sum(),'weight_above':f.loc[f.spread.gt(hi),'weight'].sum()/f.weight.sum()})
 ax.axvline(0,color='#bbbbbb',lw=1);ax.set_xlim(lo,hi);ax.set_ylim(0,1);ax.set_xlabel(('BGE_RESID_AGG' if gate=='A' else 'COMED_RESID_AGG')+' minus WESTERN HUB\nDA total LMP ($/MWh)');ax.set_ylabel('Fraction at or below spread');ax.set_title(f'{gate}: 2026 watch and weighted individual controls');ax.legend(frameon=False)
fig.suptitle('Price distributions include reversals and large tails',fontsize=16);fig.supxlabel('View: watch 1st–99th percentile; all observations enter each CDF, without renormalizing',fontsize=11);fig.savefig(FIG/'watch_price_distributions.png');plt.close(fig)
pd.DataFrame(zoom).to_csv(TAB/'cdf_view_limits.csv',index=False)
result=json.loads((OUT/'result.json').read_text());result['watchlist']=json.loads(watch.to_json(orient='records'));result['watchlist_joint_resampling']=audit;result['independent_check']={'status':'pass','scalar_checks':sum(x['scalars'] for x in checks),'scope':'SQL-selected vintages, actual load entity/error summaries, model target values and re-scored predictions, watch thresholds/targets/all control means; does not refit estimators or independently audit bootstrap endpoints'};(OUT/'result.json').write_text(json.dumps(result,indent=2))
(OUT/'numeric_check.json').write_text(json.dumps({'status':'pass','scalar_checks':sum(x['scalars'] for x in checks),'checks':checks,'joint_resampling_support':audit,'limits':['Does not refit fitted models.','Joint resampling is implementation refinement, not independent endpoint verification.','Does not verify source publication or anonymous clock/market.']},indent=2));print('Independent forecast point audit passed:',sum(x['scalars'] for x in checks),'scalar comparisons')
