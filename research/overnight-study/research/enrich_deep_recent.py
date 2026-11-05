"""Decoded exact passages, geometric witnesses and cached audio evidence."""
import json,math,bisect,statistics
from pathlib import Path
BASE=Path('/Users/jesse/Projects/PhiChain/research/overnight-study');out=BASE/'research/deep-recent';rows=json.loads((out/'manifest.json').read_text());manifest=json.loads((BASE/'corpus/manifest.json').read_text())
def ev(events,t,a='start',b='end',default=0):
 result=default
 for e in sorted(events,key=lambda e:e['startTime']):
  if e['startTime']>t:break
  if e['startTime']<=t<e['endTime']:
   return e[a]+(e[b]-e[a])*(t-e['startTime'])/(e['endTime']-e['startTime'])
  if e['endTime']<=t:result=e[b]
 return result
for r in rows:
 src=next(x for x in manifest if x['id']==r['id'] and x['difficulty']==r['difficulty']);chart=json.loads((Path('/Users/jesse/Projects/PhiChain/phichain')/src['chart']['path']).read_text());notes=json.loads((Path(r['folder'])/'notes.json').read_text());audio=json.loads((BASE/'research/audio'/f'{r["id"]}.json').read_text());peaks=audio['onset_peak_seconds']
 def decode(n,at=None):
  n=dict(n);line=chart['judgeLineList'][n['line']];t=(n['seconds'] if at is None else at)/1.875*line['bpm'];angle=math.radians(ev(line['judgeLineRotateEvents'],t));lx=ev(line['judgeLineMoveEvents'],t)-.5;ly=ev(line['judgeLineMoveEvents'],t,'start2','end2')-.5
  n['line_local_normalized_x']=n['x']/18;n['world_contact_normalized']=[lx+n['x']/18*math.cos(angle),ly+n['x']/18*1.5*math.sin(angle)];n['line_opacity_at_head']=ev(line['judgeLineDisappearEvents'],t,default=1);n['duration_seconds']=n['end_seconds']-n['seconds'];n['audio_seconds']=n['seconds']+r['offset'];return n
 for w in r['windows']:
  ns=[n for n in notes if w['start']<=n['seconds']<w['end']];w['decoded_sample']=[decode(n) for n in ns[:24]]
  fresh=sorted(set(n['seconds']+r['offset'] for n in ns if n['kind']=='tap'));near=[]
  for t in fresh:
   k=bisect.bisect_left(peaks,t);near.append(min(abs(t-peaks[j]) for j in [k-1,k] if 0<=j<len(peaks))*1000)
  w['audio_crosscheck']={'distinct_tap_times':len(fresh),'median_nearest_flux_peak_ms':statistics.median(near) if near else None,'p90_nearest_flux_peak_ms':sorted(near)[int(.9*(len(near)-1))] if near else None,'overlapping_8second_energy_bins':[s for s in audio['sections'] if s['start']<w['end']+r['offset'] and s['end']>w['start']+r['offset']]}
  holdanswers=[]
  for n in ns:
   if n['kind']!='tap':continue
   held=[h for h in notes if h['kind']=='hold' and h['seconds']<n['seconds']<h['end_seconds']]
   if held:holdanswers.append({'answer':decode(n),'active_hold_heads': [decode(h) for h in held], 'active_hold_positions_at_answer':[{'line':h['line'],'x':h['x'],'world_contact_normalized':decode(h,n['seconds'])['world_contact_normalized'],'opacity':decode(h,n['seconds'])['line_opacity_at_head']} for h in held]})
  w['sustain_answer_witnesses']=sorted(holdanswers,key=lambda h:len(h['active_hold_heads']),reverse=True)[:2]
  # Find head-free phrase gaps; held ownership is separate.
  ts=sorted(set(n['seconds'] for n in ns));gaps=[]
  for a,b in zip(ts,ts[1:]):
   if b-a>=.7:gaps.append({'start':a,'end':b,'seconds':b-a,'active_hold_overlap':sum(h['seconds']<b and h['end_seconds']>a for h in notes if h['kind']=='hold')})
  w['head_free_gaps']=gaps
 (Path(r['folder'])/'case-data.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
(out/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print('Enriched',len(rows))
