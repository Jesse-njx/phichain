"""Independent structural, timing and originality evidence for submitted baseline."""
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib,json,math,sys
from pathlib import Path
BASE=Path('/Users/jesse/Projects/PhiChain/phichain')
stage=sys.argv[1] if len(sys.argv)>1 else 'baseline'
B=BASE/'../research/overnight-study/original-chart'/stage
A=BASE/'../research/overnight-study/research'
side=json.loads((B/'chart.authoring.json').read_text());m=side['model'];ns=[n for l in m['lines'] for n in l['notes']]
v3=json.loads((B/'chart.phigros.json').read_text());native=json.loads((B/'chart.json').read_text())
beat=lambda value:F(value[0])+F(value[1],value[2])
source_meta=next(r for r in json.load(open(BASE/'../research/overnight-study/corpus/manifest.json')) if 'Cycle of Redemption' in r['title'])
source=json.load(open(BASE/source_meta['chart']['path']))
source_notes=[]
for i,l in enumerate(source['judgeLineList']):
 for side_key in ['notesAbove','notesBelow']:
  for n in l[side_key]:source_notes.append((F(str(n['time']))*F(15,8)/F(str(l['bpm'])),n['type'],n['positionX'],side_key))
report={'artifact':stage,'counts':dict(Counter(n['kind'] for n in ns)),'note_count':len(ns),'line_roles':[(l['id'],l['role']) for l in m['lines']],
        'source_eligibility':{'has_AT':source_meta['has_AT'],'IN_origin':source_meta['latest_creation_or_rechart_date'],'source_chart_sha256':source_meta['chart']['sha256']},
        'music_sha256_matches':hashlib.sha256((B/'music.ogg').read_bytes()).hexdigest()==source_meta['music']['sha256']}
# Match canonical representation tuples rather than trust counts or artist's reports.
kind={'tap':1,'drag':2,'hold':3,'flick':4}
expected=Counter((n['kind'],F(n['time']),F(n['end'])-F(n['time']),round(n['x'],8),n['side'],round(n['speed'],8)) for n in ns)
v3_decoded=Counter()
for l in v3['judgeLineList']:
 for side_key,side_name in [('notesAbove','above'),('notesBelow','below')]:
  for n in l[side_key]:
   at=F(str(n['time']))*F(15,8)/F(str(l['bpm']))
   duration=F(str(n['holdTime']))*F(15,8)/F(str(l['bpm'])) if n['type']==3 else 0
   rows=sorted(l['speedEvents'],key=lambda e:e['startTime'])
   onset_speed=next((e['value'] for e in rows if e['startTime']<=n['time']<e['endTime']),None)
   if onset_speed is None: raise ValueError('Export has no speed interval at head')
   speed=n['speed']/onset_speed if n['type']==3 else n['speed']
   v3_decoded[(next(k for k,v in kind.items() if v==n['type']),at,duration,round(n['positionX']/18,8),side_name,round(speed,8))]+=1
native_decoded=Counter((n['kind'],beat(n['beat'])*F(4,15),beat(n.get('hold_beat',[0,0,1]))*F(4,15),round(n['x']/1350,8),'above' if n['above'] else 'below',round(n['speed'],8)) for l in native['lines'] for n in l['notes'])
report['native_exact_normalized_match']=native_decoded==expected
# v3 floating raw timestamps may encode tiny numerical differences; compare nearest witness tolerance.
def compare(a,b):
 aa=sorted(a.elements(),key=lambda n:(float(n[1]),n[0],n[3]));bb=sorted(b.elements(),key=lambda n:(float(n[1]),n[0],n[3]))
 failures=[];maximum=0
 for x,y in zip(aa,bb):
  delta=max(abs(float(x[1]-y[1])),abs(float(x[2]-y[2])));maximum=max(maximum,delta)
  if x[0]!=y[0] or x[3:]!=y[3:] or delta>1e-8:failures.append({'source':list(map(str,x)),'export':list(map(str,y))})
 return {'matching':len(aa)==len(bb) and not failures,'max_time_error_seconds':maximum,'witnesses':failures[:10]}
report['official_roundtrip']=compare(expected,v3_decoded)
# Independently account declared continuous gestures and simultaneous fresh heads.
gestures=defaultdict(list);fresh=defaultdict(list);holds=[]
for n in ns:
 ann=n['annotation'];f=ann.get('finger_key');t=F(n['time']);end=F(n['end'])
 if n['kind']=='hold':holds.append({'start':t,'end':end,'finger':f,'gesture':ann.get('gesture'),'kind':'hold','x0':n['x'],'x1':n['x']})
 elif n['kind']=='drag':gestures[(f,ann.get('gesture'))].append(n)
 else:fresh[t].append(n)
for (f,g),group in gestures.items():
 group.sort(key=lambda n:F(n['time']));holds.append({'start':F(group[0]['time']),'end':F(group[-1]['time'])+F(1,30),'finger':f,'gesture':g,'kind':'drag','x0':group[0]['x'],'x1':group[-1]['x']})
# +1/8 beat =1/30s here; heuristic release allowance declared, not a timing truth.
conflicts=[];peak=0
for t in sorted({F(n['time']) for n in ns}):
 live=[h for h in holds if h['start']<=t<h['end']]
 owners=defaultdict(list)
 for h in live:owners[h['finger']].append(h['gesture'])
 for n in fresh[t]:owners[n['annotation'].get('finger_key')].append(n['annotation'].get('gesture'))
 peak=max(peak,len(owners))
 for f,gs in owners.items():
  if len(gs)>1:conflicts.append({'seconds':float(t),'finger':f,'gestures':gs})
report['assigned_occupancy']={'peak':peak,'conflicts':conflicts[:30],'conflict_count':len(conflicts),'method':'exact holds; each drag gesture through last head +1/8beat; fresh Tap/Flick contacts; not playtest'}
# Independent motion/release witnesses, including drags omitted from simple fresh-head lists.
for h in holds:
 if h['kind']=='drag':
  h['points']=sorted([(F(n['time']),n['x']) for n in gestures[(h['finger'],h['gesture'])]])
 else:h['points']=[(h['start'],h['x0']),(h['end'],h['x1'])]
def contact_x(h,t):
 points=h['points']
 for (a,x),(b,y) in zip(points,points[1:]):
  if a<=t<=b:return x+(y-x)*float((t-a)/(b-a))
 return points[-1][1]
coincident=[]
for t in sorted({F(n['time']) for n in ns}):
 active=[h for h in holds if h['start']<=t<h['end']]
 targets=[(h['finger'],contact_x(h,t),h['gesture']) for h in active]
 targets += [(n['annotation']['finger_key'],n['x'],n['annotation']['gesture']) for n in fresh[t]]
 for i,(f,x,g) in enumerate(targets):
  for of,ox,og in targets[i+1:]:
   if f!=of and abs(x-ox)<1e-7:coincident.append({'seconds':float(t),'fingers':[f,of],'gestures':[g,og],'native_x':x*1350})
releases=[]
for h in holds:
 later=sorted([n for n in ns if n['kind'] in ('tap','flick','hold') and n['annotation']['finger_key']==h['finger'] and F(n['time'])>=h['end']],key=lambda n:F(n['time']))
 if later:
  n=later[0];releases.append({'kind':h['kind'],'gesture':h['gesture'],'finger':h['finger'],'release_seconds':float(h['end']), 'next_seconds':float(F(n['time'])), 'gap_ms':float(F(n['time'])-h['end'])*1000,'travel_native_x':abs(h['x1']-n['x'])*1350,'next_kind':n['kind']})
report['coincident_assigned_fingers']={'count':len(coincident),'witnesses':coincident[:20],'limitation':'exact target coincidence; no hitbox or human comfort model'}
report['shortest_contact_release_windows']=sorted(releases,key=lambda r:r['gap_ms'])[:20]
peaks=json.load(open(A/'audio/RetributionCycleofRedemption.ArdolfvsDaily天利.json'))['onset_peak_seconds']
new_pulses=[n for n in ns if n['annotation'].get('evidence',{}).get('tier')=='audio_new_pulse_candidate']
report['novel_pulse_global_flux_crosscheck']=[{'seconds':float(F(n['time'])),'nearest_global_peak_ms':min(abs(float(F(n['time']))-p) for p in peaks)*1000} for n in new_pulses]
report['last_tail_seconds']=max(float(F(n['end'])) for n in ns)
report['audio_duration_seconds']=m['audio_duration_seconds']
report['tails_within_audio']=report['last_tail_seconds']<=m['audio_duration_seconds']
# Shared onset evidence is allowed; arrangement/type/position differences recorded separately.
source_times={t for t,k,x,s in source_notes};auth_times={F(n['time']) for n in ns}
shared=sum(any(abs(float(t-u))<1e-7 for u in source_times) for t in auth_times)
source_kind_times={(t,k) for t,k,x,s in source_notes}
kind_shared=sum(any(k==kind[n['kind']] and abs(float(F(n['time'])-t))<1e-7 for t,k in source_kind_times) for n in ns)
source_tuples=Counter((round(float(t),7),k,round(x,6),s) for t,k,x,s in source_notes)
auth_tuples=Counter((round(float(F(n['time'])),7),kind[n['kind']],round(n['x']*18,6),'notesAbove' if n['side']=='above' else 'notesBelow') for n in ns)
report['source_comparison']={'distinct_authored_onsets':len(auth_times),'distinct_source_onsets':len(source_times),'shared_authored_onsets':shared,'shared_time_and_kind_objects':kind_shared,'exact_source_local_tuple_intersection':sum((source_tuples&auth_tuples).values()),'limitation':'source-local x cannot establish presented physical equality across source carriers; matching musical time is legitimate evidence, not an originality verdict'}
report['evidence_tiers']=dict(Counter(n['annotation'].get('evidence',{}).get('tier','missing') for n in ns))
report['render_required']='renderer inspection of dense passages, holds, aesthetic motion and phrase transitions remains separate from structural checks'
(A/f'independent-original-{stage}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
