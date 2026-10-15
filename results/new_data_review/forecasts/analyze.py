"""Read-only analysis of archived load vintages; see methods.md."""
from pathlib import Path
import json, sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error, mean_squared_error

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
TAB=OUT/'tables'; FIG=OUT/'figures'; ZONE='America/New_York'
DST=['2024-03-10','2024-11-03','2025-03-09','2025-11-02','2026-03-08']
AREAS={'RTO':'PJM RTO Total','MIDATL':'Mid-Atlantic Region','DOM':'DOM Zone','COMED':'COMED Zone'}
NODES={'A':('BGE_RESID_AGG','WESTERN HUB'),'B_hub':('DOMINION HUB','WESTERN HUB'),'B_local':('DOM_RESID_AGG','DOMINION HUB'),'C':('COMED_RESID_AGG','WESTERN HUB')}
plt.rcParams.update({'font.size':12,'axes.titlesize':14,'axes.labelsize':12,'figure.dpi':150,'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
COLORS={'2024':'#577590','2025':'#287d8e','2026':'#c66b32','calendar':'#777777','forecast':'#007c91'}

def save_json(name,value):
 (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v: int(v) if isinstance(v,np.integer) else float(v) if isinstance(v,np.floating) else str(v),allow_nan=False))

def safe(v):
 if isinstance(v,dict): return {k:safe(x) for k,x in v.items()}
 if isinstance(v,list): return [safe(x) for x in v]
 if isinstance(v,float) and not np.isfinite(v): return None
 if isinstance(v,np.generic): return safe(v.item())
 return v

def interval(values,weeks,seed=20261009):
 values=np.asarray(values); groups=pd.Categorical(weeks); n=len(groups.categories)
 sums=np.bincount(groups.codes,weights=values,minlength=n); counts=np.bincount(groups.codes,minlength=n)
 rng=np.random.default_rng(seed); draws=rng.multinomial(n,np.full(n,1/n),size=599)
 means=(draws@sums)/(draws@counts)
 return float(np.quantile(means,.025)),float(np.quantile(means,.975))

def distributions(x):
 x=np.asarray(x,float); x=x[np.isfinite(x)]
 return {'n':len(x),'mean':np.mean(x),'median':np.median(x),'p05':np.quantile(x,.05),'p95':np.quantile(x,.95),'positive_fraction':np.mean(x>0)}

c=sqlite3.connect('file:'+str(ROOT/'data/pjm.sqlite')+'?mode=ro',uri=True); c.execute('BEGIN')
fc=pd.read_sql_query('select * from pjm_load_forecast_history',c)
keys=['evaluated_at_utc','forecast_hour_beginning_utc','forecast_area']
inventory={'load_rows':len(fc),'identical_key_duplicates':int(fc.duplicated(keys).sum()),'conflicting_keys':int(fc.groupby(keys).forecast_load_mw.nunique(dropna=False).gt(1).sum()),'renewables':[]}
assert not fc.duplicated(keys).any()
for utc,ept in [('evaluated_at_utc','evaluated_at_ept'),('forecast_hour_beginning_utc','forecast_hour_beginning_ept')]:
 fc[utc]=pd.to_datetime(fc[utc],utc=True,format='mixed')
 assert (fc[utc].dt.tz_convert(ZONE).dt.tz_localize(None)==pd.to_datetime(fc[ept],format='mixed')).all()
assert fc[keys+['forecast_load_mw']].notna().all().all()
for name,field in [('solar','solar_forecast_mwh'),('wind','wind_forecast_mwh')]:
 table='pjm_'+name+'_forecast_history'; frame=pd.read_sql_query('select evaluated_at_utc, datetime_beginning_utc, '+field+' from '+table,c)
 frame['evaluated_at_utc']=pd.to_datetime(frame.evaluated_at_utc,utc=True);frame['datetime_beginning_utc']=pd.to_datetime(frame.datetime_beginning_utc,utc=True)
 h=(frame.datetime_beginning_utc-frame.evaluated_at_utc).dt.total_seconds()/3600
 inventory['renewables'].append({'feed':name,'rows':len(frame),'unique_delivery_hours':frame.datetime_beginning_utc.nunique(),'evaluation_min_utc':str(frame.evaluated_at_utc.min()),'evaluation_max_utc':str(frame.evaluated_at_utc.max()),'delivery_min_utc':str(frame.datetime_beginning_utc.min()),'delivery_max_utc':str(frame.datetime_beginning_utc.max()),'duplicates':int(frame.duplicated(['evaluated_at_utc','datetime_beginning_utc']).sum()),'missing_measurements':int(frame[field].isna().sum()),'minimum_lead_hours':h.min(),'maximum_lead_hours':h.max(),'assessment_period_rows':int(frame.datetime_beginning_utc.lt(pd.Timestamp('2026-09-01 04:00Z')).sum()),'geography':'feed-wide total; no area/entity field','historical_publication_verified':False})
local=fc.forecast_hour_beginning_utc.dt.tz_convert(ZONE).dt.tz_localize(None)
fc['timestamp']=local
fc['cutoff_utc']=(local.dt.normalize()-pd.Timedelta(days=1)+pd.Timedelta(hours=9)).dt.tz_localize(ZONE).dt.tz_convert('UTC')
inside=local.between(pd.Timestamp('2024-01-01'),pd.Timestamp('2026-08-31 23:00'))
sel=(fc.loc[inside&fc.evaluated_at_utc.le(fc.cutoff_utc)].sort_values('evaluated_at_utc').drop_duplicates(['forecast_hour_beginning_utc','forecast_area'],keep='last').sort_values(['forecast_hour_beginning_utc','forecast_area']))
sel['evaluation_age_hours']=(sel.cutoff_utc-sel.evaluated_at_utc).dt.total_seconds()/3600
sel['lead_hours']=(sel.forecast_hour_beginning_utc-sel.evaluated_at_utc).dt.total_seconds()/3600
sel['publication_before_cutoff_verified']=False
assert sel.evaluated_at_utc.le(sel.cutoff_utc).all(); assert not sel.duplicated(['forecast_hour_beginning_utc','forecast_area']).any()
expected=pd.date_range('2024-01-01','2026-09-01',tz=ZONE,freq='h',inclusive='left').tz_convert('UTC')
coverage=[];missing=[]
for a in AREAS:
 f=fc.loc[inside&fc.forecast_area.eq(a)]; s=sel[sel.forecast_area.eq(a)]; absent=expected.difference(s.forecast_hour_beginning_utc)
 coverage.append({'area':a,'archive_rows_in_period':len(f),'delivery_hours_any_vintage':f.forecast_hour_beginning_utc.nunique(),'selected_hours':len(s),'expected_hours':len(expected),'missing_at_cutoff':len(absent),'lead_min_h':s.lead_hours.min(),'lead_median_h':s.lead_hours.median(),'lead_max_h':s.lead_hours.max(),'age_min_h':s.evaluation_age_hours.min(),'age_median_h':s.evaluation_age_hours.median(),'age_max_h':s.evaluation_age_hours.max(),'older_than_24h_at_cutoff':int(s.evaluation_age_hours.gt(24).sum())})
 missing.extend({'area':a,'delivery_utc':str(t),'delivery_ept':str(t.tz_convert(ZONE))} for t in absent)
pd.DataFrame(coverage).to_csv(TAB/'forecast_coverage.csv',index=False);pd.DataFrame(missing).to_csv(TAB/'missing_cutoff_hours.csv',index=False)
sel.to_csv(TAB/'selected_vintages.csv.gz',index=False)
inventory['load_coverage']=coverage;inventory['cutoff']='09:00 America/New_York on preceding local delivery date';inventory['publication_verified']=False
save_json('inventory.json',safe(inventory))
# Load comparison uses each entity separately.
actual=pd.read_sql_query("select * from load where region_zone in ('PJM RTO Total','Mid-Atlantic Region','DOM Zone','COMED Zone')",c)
actual['timestamp']=pd.to_datetime(actual.opr_date)+pd.to_timedelta(actual.opr_hour-1,unit='h')
assert not actual.duplicated(['timestamp','region_zone']).any()
actual=actual.pivot(index='timestamp',columns='region_zone',values='load_value')
accuracy=[];errs=[]
for a,entity in AREAS.items():
 s=sel.loc[sel.forecast_area.eq(a)].copy();s=s.loc[~s.timestamp.dt.strftime('%Y-%m-%d').isin(DST)]
 s=s.merge(actual[[entity]].rename(columns={entity:'actual'}),on='timestamp',how='left',validate='one_to_one')
 lag=actual[[entity]].rename(columns={entity:'week_earlier_actual'});lag=lag.loc[~lag.index.strftime('%Y-%m-%d').isin(DST)];lag.index=lag.index+pd.Timedelta(days=7)
 s=s.merge(lag,on='timestamp',how='left',validate='one_to_one');s['error_actual_minus_forecast']=s.actual-s.forecast_load_mw
 errs.append(s[['timestamp','forecast_area','actual','forecast_load_mw','week_earlier_actual','error_actual_minus_forecast']])
 for year,g in s.groupby(s.timestamp.dt.year):
  g=g.dropna(subset=['actual','forecast_load_mw','week_earlier_actual'])
  for model,field in [('archived_forecast','forecast_load_mw'),('week_earlier_actual','week_earlier_actual')]:
   e=g.actual-g[field]; d=distributions(e)
   accuracy.append({'area':a,'actual_entity':entity,'year':year,'model':model,**d,'mae':np.abs(e).mean(),'rmse':np.sqrt((e**2).mean()),'abs_error_over_5pct':np.mean(np.abs(e)/g.actual>.05)})
pd.DataFrame(accuracy).to_csv(TAB/'forecast_accuracy.csv',index=False)
pd.concat(errs).to_csv(TAB/'load_errors.csv.gz',index=False)
# Eligible gate rows and UTC-addressed paired prices.
panel=pd.read_sql_query('select timestamp,flowgate,event_recorded,year,month,hour,weekend from hourly_analysis where dst_transition_date=0',c)
panel['timestamp']=pd.to_datetime(panel.timestamp)
forecasts=sel.loc[~sel.timestamp.dt.strftime('%Y-%m-%d').isin(DST)].pivot(index='timestamp',columns='forecast_area',values='forecast_load_mw')
assert forecasts.index.is_unique
nodes=sorted(set(sum([list(x) for x in NODES.values()],[])))
q="select timestamp_utc,pnode_name,total_lmp_da,congestion_price_da,total_lmp_rt,congestion_price_rt from pjm_multi_node_hourly_lmps where pnode_name in ("+','.join('?' for _ in nodes)+")"
prices=pd.read_sql_query(q,c,params=nodes);c.close()
prices['utc']=pd.to_datetime(prices.timestamp_utc,utc=True,format='mixed');assert not prices.duplicated(['utc','pnode_name']).any()
prices['timestamp']=prices.utc.dt.tz_convert(ZONE).dt.tz_localize(None)
prices=prices[~prices.timestamp.dt.strftime('%Y-%m-%d').isin(DST)]
pw=prices.pivot(index='timestamp',columns='pnode_name',values=['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt'])
sp=pd.DataFrame(index=pw.index)
for key,(left,right) in NODES.items():
 for field in ['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt']:
  sp[key+'__'+field]=pw[(field,left)]-pw[(field,right)]
base=panel.merge(forecasts,on='timestamp',validate='many_to_one').merge(sp,on='timestamp',validate='many_to_one').dropna(subset=list(AREAS))
base['month_hour']=base.month.astype(str)+'_'+base.hour.astype(str);base['hour_weektype']=base.hour.astype(str)+'_'+base.weekend.astype(str)
base['week']=base.timestamp.dt.to_period('W-SUN').astype(str)
cal=['month','hour','weekend','month_hour','hour_weektype']

def pipeline(kind,demand):
 transforms=[('calendar',OneHotEncoder(handle_unknown='ignore',sparse_output=False),cal)]
 if demand: transforms.append(('demand',Pipeline([('spline',SplineTransformer(n_knots=5,degree=3,include_bias=False,extrapolation='linear')),('scale',StandardScaler())]),list(AREAS)))
 model=LogisticRegression(C=1,max_iter=2000,tol=1e-7) if kind=='occurrence' else Ridge(alpha=100)
 return Pipeline([('features',ColumnTransformer(transforms)),('model',model)])

scores=[];predictions=[];reliability=[];watch=[];watch_hours=[];pairs=[]
for year in [2025,2026]:
 train=base[base.timestamp.lt(pd.Timestamp(f'{year-1}-12-25'))];test=base[base.year.eq(year)]
 for gate in ['A','B','C']:
  tr=train[train.flowgate.eq('Flowgate '+gate)].copy();te=test[test.flowgate.eq('Flowgate '+gate)].copy()
  # Identical complete support for all four outcomes, then evaluate all hours.
  pricekeys=[gate] if gate!='B' else ['B_hub','B_local']
  targets=['event_recorded']+[key+'__'+field for key in pricekeys for field in ['total_lmp_da','congestion_price_da','total_lmp_rt','congestion_price_rt']]
  tr=tr.dropna(subset=targets);te=te.dropna(subset=targets)
  for target in targets:
   kind='occurrence' if target=='event_recorded' else 'price';store={}
   for label,demand in [('calendar',False),('forecast',True)]:
    p=pipeline(kind,demand);p.fit(tr,tr[target]); pred=p.predict_proba(te)[:,1] if kind=='occurrence' else p.predict(te)
    store[label]=pred
    e=te[target].to_numpy()-pred
    row={'year':year,'gate':gate,'target':target,'model':label,'train_n':len(tr),'test_n':len(te),'actual_mean':te[target].mean(),'predicted_mean':pred.mean(),'bias_prediction_minus_actual':-e.mean(),'mae':np.abs(e).mean(),'rmse':np.sqrt((e**2).mean())}
    if kind=='occurrence': row.update(brier=brier_score_loss(te[target],pred),log_loss=log_loss(te[target],pred))
    scores.append(row)
    if kind=='occurrence':
     r=pd.DataFrame({'prediction':pred,'actual':te[target].to_numpy()});r['bin']=pd.qcut(r.prediction.rank(method='first'),10,labels=False)
     for b,g in r.groupby('bin'):reliability.append({'year':year,'gate':gate,'model':label,'bin':b,'n':len(g),'mean_prediction':g.prediction.mean(),'recorded_fraction':g.actual.mean()})
   actual_values=te[target].to_numpy();d=(actual_values-store['forecast'])**2-(actual_values-store['calendar'])**2;ci=interval(d,te.week)
   pairs.append({'year':year,'gate':gate,'target':target,'score':'Brier' if kind=='occurrence' else 'MSE','forecast_minus_calendar':d.mean(),'week_ci_low':ci[0],'week_ci_high':ci[1],'n':len(d),'weeks':te.week.nunique()})
   if kind=='occurrence' or target.endswith('total_lmp_da'):
    predictions.append(pd.DataFrame({'timestamp':te.timestamp,'year':year,'gate':gate,'target':target,'actual':actual_values,'calendar_prediction':store['calendar'],'forecast_prediction':store['forecast']}))
  # Training-relative calendar load anomaly watchlist.
  if gate in ['A','C']:
   pressure='RTO' if gate=='A' else 'MIDATL';cells=['month','hour','weekend']
   center=tr.groupby(cells)[pressure].median().rename('training_calendar_median')
   tr=tr.join(center,on=cells);te=te.join(center,on=cells)
   train_anomaly=tr[pressure]-tr.training_calendar_median;threshold=np.quantile(train_anomaly,.75)
   te['anomaly']=te[pressure]-te.training_calendar_median;te['watch']=te.anomaly.gt(threshold)
   te['calendar_cell']=te[cells].astype(str).agg('_'.join,axis=1)
   ctrl=te.loc[~te.watch].groupby('calendar_cell')[targets].agg(['mean','size'])
   for _,g in te.loc[te.watch].groupby('calendar_cell'):
    cell=g.calendar_cell.iloc[0]
    if cell not in ctrl.index or ctrl.loc[cell,('event_recorded','size')]<3:continue
    for _,r in g.iterrows():
     row={'year':year,'gate':gate,'timestamp':r.timestamp,'week':r.week,'pressure_area':pressure,'forecast_mw':r[pressure],'anomaly_mw':r.anomaly,'threshold_mw':threshold,'control_n':ctrl.loc[cell,('event_recorded','size')]}
     for target in targets:
      row[target]=r[target];row[target+'__control']=ctrl.loc[cell,(target,'mean')];row[target+'__difference']=r[target]-ctrl.loc[cell,(target,'mean')]
     watch_hours.append(row)
   wh=pd.DataFrame([r for r in watch_hours if r['year']==year and r['gate']==gate])
   for target in targets:
    d=wh[target+'__difference'];ci=interval(d,wh.week)
    watch.append({'year':year,'gate':gate,'pressure_area':pressure,'target':target,'training_anomaly_threshold_mw':threshold,'all_watch_hours':int(te.watch.sum()),'supported_watch_hours':len(wh),'all_test_hours':len(te),'watch_mean':wh[target].mean(),'control_mean':wh[target+'__control'].mean(),'difference':d.mean(),'week_ci_low':ci[0],'week_ci_high':ci[1],**{'watch_'+k:v for k,v in distributions(wh[target]).items()},'negative_difference_fraction':np.mean(d<0)})
 print('Completed year',year,flush=True)
for name,data in [('model_scores',scores),('paired_score_differences',pairs),('reliability',reliability),('watchlist',watch)]:pd.DataFrame(data).to_csv(TAB/(name+'.csv'),index=False)
pd.concat(predictions).to_csv(TAB/'predictions.csv.gz',index=False);pd.DataFrame(watch_hours).to_csv(TAB/'watch_hours.csv.gz',index=False)
# Fig 1 makes coverage and accuracy explicit.
acc=pd.DataFrame(accuracy);fig,axs=plt.subplots(1,2,figsize=(13,4.7),layout='constrained')
x=np.arange(4)
for j,year in enumerate([2024,2025,2026]):
 a=acc[(acc.year.eq(year))&(acc.model.eq('archived_forecast'))].set_index('area').loc[list(AREAS)]
 axs[0].bar(x+(j-1)*.24,a.mae/1000,.23,label=str(year),color=COLORS[str(year)])
axs[0].set_xticks(x,list(AREAS));axs[0].set_ylabel('Mean absolute load error (GW)');axs[0].set_title('Prior-day 09:00 archive: load error');axs[0].legend(frameon=False)
a=acc[acc.year.eq(2026)].pivot(index='area',columns='model',values='mae').loc[list(AREAS)]
axs[1].bar(x-.18,a.archived_forecast/1000,.36,label='Archived forecast',color='#007c91');axs[1].bar(x+.18,a.week_earlier_actual/1000,.36,label='Actual load seven days earlier',color='#bbbbbb');axs[1].set_xticks(x,list(AREAS));axs[1].set_ylabel('2026 mean absolute load error (GW)');axs[1].set_title('Compare the same entity and hours');axs[1].legend(frameon=False)
fig.suptitle('Load is forecastable; historical publication before entry remains unverified',fontsize=16);fig.savefig(FIG/'load_forecast_accuracy.png');plt.close(fig)
# Fig2 calibration separates better demand forecasts from calibrated gate odds.
scores_df=pd.DataFrame(scores);rel=pd.DataFrame(reliability);fig,axs=plt.subplots(2,3,figsize=(13.6,8.2),layout='constrained')
for j,gate in enumerate(['A','B','C']):
 for i,year in enumerate([2025,2026]):
  ax=axs[i,j];g=rel[(rel.gate.eq(gate))&(rel.year.eq(year))]
  for model in ['calendar','forecast']:
   r=g[g.model.eq(model)];ax.plot(r.mean_prediction*100,r.recorded_fraction*100,'o-',label=model.title(),color=COLORS[model])
  lim=100;ax.plot([0,lim],[0,lim],ls='--',color='#cccccc',lw=1);ax.set_xlim(0,lim);ax.set_ylim(0,lim)
  ss=scores_df[(scores_df.gate.eq(gate))&(scores_df.year.eq(year))&(scores_df.target.eq('event_recorded'))]
  ax.set_title(f'{gate}, {year}: actual {ss.actual_mean.iloc[0]:.1%}');ax.set_xlabel('Mean estimated probability (%)');ax.set_ylabel('Hours containing binding (%)');ax.legend(frameon=False,fontsize=10)
fig.suptitle('Adding earlier demand information does not remove changing gate relationships',fontsize=16);fig.savefig(FIG/'gate_calibration.png');plt.close(fig)
# Fig3 direct paired prediction differences, keep all named markets separate.
pairdf=pd.DataFrame(pairs);fig,axs=plt.subplots(1,2,figsize=(13.5,5.8),layout='constrained')
for ax,target_kind,title in [(axs[0],'event_recorded','Occurrence: forecast minus calendar Brier'),(axs[1],'total_lmp_da','DA total price: forecast minus calendar MSE')]:
 g=pairdf[pairdf.target.eq(target_kind)] if target_kind=='event_recorded' else pairdf[pairdf.target.str.endswith(target_kind)]
 labels=[]
 for k,(_,r) in enumerate(g.iterrows()):
  ax.errorbar(r.forecast_minus_calendar,k,xerr=np.array([[r.forecast_minus_calendar-r.week_ci_low],[r.week_ci_high-r.forecast_minus_calendar]]),fmt='o',color=COLORS[str(r.year)],capsize=3)
  labels.append(f"{r.gate} {r.year}"+(' local' if r.target.startswith('B_local') else ' hub' if r.target.startswith('B_hub') else ''))
 ax.axvline(0,color='#777',lw=1);ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_title(title);ax.set_xlabel('Negative values favor demand model\nDots: paired score difference; bars: week-resampling range')
fig.suptitle('Judge usable information against the same later-hour benchmark',fontsize=16);fig.savefig(FIG/'paired_model_scores.png');plt.close(fig)
# Fig4 conditional watch differences vs matched calendar hours.
w=pd.DataFrame(watch);fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
for ax,kind,title,scale in [(axs[0],'event_recorded','Binding-hour fraction',100),(axs[1],'total_lmp_da','Named DA total spread',1)]:
 g=w[w.target.eq(kind)] if kind=='event_recorded' else w[w.target.str.endswith(kind)]
 labels=[]
 for k,(_,r) in enumerate(g.iterrows()):
  ax.errorbar(r.difference*scale,k,xerr=np.array([[(r.difference-r.week_ci_low)*scale],[(r.week_ci_high-r.difference)*scale]]),fmt='o',color=COLORS[str(r.year)],capsize=3);labels.append(f'{r.gate} {r.year}  n={r.supported_watch_hours:,}')
 ax.axvline(0,color='#777',lw=1);ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_title(title);ax.set_xlabel('Watch minus same-calendar nonwatch\n'+('Percentage points' if scale==100 else '$/MWh'))
fig.suptitle('High forecast demand can mark price exposure without identifying the gate',fontsize=16);fig.savefig(FIG/'forecast_watchlist.png');plt.close(fig)
# Full empirical price distributions preserve every supported watch target and matched mean.
wh=pd.DataFrame(watch_hours);fig,axs=plt.subplots(1,2,figsize=(13,4.8),layout='constrained')
for ax,gate in zip(axs,['A','C']):
 g=wh[(wh.gate.eq(gate))&(wh.year.eq(2026))];target=gate+'__total_lmp_da'
 for label,field,color in [('Watch hour',target,'#007c91'),('Mean of calendar controls',target+'__control','#999999')]:
  x=np.sort(g[field].to_numpy());ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=label,color=color,lw=1.8)
 ax.axvline(0,color='#bbbbbb',lw=1);ax.set_ylim(0,1);ax.set_xlabel('DA '+('BGE_RESID_AGG' if gate=='A' else 'COMED_RESID_AGG')+' minus WESTERN HUB ($/MWh)');ax.set_ylabel('Fraction at or below spread');ax.set_title(f'{gate}: 2026, {len(g):,} supported watch hours');ax.legend(frameon=False)
fig.suptitle('A watch condition describes a distribution, not a guaranteed price sign',fontsize=16);fig.savefig(FIG/'watch_price_distributions.png');plt.close(fig)
result={'status':'complete, publication-time validation remains unresolved','inventory':inventory,'model_scores':scores,'paired_scores':pairs,'watchlist':watch,'sources':['D01','D02','A29','A32','A33','P24','T02'],'limitations':['Forecast evaluation time is not verified publication time.','Historical renewable forecasts do not overlap the assessment; no forward wind or solar test.','Previously explored 2025/2026 years are not fresh confirmation.','Anonymous gate clock and market remain provisional.','No executable quote, official settlement or trade-profit backtest.','Intervals condition on fixed models and omit specification/future-regime uncertainty.'],'figures':[str(p.relative_to(ROOT)) for p in sorted(FIG.glob('*.png'))]}
save_json('result.json',safe(result))
print('Saved forecast analysis',flush=True)

# Continue with check_and_refine.py, recent_benchmark.py and refresh_accuracy.py --full-rebuild.
