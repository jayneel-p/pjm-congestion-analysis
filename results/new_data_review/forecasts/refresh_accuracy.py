"""Rebuild accuracy on common support with both target and lag-source DST exclusions."""
from pathlib import Path
import argparse
import hashlib,json,sqlite3

def build_arg_parser():
 parser=argparse.ArgumentParser(description="Refresh forecast accuracy on common support without refitting models.")
 parser.add_argument("--full-rebuild",action="store_true",help="Skip comparison with the old pre-fix model/watch byte hashes after a full rebuild; default checks that those files are unchanged.")
 return parser

args=build_arg_parser().parse_args()
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;TAB=OUT/'tables';FIG=OUT/'figures'
DST=['2024-03-10','2024-11-03','2025-03-09','2025-11-02','2026-03-08'];AREA={'RTO':'PJM RTO Total','MIDATL':'Mid-Atlantic Region','DOM':'DOM Zone','COMED':'COMED Zone'}
f=pd.read_csv(TAB/'selected_vintages.csv.gz',parse_dates=['timestamp']);f=f[~f.timestamp.dt.strftime('%Y-%m-%d').isin(DST)]
c=sqlite3.connect('file:'+str(ROOT/'data/pjm.sqlite')+'?mode=ro',uri=True);a=pd.read_sql_query('select opr_date,opr_hour,region_zone,load_value from load',c);c.close();a['timestamp']=pd.to_datetime(a.opr_date)+pd.to_timedelta(a.opr_hour-1,unit='h');a=a.pivot(index='timestamp',columns='region_zone',values='load_value')
accuracy=[];errors=[];checks=[];dropped=[]
def ck(name,x,y):
 x=np.asarray(x,float);y=np.asarray(y,float);assert np.allclose(x,y,rtol=1e-9,atol=1e-8,equal_nan=True),name;checks.append({'check':name,'scalars':int(x.size),'status':'pass'})
for area,entity in AREA.items():
 s=f[f.forecast_area.eq(area)].copy();s=s.merge(a[[entity]].rename(columns={entity:'actual'}),on='timestamp',how='left',validate='one_to_one')
 lag=a[[entity]].rename(columns={entity:'week_earlier_actual'});lag=lag.loc[~lag.index.strftime('%Y-%m-%d').isin(DST)];lag.index=lag.index+pd.Timedelta(days=7);s=s.merge(lag,on='timestamp',how='left',validate='one_to_one');s['error_actual_minus_forecast']=s.actual-s.forecast_load_mw
 errors.append(s[['timestamp','forecast_area','actual','forecast_load_mw','week_earlier_actual','error_actual_minus_forecast']])
 rawlag=a[entity].reindex(pd.DatetimeIndex(s.timestamp)-pd.Timedelta(days=7)).to_numpy(copy=True);bad=(s.timestamp-pd.Timedelta(days=7)).dt.strftime('%Y-%m-%d').isin(DST).to_numpy();rawlag[bad]=np.nan;ck(area+' delayed baseline source value with DST dates excluded',s.week_earlier_actual,rawlag)
 for year,g in s.groupby(s.timestamp.dt.year):
  banned=(g.timestamp-pd.Timedelta(days=7)).dt.strftime('%Y-%m-%d').isin(DST);assert g.loc[banned,'week_earlier_actual'].isna().all();dropped.append({'area':area,'year':int(year),'clock_ambiguous_lag_rows_removed_from_both_arms':int(banned.sum())});g=g.dropna(subset=['actual','forecast_load_mw','week_earlier_actual'])
  for model,field in [('archived_forecast','forecast_load_mw'),('week_earlier_actual','week_earlier_actual')]:
   e=g.actual-g[field];row={'area':area,'actual_entity':entity,'year':year,'model':model,'n':len(g),'mean':e.mean(),'median':e.median(),'p05':e.quantile(.05),'p95':e.quantile(.95),'positive_fraction':np.mean(e>0),'mae':np.abs(e).mean(),'rmse':np.sqrt(np.mean(e**2)),'abs_error_over_5pct':np.mean(np.abs(e)/g.actual>.05)};accuracy.append(row)
acc=pd.DataFrame(accuracy);acc.to_csv(TAB/'forecast_accuracy.csv',index=False);pd.concat(errors).to_csv(TAB/'load_errors.csv.gz',index=False)
# Re-read saved outputs, reconstruct summary with NumPy arrays independently of the table writer.
saved=pd.read_csv(TAB/'load_errors.csv.gz',parse_dates=['timestamp']);summ=pd.read_csv(TAB/'forecast_accuracy.csv')
for (area,year),g in saved.groupby(['forecast_area',saved.timestamp.dt.year]):
 g=g.dropna(subset=['actual','forecast_load_mw','week_earlier_actual'])
 for model,field in [('archived_forecast','forecast_load_mw'),('week_earlier_actual','week_earlier_actual')]:
  e=g.actual.to_numpy()-g[field].to_numpy();r=summ[summ.area.eq(area)&summ.year.eq(year)&summ.model.eq(model)].iloc[0];ck(f'{area}{year}{model} saved common-support error summary',[r.n,r['mean'],r['median'],r.p05,r.p95,r.mae,r.rmse],[len(e),np.mean(e),np.median(e),np.quantile(e,.05),np.quantile(e,.95),np.mean(np.abs(e)),np.sqrt(np.mean(e**2))])
plt.rcParams.update({'font.size':12,'axes.titlesize':14,'axes.labelsize':12,'figure.dpi':150,'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False});colors={2024:'#577590',2025:'#287d8e',2026:'#c66b32'};fig,axs=plt.subplots(1,2,figsize=(13,4.7),layout='constrained');x=np.arange(4)
for j,year in enumerate([2024,2025,2026]):
 a=acc[acc.year.eq(year)&acc.model.eq('archived_forecast')].set_index('area').loc[list(AREA)];axs[0].bar(x+(j-1)*.24,a.mae/1000,.23,label=str(year),color=colors[year])
axs[0].set_xticks(x,list(AREA));axs[0].set_ylabel('Mean absolute load error (GW)');axs[0].set_title('Prior-day 09:00 archive: load error');axs[0].legend(frameon=False)
a=acc[acc.year.eq(2026)].pivot(index='area',columns='model',values='mae').loc[list(AREA)];axs[1].bar(x-.18,a.archived_forecast/1000,.36,label='Archived forecast',color='#007c91');axs[1].bar(x+.18,a.week_earlier_actual/1000,.36,label='Actual load seven days earlier',color='#bbbbbb');axs[1].set_xticks(x,list(AREA));axs[1].set_ylabel('2026 mean absolute load error (GW)');axs[1].set_title('Compare the same entity and hours');axs[1].legend(frameon=False)
fig.suptitle('Load is forecastable; historical publication before entry remains unverified',fontsize=16);fig.supxlabel('Common support excludes clock-change dates in both delivery and seven-day-lag source',fontsize=10);fig.savefig(FIG/'load_forecast_accuracy.png');plt.close(fig)
verify=not args.full_rebuild
unchanged=None
if verify:
 pre=json.loads((OUT/'pre_accuracy_fix_hashes.json').read_text())
 unchanged={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()==hashval for n,hashval in pre.items()}
 assert all(unchanged.values()), 'Model/watch files differ from the accuracy-only baseline; use --full-rebuild only after the complete rebuild sequence.'
audit={'status':'pass','scalar_point_checks':sum(x['scalars'] for x in checks),'checks':checks,'excluded_lag_source_rows':dropped,'model_watch_files_unchanged':unchanged};(OUT/'accuracy_clock_audit.json').write_text(json.dumps(audit,indent=2));numeric=json.loads((OUT/'numeric_check.json').read_text());numeric['checks']=[x for x in numeric['checks'] if not x['check'].endswith('errors summary') and not x['check'].endswith('delayed baseline source value with DST dates excluded') and not x['check'].endswith('saved common-support error summary')]+checks;numeric['scalar_checks']=sum(x['scalars'] for x in numeric['checks']);numeric['accuracy_lag_clock_fix']=audit;(OUT/'numeric_check.json').write_text(json.dumps(numeric,indent=2));result=json.loads((OUT/'result.json').read_text());result['accuracy_lag_clock_fix']={'status':'pass','total_ambiguous_lag_source_rows':sum(x['clock_ambiguous_lag_rows_removed_from_both_arms'] for x in dropped),'model_watch_results_unchanged':True if verify else 'not applicable to a full refit rebuild','comparison_support':'Both forecast and week-earlier actual arms exclude target and lag-source clock-change dates.'};result['independent_check']['scalar_checks']=numeric['scalar_checks'];result['independent_check']['recent_benchmark_scalar_checks']=numeric.get('recent_benchmark_scalar_checks',0);result['forecast_accuracy']=json.loads(acc.to_json(orient='records'));(OUT/'result.json').write_text(json.dumps(result,indent=2))
hashes={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='final_hashes.json'};(OUT/'final_hashes.json').write_text(json.dumps(hashes,indent=2));print(acc[acc.year.eq(2026)].to_string(index=False));print('Accuracy audit scalar comparisons',audit['scalar_point_checks'])
