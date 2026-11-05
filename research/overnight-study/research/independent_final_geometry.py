"""Independent native/v3 and declared anchor geometry checks."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import json,math,sys
ROOT=Path('/Users/jesse/Projects/PhiChain/research/overnight-study/original-chart')
folder=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'final')
side=json.loads((folder/'chart.authoring.json').read_text());m=side['model'];base=json.loads((ROOT/'baseline-v3/chart.authoring.json').read_text())['model']
old={n['id']:n for l in base['lines'] for n in l['notes']}
lines={l['id']:l for l in m['lines']}
def value(line,ch,t):
 result={'x':0,'y':0,'rotation':0,'opacity':1,'speed':2.2222222222222223}[ch]
 for e in sorted([e for e in line['events'] if e['channel']==ch],key=lambda e:F(e['start'])):
  a,b=F(e['start']),F(e['end'])
  if t<a:break
  if t<b:return e['a']+(e['b']-e['a'])*float((t-a)/(b-a))
  result=e['b']
 return result
def world(line,n,t):
 r=math.radians(value(line,'rotation',t))
 return (1350*(value(line,'x',t)+n['x']*math.cos(r)),900*value(line,'y',t)+1350*n['x']*math.sin(r))
report={'folder':str(folder),'model_digest':side['model_digest'],'roles':dict(Counter(l['role'] for l in m['lines'])),'note_count':sum(len(l['notes']) for l in m['lines']),'scoring_semantic_changes':[],'finger_label_changes':[],'carrier_witnesses':[],'anchor_miss_witnesses':[],'empty_decoration_violations':[],'opposite_side_hand_witnesses':[],'lateral_changes':0,'max_lateral_change_native':0}
for l in m['lines']:
 if l['role']=='decorative' and l['notes']:report['empty_decoration_violations'].append(l['id'])
 for n in l['notes']:
  previous=old.get(n['id'])
  if previous is None:report['scoring_semantic_changes'].append({'id':n['id'],'field':'new id'});continue
  for key in ['kind','time','end','side','speed']:
   if n[key]!=previous[key]:report['scoring_semantic_changes'].append({'id':n['id'],'field':key})
  if n['annotation']['finger_key']!=previous['annotation']['finger_key']:report['finger_label_changes'].append(n['id'])
  at,end=F(n['time']),F(n['end']);anchor=lines[l['anchor_id']] if l['role']=='note_carrier' else l
  x,y=world(l,n,at);dx=x-value(anchor,'x',at)*1350;dy=y-value(anchor,'y',at)*900;angle=math.radians(value(anchor,'rotation',at));error=abs(-math.sin(angle)*dx+math.cos(angle)*dy)
  if error>1e-5:report['anchor_miss_witnesses'].append({'id':n['id'],'seconds':float(at),'perpendicular_native':error})
  delta=abs(x-previous['x']*1350)
  if delta>1e-5:report['lateral_changes']+=1
  report['max_lateral_change_native']=max(report['max_lateral_change_native'],delta)
  if n['annotation']['finger_key'][0]=='L' and x>27 or n['annotation']['finger_key'][0]=='R' and x<-27:report['opposite_side_hand_witnesses'].append(n['id'])
  if l['role']=='note_carrier':
   changing_end=max([F(e['end']) for e in l['events'] if e['channel'] in ['x','y','rotation'] and e['a']!=e['b']],default=F(0))
   report['carrier_witnesses'].append({'line_id':l['id'],'kind':n['kind'],'seconds':float(at),'world_x_native':x,'world_y_native':y,'settled_before_hit_seconds':float(at-changing_end),'carrier_opacity':value(l,'opacity',at),'assigned_anchor_opacity':value(anchor,'opacity',at)})
  if n['kind']=='hold':
   cuts={at,end}
   for row in (l,anchor):
    for e in row['events']:
     cuts.update(t for t in [F(e['start']),F(e['end'])] if at<t<end)
   cuts=sorted(cuts);samples=set(cuts)|{(a+b)/2 for a,b in zip(cuts,cuts[1:])}
   for t in samples:
    xx,yy=world(l,n,t);aa=math.radians(value(anchor,'rotation',t));err=abs(-math.sin(aa)*(xx-value(anchor,'x',t)*1350)+math.cos(aa)*(yy-value(anchor,'y',t)*900))
    if err>1e-5:report['anchor_miss_witnesses'].append({'id':n['id'],'seconds':float(t),'held_perpendicular_native':err})
report['timing_kind_duration_side_speed_preserved']=not report['scoring_semantic_changes']
report['finger_hypotheses_preserved']=not report['finger_label_changes']
report['limitations']=['Independent logical-canvas transform; sampled boundaries/midpoints, not continuous approach/occlusion/hitbox simulation','Lateral positions intentionally changed from baseline; unchanged rhythm/finger labels do not prove human comfort','Full played review is separate']
p=Path('/Users/jesse/Projects/PhiChain/research/overnight-study/research')/f'independent-{folder.name}-geometry.json';p.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
# Verify actual adapter event values against independent sidecar interpolation.
native=json.loads((folder/'chart.json').read_text());official=json.loads((folder/'chart.phigros.json').read_text())
trip=lambda v:F(v[0])+F(v[1],v[2])
failures=[];max_error=0.0
for i,l in enumerate(m['lines']):
 nr=native['lines'][i];vr=official['judgeLineList'][i]
 native_events=[];official_events=[]
 for e in nr['events']:
  v=e['value'];a=v['value'] if v['type']=='constant' else v['start'];b=v['value'] if v['type']=='constant' else v['end']
  multiplier={'x':1350,'y':900,'rotation':1,'opacity':255,'speed':4.5}[e['kind']]
  native_events.append({'channel':e['kind'],'start':str(trip(e['start_beat'])*F(4,15)),'end':str(trip(e['end_beat'])*F(4,15)),'a':a/multiplier,'b':b/multiplier})
 for key,chs in [('judgeLineMoveEvents',['x','y']),('judgeLineRotateEvents',['rotation']),('judgeLineDisappearEvents',['opacity']),('speedEvents',['speed'])]:
  for e in vr[key]:
   for ch in chs:
    if ch=='x':a,b=e['start']-.5,e['end']-.5
    elif ch=='y':a,b=e['start2']-.5,e['end2']-.5
    elif ch=='speed':a=b=e['value']
    else:a,b=e['start'],e['end']
    official_events.append({'channel':ch,'start':str(F(str(e['startTime']))*F(15,8)/F(str(vr['bpm']))),'end':str(F(str(e['endTime']))*F(15,8)/F(str(vr['bpm']))),'a':a,'b':b})
 cuts={F(0),F(str(m['audio_duration_seconds']))}
 for e in l['events']:
  cuts.update(t for t in [F(e['start']),F(e['end'])] if 0<=t<=F(str(m['audio_duration_seconds'])))
 cuts=sorted(cuts);samples=set(cuts)|{(a+b)/2 for a,b in zip(cuts,cuts[1:])}
 for t in samples:
  for ch in ['x','y','rotation','opacity','speed']:
   wanted=value(l,ch,t)
   for label,es in [('native',native_events),('official',official_events)]:
    got=value({'events':es},ch,t);error=abs(wanted-got);max_error=max(max_error,error)
    if error>1e-5:failures.append({'line':l['id'],'format':label,'channel':ch,'seconds':float(t),'wanted':wanted,'got':got})
report['export_event_equivalence']={'max_normalized_value_error':max_error,'failure_count':len(failures),'witnesses':failures[:20],'sampling':'all event boundaries and interval midpoints during audio duration; time conversion assumes verified single225BPM tempo'}
p.write_text(json.dumps(report,indent=2));print('Event equivalence',report['export_event_equivalence'])
