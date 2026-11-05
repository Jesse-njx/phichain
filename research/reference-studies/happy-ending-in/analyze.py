import json,math,hashlib,statistics,bisect,collections
from pathlib import Path
R=Path('/Users/jesse/Projects/PhiChain/research/reference-studies/happy-ending-in')
P=Path('/Users/jesse/Projects/PhiChain/phichain')
chart=json.loads((R/'IN.original.json').read_text())
overridepath=P/'../research/music-flow-study/override-in15/chart.json'
overridebytes=overridepath.read_bytes();override=json.loads(overridebytes)
def at(events,t):
 e=events[max(0,bisect.bisect_right([e['startTime'] for e in events],t)-1)]
 return e
notes=[]
for li,line in enumerate(chart['judgeLineList']):
 for side in ['notesAbove','notesBelow']:
  for n in line[side]:
   scale=60/32/line['bpm']; speed=at(line['speedEvents'],n['time'])['value']
   # Official hold speed is absolute scroll speed, unlike other note types.
   effective=n['speed'] if n['type']==3 else speed*n['speed']
   notes.append({'time':n['time']*scale+chart['offset'],'end':(n['time']+n['holdTime'])*scale+chart['offset'],'kind':{1:'tap',2:'drag',3:'hold',4:'flick'}[n['type']],'line':li,'line_speed':speed,'note_speed':n['speed'],'effective_official_speed_at_hit':effective,'phichain_equivalent':effective*4.5,'screen_heights_per_second':effective*.6})
def beat(b):return b[0]+b[1]/b[2]
ons=[]
for l in override['lines']:
 for n in l['notes']:
  k=n['kind'];kind=k if isinstance(k,str) else 'hold'
  hold=n.get('hold_beat',k.get('hold',{}).get('hold_beat',[0,0,1]) if isinstance(k,dict) else [0,0,1])
  ons.append({'time':beat(n['beat'])*60/204+.348,'end':(beat(n['beat'])+beat(hold))*60/204+.348,'kind':kind})
def percentile(a,p):
 a=sorted(a);i=(len(a)-1)*p;return a[int(i)]+(a[math.ceil(i)]-a[int(i)])*(i%1)
def peak(ts,width):
 ts=sorted(ts);best=(0,0)
 for i,t in enumerate(ts):
  j=bisect.bisect_left(ts,t+width-1e-8)
  if j-i>best[0]:best=(j-i,t)
 return {'count':best[0],'nps':best[0]/width,'from_seconds':best[1],'to_seconds':best[1]+width,'window':'[start,end)'}
def stats(ns):
 times=sorted(n['time'] for n in ns);groups=collections.Counter(round(t,6) for t in times);unique=sorted(groups);interval=[b-a for a,b in zip(unique,unique[1:])];first=min(times);last=max(n['end'] for n in ns)
 return {'notes':len(ns),'kinds':dict(collections.Counter(n['kind'] for n in ns)),'first_onset':first,'last_onset':max(times),'last_hold_end_or_onset':last,'active_span':last-first,'nps_active_span':len(ns)/(last-first),'nps_from_audio_zero_to_last_judgment':len(ns)/last,'unique_onset_groups':len(groups),'simultaneous_group_size_counts':dict(collections.Counter(groups.values())),'unique_onset_ioi_ms':{'p10':percentile(interval,.1)*1000,'median':statistics.median(interval)*1000,'p90':percentile(interval,.9)*1000,'minimum':min(interval)*1000},'sliding_peaks_all_notes':{str(w):peak(times,w) for w in [1,4,8]},'sliding_peaks_tap_hold_flick':{str(w):peak([n['time'] for n in ns if n['kind']!='drag'],w) for w in [1,4,8]},'windows_10s':[{'from':a,'to':a+10,'notes':sum(a<=n['time']<a+10 for n in ns),'nps':sum(a<=n['time']<a+10 for n in ns)/10,'kinds':dict(collections.Counter(n['kind'] for n in ns if a<=n['time']<a+10))} for a in range(0,math.ceil(last/10)*10,10)]}
ref=stats(notes);ours=stats(ons)
speeds=collections.Counter(round(n['effective_official_speed_at_hit'],6) for n in notes)
# Interval histogram in source ticks, showing 1/3-beat and 1/2-beat rhythms explicitly.
ts=sorted(set(round(n['time']*219*32/60) for n in notes))
ioi=collections.Counter(b-a for a,b in zip(ts,ts[1:]))
result={'reference':ref,'override_read_only':ours,'scroll':{'effective_official_speed_at_judgment_counts':dict(sorted(speeds.items())),'native_equivalent_formula':'official_speed * 9 / 2','usual_official':2.3,'usual_native':10.35,'override_native':4.6,'speed_ratio':10.35/4.6,'usual_screen_heights_per_second':1.38,'override_screen_heights_per_second':4.6*120/900,'stationary_half_screen_travel_seconds_reference':.5/1.38,'stationary_half_screen_travel_seconds_override':.5/(4.6*120/900),'warning':'Travel times are normalized stationary-line comparisons, NOT measured full visual lifetime. Moving/rotating lines and visibility events change exposure; 999, zero and reverse-speed events are effects, not ordinary reading speed.'},'source_tick_interval_counts':dict(ioi.most_common()),'source_tick_seconds':60/219/32,'override_sha256_before':hashlib.sha256(overridebytes).hexdigest(),'method':'Count each playable object once at its head. Holds are not repeated ticks. Simultaneous objects count separately in NPS; IOI deduplicates simultaneous judgment times. Half-open sliding windows. Source format v3 timestamps converted using each line BPM and offset. JSON-only study; no render-based style judgment.'}
(R/'metrics.json').write_text(json.dumps(result,indent=2))
(R/'notes-measured.json').write_text(json.dumps(notes,separators=(',',':')))
print(json.dumps({k:v for k,v in result.items() if k not in ['reference','override_read_only']},indent=2))
for name,s in [('REFERENCE',ref),('OVERRIDE',ours)]: print(name,json.dumps({k:v for k,v in s.items() if k!='windows_10s'},indent=2))
print('REFERENCE 10s',ref['windows_10s'])
assert hashlib.sha256(overridepath.read_bytes()).hexdigest()==result['override_sha256_before']
