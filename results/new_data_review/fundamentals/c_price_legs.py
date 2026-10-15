from pathlib import Path
import sqlite3,pandas as pd,numpy as np,json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent;R=P.parents[2];b=pd.read_pickle(P/'operating_panel.pkl')
c=sqlite3.connect(f'file:{R}/data/pjm.sqlite?mode=ro',uri=True)
p=pd.read_sql_query("select timestamp_ept,pnode_name,total_lmp_da,congestion_price_da from pjm_multi_node_hourly_lmps where pnode_name in ('COMED_RESID_AGG','WESTERN HUB')",c);p.timestamp_ept=pd.to_datetime(p.timestamp_ept);p=p[p.timestamp_ept.isin(b.index)]
p=p.pivot(index='timestamp_ept',columns='pnode_name',values=['total_lmp_da','congestion_price_da']);p.columns=['__'.join(x) for x in p.columns];b=b.join(p);rows=[];rng=np.random.default_rng(20261012)
for year,yd in b[b.jan_aug].groupby('year'):
 yd=yd.dropna(subset=['WEST_wind','MIDATL_load','C_total_da','C_cong_da']).copy();yd['wh']=yd.WEST_wind>yd.groupby('stratum').WEST_wind.transform('median');yd['dh']=yd.MIDATL_load>yd.groupby('stratum').MIDATL_load.transform('median');yd['cell']=yd.wh.astype(int)*2+yd.dh.astype(int)
 counts=yd.groupby(['stratum','cell']).size().unstack(fill_value=0).reindex(columns=range(4),fill_value=0);good=counts[(counts>=3).all(axis=1)].index;z=yd[yd.stratum.isin(good)]
 cols=list(p.columns)+['C_total_da','C_cong_da'];sid,slevels=pd.factorize(z.stratum);groups=sid*4+z.cell.to_numpy();ns=len(slevels);ng=ns*4;v=z[cols].to_numpy(float)
 cnt=np.bincount(groups,minlength=ng).reshape(ns,4);sw=cnt.sum(axis=1)/len(z)
 sums=np.stack([np.bincount(groups,weights=v[:,j],minlength=ng) for j in range(len(cols))],axis=1).reshape(ns,4,len(cols));means=sums/cnt[:,:,None];est=(means*sw[:,None,None]).sum(axis=0)
 wu,wi=np.unique(z.week,return_inverse=True);boot=[]
 for _ in range(799):
  rw=rng.multinomial(len(wu),np.ones(len(wu))/len(wu))[wi];bc=np.bincount(groups,weights=rw,minlength=ng).reshape(ns,4)
  bs=np.stack([np.bincount(groups,weights=v[:,j]*rw,minlength=ng) for j in range(len(cols))],axis=1).reshape(ns,4,len(cols));bm=np.divide(bs,bc[:,:,None],out=np.full_like(bs,np.nan),where=bc[:,:,None]>0);vals=[]
  for cell in range(4):
   valid=bc[:,cell]>0;w=sw[valid];vals.append((bm[valid,cell,:]*w[:,None]).sum(axis=0)/w.sum())
  boot.append(vals)
 boot=np.array(boot)
 for state in range(4):
  for j,col in enumerate(cols):rows.append({'year':year,'wind_high':state//2,'MIDATL_demand_high':state%2,'price_leg':col,'mean':est[state,j],'week_lo':np.quantile(boot[:,state,j],.025),'week_hi':np.quantile(boot[:,state,j],.975),'same_support_hours':len(z),'cell_hours':int((z.cell==state).sum()),'calendar_cells':len(good)})
r=pd.DataFrame(rows);r.to_csv(P/'tables/c_joint_price_legs.csv',index=False)
for year in [2024,2025,2026]:
 for wind in [0,1]:
  for demand in [0,1]:
   q=r[(r.year==year)&(r.wind_high==wind)&(r.MIDATL_demand_high==demand)].set_index('price_leg')['mean']
   assert abs(q['total_lmp_da__COMED_RESID_AGG']-q['total_lmp_da__WESTERN HUB']-q.C_total_da)<1e-10
plt.rcParams.update({'font.size':12,'axes.titlesize':14,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(13,6),gridspec_kw={'width_ratios':[1.25,1]})
z=r[(r.year==2026)&(r.MIDATL_demand_high==1)];x=np.arange(2);colors=['#1768AC','#DD8452']
for i,(leg,label) in enumerate([('total_lmp_da__COMED_RESID_AGG','COMED_RESID_AGG'),('total_lmp_da__WESTERN HUB','WESTERN HUB')]):
 d=z[z.price_leg==leg].sort_values('wind_high');pos=x+(i-.5)*.30
 axes[0].bar(pos,d['mean'],.29,color=colors[i],label=label);axes[0].errorbar(pos,d['mean'],yerr=np.array([d['mean']-d.week_lo,d.week_hi-d['mean']]),fmt='none',ecolor='#333',capsize=4)
 for px,val in zip(pos,d['mean']):axes[0].text(px,val+2,f'${val:.2f}',ha='center',va='bottom',fontsize=11,bbox={'facecolor':'white','edgecolor':'none','pad':1.5})
axes[0].set_ylabel('Mean DA total LMP ($/MWh)');axes[0].set_title('Both outright prices are lower in higher-wind states');axes[0].legend(frameon=False,loc='upper right',fontsize=10);axes[0].set_ylim(0,180)
d=z[z.price_leg=='C_total_da'].sort_values('wind_high');axes[1].bar(x,d['mean'],.55,color='#46966A');axes[1].errorbar(x,d['mean'],yerr=np.array([d['mean']-d.week_lo,d.week_hi-d['mean']]),fmt='none',ecolor='#333',capsize=5)
for px,val in zip(x,d['mean']):axes[1].text(px,val+3,f'${val:.2f}',ha='center',va='bottom',fontsize=12,bbox={'facecolor':'white','edgecolor':'none','pad':2})
axes[1].axhline(0,color='#666',lw=.8);axes[1].set_ylabel('COMED_RESID_AGG minus WESTERN HUB ($/MWh)');axes[1].set_title('The relative discount is almost unchanged');axes[1].set_ylim(-80,5)
for ax in axes:ax.set_xticks(x,['Lower WEST wind\n979 hours','Higher WEST wind\n898 hours'])
fig.suptitle('C: lower power prices under wind do not imply a deeper ComEd discount',fontsize=16)
fig.text(.02,.035,'January–August 2026, higher-than-calendar-median Mid-Atlantic demand. Both groups use identical calendar weights.\nThese 1,877 hours belong to 3,821-hour four-state overlap; bars show week resampling. Actual operating states are not issued forecasts.',fontsize=10)
fig.subplots_adjust(left=.08,right=.98,bottom=.25,top=.82,wspace=.35);fig.savefig(P/'figures/c_two_price_legs.png',dpi=150,bbox_inches='tight');plt.close(fig)
res=json.loads((P/'result.json').read_text());res['c_price_legs']=rows;res['recommended_figures']=['results/new_data_review/fundamentals/figures/'+x for x in ['a_competing_demand.png','b_solar_ramps_and_exposure.png','c_two_price_legs.png','c_public_family_fundamentals.png','c_wind_demand.png']];res['figures']=[str(x.relative_to(R)) for x in sorted((P/'figures').glob('*.png'))];res['tables']=[str(x.relative_to(R)) for x in sorted((P/'tables').glob('*.csv'))];(P/'result.json').write_text(json.dumps(res,indent=2,default=str))
qa=json.loads((P/'figure_qa.json').read_text());qa['sha256']['c_two_price_legs.png']=hashlib.sha256((P/'figures/c_two_price_legs.png').read_bytes()).hexdigest();(P/'figure_qa.json').write_text(json.dumps(qa,indent=2));print(r[(r.year==2026)&(r.MIDATL_demand_high==1)].to_string(index=False))
