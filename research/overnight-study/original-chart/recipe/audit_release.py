"""Inspect exported annotated model; never changes a chart or authoring checkpoint."""
import json,sys
from pathlib import Path
from fractions import Fraction
from replay_baseline import audit,ROOT
folder=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'release-v2')
data=json.loads((folder/'chart.authoring.json').read_text());prior=json.loads((ROOT/'baseline-v3/chart.authoring.json').read_text());before={n['id']:n for l in prior['model']['lines'] for n in l['notes']};notes=[]
for l in data['model']['lines']:
    for n in l['notes']:
        v=dict(n,beat=str(Fraction(n['time'])*Fraction(15,4)),line_id=l['id'])
        if n['kind']=='hold':v['duration']=str((Fraction(n['end'])-Fraction(n['time']))*Fraction(15,4))
        notes.append(v)
audit(notes);(folder/'finger-audit.json').write_text((ROOT/'recipe/corrected-prospective-finger-audit.json').read_text())
changes=[];travel=[];clearance=[]
for n in notes:
    p=before[n['id']]
    for key in ['time','end','kind','side','speed']:
        if n[key]!=p[key]:changes.append([n['id'],key,p[key],n[key]])
    if n['annotation']['finger_key']!=p['annotation']['finger_key']:changes.append([n['id'],'ownership'])
    t=Fraction(n['time'])
    if n['kind']!='hold':
        for h in notes:
            if h['kind']=='hold' and Fraction(h['time'])<=t<Fraction(h['end']):clearance.append({'seconds':float(t),'head':n['id'],'held':h['id'],'center_distance_native':abs(n['x']-h['x'])*1350})
for f in ('L_middle','L_index','R_index','R_middle'):
    ns=sorted([n for n in notes if n['annotation']['finger_key']==f],key=lambda n:Fraction(n['time']))
    for a,b in zip(ns,ns[1:]):
        gap=float(Fraction(b['time'])-Fraction(a['time']));distance=abs(b['x']-a['x'])*1350
        if gap>0:travel.append({'finger':f,'from_s':float(Fraction(a['time'])),'to_s':float(Fraction(b['time'])),'kinds':[a['kind'],b['kind']],'gap_ms':gap*1000,'distance_native':distance,'native_units_per_second':distance/gap})
report={'digest':data['model_digest'],'baseline_digest':prior['model_digest'],'scoring_or_ownership_changes':changes,'notes':len(notes),'lateral_targets_changed':sum(n['x']!=before[n['id']]['x'] for n in notes),'max_lateral_change_native':max(abs(n['x']-before[n['id']]['x'])*1350 for n in notes),'fastest_travel_witnesses':sorted(travel,key=lambda v:v['native_units_per_second'],reverse=True)[:20],'minimum_active_hold_to_other_target_center_distance':min(clearance,key=lambda c:c['center_distance_native']) if clearance else None,'sparse_phrase_positions':[{'beat':n['beat'],'kind':n['kind'],'finger':n['annotation']['finger_key'],'native_x':n['x']*1350} for n in notes if n['annotation']['phrase']=='phrase-11'],'limitations':['Native-unit travel estimates are geometric; no human comfort/playtest proof.','Center distances alone do not establish complete approach-body occlusion; rendered sequence review required.']}
(folder/'baseline-invariants.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ['notes','scoring_or_ownership_changes','minimum_active_hold_to_other_target_center_distance']}))
