from pathlib import Path
import sqlite3,json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
DB=ROOT/'data/pjm.sqlite'
RNG=np.random.default_rng(20261009)
plt.rcParams.update({'font.size':12,'axes.titlesize':15,'axes.labelsize':12,'figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':150})
COLORS=['#1768AC','#DD8452','#46966A','#9A6FB0']

def savefig(name,fig):
 fig.savefig(OUT/'figures'/f'{name}.png',bbox_inches='tight'); plt.close(fig)
def csv(name,d):
 d.to_csv(OUT/'tables'/f'{name}.csv',index=False)
def summaries(v):
 v=pd.Series(v).dropna().to_numpy(); n=len(v)
 if not n:return {'n':0}
 s=np.sort(v); k=int(np.ceil(.05*n))
 return {'n':n,'mean':float(v.mean()),'median':float(np.median(v)),'p05':float(np.quantile(v,.05)),'p95':float(np.quantile(v,.95)),'negative_fraction':float((v<0).mean()),'positive_fraction':float((v>0).mean()),'bottom5_mean_contribution':float(s[:k].sum()/n),'top5_mean_contribution':float(s[-k:].sum()/n)}

c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
a=pd.read_sql_query("select timestamp, flowgate, event_recorded, avg_shadow_price, dst_transition_date from hourly_analysis",c)
a['timestamp']=pd.to_datetime(a.timestamp)
assert not a.duplicated(['timestamp','flowgate']).any()
occ=a.pivot(index='timestamp',columns='flowgate',values='event_recorded').rename(columns={'Flowgate A':'A','Flowgate B':'B','Flowgate C':'C'})
base=occ.loc[~a.drop_duplicates('timestamp').set_index('timestamp').dst_transition_date.astype(bool)].copy()
loads=pd.read_sql_query("select timestamp_source,region_zone,load_value from load where region_zone in ('BC Zone','DOM Zone','COMED Zone','PJM RTO Total','Mid-Atlantic Region','Southern Region','Western Region')",c)
assert not loads.duplicated(['timestamp_source','region_zone']).any()
loads.timestamp_source=pd.to_datetime(loads.timestamp_source)
loads=loads.pivot(index='timestamp_source',columns='region_zone',values='load_value').rename(columns={'BC Zone':'BC_load','DOM Zone':'DOM_load','COMED Zone':'COMED_load','PJM RTO Total':'PJM_load','Mid-Atlantic Region':'MIDATL_load','Southern Region':'SOUTH_load','Western Region':'WEST_load'})
base=base.join(loads)
for tab,val in [('solar','solar_value'),('wind','wind_value')]:
 d=pd.read_sql_query(f'select timestamp_source,area,{val} from {tab}',c)
 assert not d.duplicated(['timestamp_source','area']).any()
 d.timestamp_source=pd.to_datetime(d.timestamp_source)
 d=d.pivot(index='timestamp_source',columns='area',values=val)
 d.columns=[f'{x}_{tab}' for x in d.columns]
 base=base.join(d)
 if tab=='solar':
  for col in d:
   for lag in [1,3]:
    eligible=pd.Series(True,index=base.index)
    for h in range(lag+1):eligible &= pd.Series(base.index-pd.Timedelta(hours=h),index=base.index).isin(base.index)
    old=d[col].reindex(base.index-pd.Timedelta(hours=lag));old.index=base.index
    base[f'{col}_ramp{lag}']=(base[col]-old).where(eligible)
f=pd.read_sql_query('select timestamp_source,fuel_type,mw from fuel_generation',c)
f.timestamp_source=pd.to_datetime(f.timestamp_source)
assert not f.duplicated(['timestamp_source','fuel_type']).any()
f=f.pivot(index='timestamp_source',columns='fuel_type',values='mw')
fuel_total=f.sum(axis=1,min_count=10)
for fuel in ['Gas','Coal','Nuclear','Wind','Solar']:
 base[f'{fuel.lower()}_mw']=f[fuel]
 base[f'{fuel.lower()}_share']=f[fuel]/fuel_total*100
p=pd.read_sql_query('select timestamp_ept,pnode_name,total_lmp_da,total_lmp_rt,congestion_price_da,congestion_price_rt from pjm_multi_node_hourly_lmps',c)
p.timestamp_ept=pd.to_datetime(p.timestamp_ept)
p=p[p.timestamp_ept.isin(base.index)]
assert not p.duplicated(['timestamp_ept','pnode_name']).any()
for component in ['total_lmp','congestion_price']:
 for market in ['da','rt']:
  z=p.pivot(index='timestamp_ept',columns='pnode_name',values=f'{component}_{market}')
  key=f'{"total" if component=="total_lmp" else "cong"}_{market}'
  for gate,node in [('A','BGE_RESID_AGG'),('B','DOM_RESID_AGG'),('C','COMED_RESID_AGG')]:base[f'{gate}_{key}']=z[node]-z['WESTERN HUB']
  base[f'B_hub_{key}']=z['DOMINION HUB']-z['WESTERN HUB']
  base[f'B_pocket_{key}']=z[['ACCA','BASIN','BELLWOOD']].mean(axis=1)-z['DOMINION HUB']
  for node in ['ACCA','BASIN','BELLWOOD']:base[f'B_{node}_{key}']=z[node]-z['DOMINION HUB']
base['year']=base.index.year;base['month']=base.index.month;base['hour']=base.index.hour;base['weekend']=(base.index.dayofweek>=5).astype(int)
base['week']=(base.index-pd.to_timedelta(base.index.dayofweek,unit='D')).normalize()
base['date']=base.index.normalize()
base['stratum']=list(zip(base.month,base.hour,base.weekend))
base['year_stratum']=list(zip(base.year,base.month,base.hour,base.weekend))
base['jan_aug']=base.month<=8
base.to_pickle(OUT/'operating_panel.pkl')
csv('coverage',pd.DataFrame([{'year':y,'hours':len(d),'A_records':int(d.A.sum()),'B_records':int(d.B.sum()),'C_records':int(d.C.sum()),**{x+'_missing':int(d[x].isna().sum()) for x in ['BC_load','PJM_load','DOM_load','WEST_wind','MIDATL_solar','gas_mw']}} for y,d in base[base.jan_aug].groupby('year')]))

# A nested actual-state overlap against prior year.
specs={
 'Local and total demand':['BC_load','PJM_load'],
 'Add competing regions':['BC_load','PJM_load','DOM_load','MIDATL_load','WEST_load'],
 'Add wind and solar':['BC_load','PJM_load','DOM_load','MIDATL_load','WEST_load','WEST_wind','MIDATL_solar','SOUTH_solar'],
 'Add system fuel output':['BC_load','PJM_load','DOM_load','MIDATL_load','WEST_load','WEST_wind','MIDATL_solar','SOUTH_solar','gas_mw','coal_mw','nuclear_mw']}
train=base[base.jan_aug & (base.year==2025)]
test=base[base.jan_aug & (base.year==2026)]
scale=train[list(specs.values())[-1]].std()
matchsets={}; matchrows=[]
for label,cols in specs.items():
 pairs=[]
 for st,tg in test.dropna(subset=cols).groupby('stratum'):
  cg=train[(train.stratum==st)].dropna(subset=cols)
  if len(cg)<3:continue
  tx=tg[cols].to_numpy();cx=cg[cols].to_numpy()
  dif=(tx[:,None,:]-cx[None,:,:])/scale[cols].to_numpy()
  dist=np.sqrt((dif*dif).sum(axis=2));dist[(np.abs(dif)>.5).any(axis=2)]=np.inf
  near=np.argsort(dist,axis=1)[:,:3]
  valid=np.isfinite(np.take_along_axis(dist,near,axis=1)).all(axis=1)
  for k in np.flatnonzero(valid):
   ct=cg.index[near[k]]
   pairs.append({'target':tg.index[k],'controls':ct,'distance':float(dist[k,near[k]].mean())})
   for j in near[k]:matchrows.append({'specification':label,'target':tg.index[k],'control':cg.index[j],'distance':float(dist[k,j])})
 matchsets[label]=pairs
csv('a_neighbors',pd.DataFrame(matchrows))
common=set.intersection(*[{r['target'] for r in pairs} for pairs in matchsets.values()])

def paired_stats(pairs,cols,blockdays=7,nboot=799):
 if not pairs:return {}
 targ=pd.Index([r['target'] for r in pairs]);ctrl=np.array([r['controls'].to_numpy() for r in pairs]);ctrlflat=pd.Index(ctrl.ravel())
 tv=base.loc[targ,cols].to_numpy(float);cv=base.loc[ctrlflat,cols].to_numpy(float).reshape(len(targ),3,len(cols))
 dif=tv-cv.mean(axis=1)
 # Independent target and baseline calendar blocks, preserving reused controls.
 td=((targ-pd.Timestamp('2024-01-01')).days//blockdays).to_numpy();cd=((ctrlflat-pd.Timestamp('2024-01-01')).days//blockdays).to_numpy().reshape(len(targ),3)
 tu,ti=np.unique(td,return_inverse=True);cu,ci=np.unique(cd,return_inverse=True);ci=ci.reshape(len(targ),3)
 boot=[]
 for _ in range(nboot):
  tw=RNG.multinomial(len(tu),np.ones(len(tu))/len(tu))[ti]
  cw=RNG.multinomial(len(cu),np.ones(len(cu))/len(cu))[ci]
  den=cw.sum(axis=1);ok=(den>0)&(tw>0)
  if not ok.any():continue
  ctl=(cv[ok]*cw[ok,:,None]).sum(axis=1)/den[ok,None]
  boot.append(np.average(tv[ok]-ctl,axis=0,weights=tw[ok]))
 boot=np.asarray(boot)
 return {col:{'target_mean':float(tv[:,j].mean()),'control_mean':float(cv[:,:,j].mean()),'difference':float(dif[:,j].mean()),'lo':float(np.quantile(boot[:,j],.025)),'hi':float(np.quantile(boot[:,j],.975))} for j,col in enumerate(cols)}
a_rows=[];a_balance=[];a_robust=[]
for label,pairs in matchsets.items():
 for support,ps in [('own',pairs),('common',[r for r in pairs if r['target'] in common])]:
  stats=paired_stats(ps,['A','A_total_da','A_cong_da','A_total_rt','A_cong_rt'])
  for outcome,res in stats.items():a_rows.append({'specification':label,'support':support,'outcome':outcome,'target_hours':len(ps),'target_fraction':len(ps)/len(test),'unique_controls':len(set(x for r in ps for x in r['controls'])),'mean_distance':np.mean([r['distance'] for r in ps]),**res})
  if ps:
   for col in list(specs.values())[-1]:
    t=base.loc[[r['target'] for r in ps],col];v=np.array([base.loc[r['controls'],col].mean() for r in ps])
    a_balance.append({'specification':label,'support':support,'covariate':col,'target_mean':t.mean(),'control_mean':v.mean(),'standardized_difference':(t.mean()-v.mean())/scale[col]})
 for b in [1,14]:
  ps=[r for r in pairs if r['target'] in common]
  stat=paired_stats(ps,['A'],blockdays=b,nboot=399)
  if stat:a_robust.append({'specification':label,'block_days':b,'target_hours':len(ps),**stat['A']})
a_results=pd.DataFrame(a_rows);csv('a_nested_matches',a_results);csv('a_match_balance',pd.DataFrame(a_balance));csv('a_block_sensitivity',pd.DataFrame(a_robust))
fig,axes=plt.subplots(1,2,figsize=(13,5.5),gridspec_kw={'width_ratios':[1.1,1]})
for support,color,offset in [('own',COLORS[0],-.10),('common',COLORS[1],.10)]:
 d=a_results[(a_results.support==support)&(a_results.outcome=='A')].set_index('specification').loc[list(specs)]
 x=np.arange(len(d));axes[0].errorbar(d.difference*100,x+offset,xerr=np.array([d.difference-d.lo,d.hi-d.difference])*100,fmt='o',capsize=4,color=color,label=f'{support} support')
axes[0].axvline(0,color='#666',lw=1);axes[0].set_yticks(np.arange(4),list(specs));axes[0].invert_yaxis();axes[0].set_xlabel('2026 minus matched 2025 recorded fraction (points)');axes[0].legend(fontsize=10)
d=a_results[(a_results.support=='own')&(a_results.outcome=='A')].set_index('specification').loc[list(specs)]
axes[1].barh(np.arange(4),d.target_hours,color=COLORS[0]);axes[1].set_yticks(np.arange(4),['']*4);axes[1].invert_yaxis();axes[1].set_xlabel(f'2026 hours with three controls (of {len(test):,})')
for i,r in enumerate(d.itertuples()):axes[1].text(r.target_hours+30,i,f'{r.target_hours:,}',va='center')
fig.suptitle('A: adding other regions and supply can change the conclusion — and the coverage')
fig.text(.01,-.02,f'Actual-state nearest matches; same month, hour and week type. Every included input within 0.5 baseline SD.\nCommon support: {len(common):,} hours. Bars are resampled-week intervals, not causal or forecast intervals.',fontsize=10)
savefig('a_competing_demand',fig)

# All five original input families, recalculated occurrence/control calendar contrasts.
features={'A':['BC_load','DOM_load','MIDATL_load','PJM_load','WEST_wind','MIDATL_solar','MIDATL_solar_ramp1','MIDATL_solar_ramp3','gas_mw','coal_mw','nuclear_mw'],
'B':['DOM_load','MIDATL_load','PJM_load','SOUTH_wind','SOUTH_solar','SOUTH_solar_ramp1','SOUTH_solar_ramp3','gas_mw','coal_mw','nuclear_mw'],
'C':['COMED_load','MIDATL_load','PJM_load','WEST_wind','WEST_solar','WEST_solar_ramp1','WEST_solar_ramp3','gas_mw','coal_mw','nuclear_mw']}
ctx=[]
for gate,cols in features.items():
 for year,d in base[base.jan_aug].groupby('year'):
  for col in cols+[f'{gate}_total_da',f'{gate}_cong_da',f'{gate}_total_rt',f'{gate}_cong_rt']:
   v=d[[gate,col,'stratum','week']].dropna()
   sums=v.groupby(['stratum',gate])[col].agg(['mean','size'])
   ss=[]
   for st,g in v.groupby('stratum'):
    e=g[g[gate]==1];ct=g[g[gate]==0]
    if len(e) and len(ct)>=3:
     ss.append((e[col].sum(),len(e),ct[col].mean()*len(e),len(ct)))
   if ss:
    z=np.array(ss);ctx.append({'gate':gate,'year':year,'input':col,'record_hours':int(z[:,1].sum()),'control_hours':int(z[:,3].sum()),'record_mean':z[:,0].sum()/z[:,1].sum(),'control_mean':z[:,2].sum()/z[:,1].sum(),'difference':(z[:,0].sum()-z[:,2].sum())/z[:,1].sum()})
csv('five_input_calendar_contrasts',pd.DataFrame(ctx))

# Joint states, with all four cells and their actual supported prices.
def joint_table(gate,xcol,ycol,daylight=False):
 rows=[];details=[]
 d=base[base.jan_aug].copy()
 if daylight:d=d[d.hour.between(8,17)]
 for year,yd in d.groupby('year'):
  yd=yd.dropna(subset=[xcol,ycol,f'{gate}_total_da',f'{gate}_cong_da'])
  yd['xhigh']=yd[xcol]>yd.groupby('stratum')[xcol].transform('median')
  yd['yhigh']=yd[ycol]>yd.groupby('stratum')[ycol].transform('median')
  yd['cell']=yd.xhigh.astype(int)*2+yd.yhigh.astype(int)
  counts=yd.groupby(['stratum','cell']).size().unstack(fill_value=0).reindex(columns=range(4),fill_value=0)
  good=counts[(counts>=3).all(axis=1)].index
  z=yd[yd.stratum.isin(good)].copy();weights=z.groupby('stratum').size();weights=weights/weights.sum()
  outcomes=[gate,f'{gate}_total_da',f'{gate}_cong_da',f'{gate}_total_rt',f'{gate}_cong_rt']
  if gate=='B':outcomes+=['B_hub_total_da','B_hub_cong_da','B_hub_total_rt','B_hub_cong_rt','B_pocket_total_da','B_pocket_cong_da','B_pocket_total_rt','B_pocket_cong_rt']
  sid,slevels=pd.factorize(z.stratum)
  groups=sid*4+z.cell.to_numpy(); nstr=len(slevels); ng=nstr*4
  outcomes_array=z[outcomes].to_numpy(float)
  original_counts=np.bincount(groups,minlength=ng).reshape(nstr,4)
  stratum_weights=original_counts.sum(axis=1)/len(z)
  original_sums=np.stack([np.bincount(groups,weights=outcomes_array[:,j],minlength=ng) for j in range(len(outcomes))],axis=1).reshape(nstr,4,len(outcomes))
  original_means=original_sums/original_counts[:,:,None]
  estimates={cell:(original_means[:,cell,:]*stratum_weights[:,None]).sum(axis=0) for cell in range(4)}
  week_codes,wi=np.unique(z.week,return_inverse=True);boot=[]
  for _ in range(799):
   bw=RNG.multinomial(len(week_codes),np.ones(len(week_codes))/len(week_codes))[wi]
   bcounts=np.bincount(groups,weights=bw,minlength=ng).reshape(nstr,4)
   bsums=np.stack([np.bincount(groups,weights=outcomes_array[:,j]*bw,minlength=ng) for j in range(len(outcomes))],axis=1).reshape(nstr,4,len(outcomes))
   bmeans=np.divide(bsums,bcounts[:,:,None],out=np.full_like(bsums,np.nan),where=bcounts[:,:,None]>0)
   result=[]
   for cell in range(4):
    valid=bcounts[:,cell]>0;w=stratum_weights[valid]
    result.append((bmeans[valid,cell,:]*w[:,None]).sum(axis=0)/w.sum())
   boot.append(result)
  boot=np.asarray(boot)
  for cell in range(4):
   dc=z[z.cell==cell]
   for j,col in enumerate(outcomes):rows.append({'gate':gate,'year':year,'x':xcol,'y':ycol,'xhigh':cell//2,'yhigh':cell%2,'outcome':col,'hours':len(dc),'records':int(dc[gate].sum()),'retained_total_hours':len(z),'eligible_total_hours':len(yd),'calendar_cells':len(good),'estimate':estimates[cell][j],'lo':np.nanquantile(boot[:,cell,j],.025),'hi':np.nanquantile(boot[:,cell,j],.975),'mean_x':dc[xcol].mean(),'mean_y':dc[ycol].mean()})
   for key,val in summaries(dc[f'{gate}_total_da']).items():details.append({'gate':gate,'year':year,'x':xcol,'y':ycol,'xhigh':cell//2,'yhigh':cell%2,'metric':key,'value':val})
  # Paired price/occurrence interaction contrasts use the same bootstrap arrays.
  for yh in [0,1]:
   v=estimates[2+yh]-estimates[yh];b=boot[:,2+yh,:]-boot[:,yh,:]
   for j,col in enumerate(outcomes):rows.append({'gate':gate,'year':year,'x':xcol,'y':ycol,'xhigh':'high-minus-low','yhigh':yh,'outcome':col,'hours':len(z),'records':int(z[gate].sum()),'retained_total_hours':len(z),'eligible_total_hours':len(yd),'calendar_cells':len(good),'estimate':v[j],'lo':np.nanquantile(b[:,j],.025),'hi':np.nanquantile(b[:,j],.975),'mean_x':np.nan,'mean_y':np.nan})
 return pd.DataFrame(rows),pd.DataFrame(details)
ct,cd=joint_table('C','WEST_wind','MIDATL_load');csv('c_wind_demand_joint',ct);csv('c_joint_price_distributions',cd)
bt,bd=joint_table('B','SOUTH_solar','DOM_load',daylight=True);csv('b_solar_demand_joint',bt);csv('b_joint_price_distributions',bd)
for label,tab,gate,mainx in [('c_wind_demand',ct,'C','WEST wind'),('b_solar_demand',bt,'B','SOUTH solar')]:
 fig,axes=plt.subplots(2,3,figsize=(14,8),sharex=True)
 for i,year in enumerate([2024,2025,2026]):
  for j,outcome in enumerate([gate,f'{gate}_total_da']):
   ax=axes[j,i];d=tab[(tab.year==year)&(tab.outcome==outcome)&(tab.xhigh!='high-minus-low')].sort_values(['yhigh','xhigh'])
   positions=np.arange(4);mult=100 if outcome==gate else 1
   ax.bar(positions,d.estimate*mult,color=[COLORS[0],COLORS[1]]*2,alpha=.85)
   ax.errorbar(positions,d.estimate*mult,yerr=np.array([d.estimate-d.lo,d.hi-d.estimate])*mult,fmt='none',ecolor='#333',capsize=4)
   ax.set_xticks(positions,['Low / low','High / low','Low / high','High / high'],rotation=30,ha='right')
   if j==0:ax.set_title(f'{year}\n{int(d.retained_total_hours.iloc[0]):,}/{int(d.eligible_total_hours.iloc[0]):,} hours supported')
   if i==0:ax.set_ylabel('Hours containing binding (%)' if j==0 else f'{gate} named DA total spread ($/MWh)')
   ax.axhline(0,color='#666',lw=.7)
 fig.suptitle(f'{gate}: {mainx} and demand must be tested together')
 fig.text(.02,-.01,f'Labels: {mainx} / {"Mid-Atlantic" if gate=="C" else "Dominion"} demand, relative to same-month/hour/week-type medians.\nAll four states use identical calendar weights; resampled-week intervals. Regional proxies do not identify a branch.',fontsize=10)
 fig.tight_layout(rect=[0,.02,1,.94]);savefig(label,fig)

# B solar ramps and prices: calendar standardized high vs low within similar demand state.
br=[]
for feature in ['SOUTH_solar','SOUTH_solar_ramp1','SOUTH_solar_ramp3']:
 z,_=joint_table('B',feature,'DOM_load',daylight=True);z['solar_feature']=feature;br.append(z)
br=pd.concat(br,ignore_index=True);csv('b_solar_ramp_states',br)
fig,axes=plt.subplots(1,3,figsize=(14,5))
for i,(outcome,title) in enumerate([('B','Binding frequency'),('B_pocket_cong_rt','Local bus basket minus Dominion Hub'),('B_hub_total_da','Dominion Hub minus Western Hub')]):
 ax=axes[i]
 for k,year in enumerate([2024,2025,2026]):
  z=br[(br.year==year)&(br.outcome==outcome)&(br.xhigh=='high-minus-low')&(br.yhigh==1)].set_index('solar_feature').loc[['SOUTH_solar','SOUTH_solar_ramp1','SOUTH_solar_ramp3']]
  mul=100 if outcome=='B' else 1;x=np.arange(3)+(k-1)*.16
  ax.errorbar(x,z.estimate*mul,yerr=np.array([z.estimate-z.lo,z.hi-z.estimate])*mul,fmt='o',capsize=3,color=COLORS[k],label=str(year))
 ax.axhline(0,color='#666',lw=.8);ax.set_xticks(range(3),['Solar level','1-hour change','3-hour change'],rotation=25,ha='right');ax.set_title(title,fontsize=13);ax.set_ylabel('High-minus-low solar (points)' if i==0 else 'High-minus-low solar ($/MWh)')
 if i==0:ax.legend(fontsize=10)
fig.suptitle('B: more solar and stronger solar ramps do not imply the same trade')
fig.text(.01,-.05,'Daylight hours, higher-than-calendar-median Dominion demand. All four input states retained with common calendar weights.\nThe local basket equally weights ACCA, BASIN and BELLWOOD. It is not the Dominion Hub contract.',fontsize=10)
fig.tight_layout(rect=[0,.04,1,.91]);savefig('b_solar_ramps_and_exposure',fig)

result={'purpose':'Independent recomputation of actual operating-state fundamentals, excluding causal and trading-forecast claims.','database':str(DB),'eligible_hours':len(base),'common_a_target_hours':len(common),'a_nested_matches':a_results.to_dict(orient='records'),'a_block_sensitivity':a_robust,'figures':[str(x.relative_to(ROOT)) for x in sorted((OUT/'figures').glob('*.png'))],'tables':[str(x.relative_to(ROOT)) for x in sorted((OUT/'tables').glob('*.csv'))],'checks':{'eligible_A_records':int(base.A.sum()),'eligible_B_records':int(base.B.sum()),'eligible_C_records':int(base.C.sum()),'unique_source_hours':base.index.is_unique,'price_coverage':int(base.A_total_da.notna().sum()),'fuel_complete_hours':int(fuel_total.reindex(base.index).notna().sum()),'common_a_targets_subset_each':all(common.issubset({r['target'] for r in ps}) for ps in matchsets.values())}}
(OUT/'result.json').write_text(json.dumps(result,indent=2,default=str))
print(json.dumps({'A':a_results[(a_results.support=='own')&(a_results.outcome=='A')].to_dict('records'),'A_common':len(common),'C_2026':ct[(ct.year==2026)&ct.outcome.isin(['C','C_total_da'])].to_dict('records'),'B_2026':bt[(bt.year==2026)&bt.outcome.isin(['B','B_pocket_cong_rt','B_hub_total_da'])].to_dict('records')},indent=2,default=str))
