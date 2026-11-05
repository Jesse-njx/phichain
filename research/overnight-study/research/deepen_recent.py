"""Additional recent-source study, strict MCP native conversion without repairs."""
from pathlib import Path
from fractions import Fraction as F
import json,math,hashlib,sys,time
from collections import Counter
from phigros_chart_mcp.core import Engine
ROOT=Path('/Users/jesse/Projects/PhiChain/phichain'); BASE=ROOT/'../research/overnight-study'; OUT=BASE/'research/deep-recent';OUT.mkdir(exist_ok=True)
manifest=json.loads((BASE/'corpus/manifest.json').read_text())
excluded={('BoundedQuietude.FiniteLimitvsSiLiS','IN'),('PRAGMATISMRESURRECTION.Laur','IN'),('AbsoluTedisoRdeR.AcuteDisarray','AT'),('QZKagoRequiem.tpazolite','AT'),('RetributionCycleofRedemption.ArdolfvsDaily天利','IN'),('Verruckt.Raimukun','IN'),('玩具狂奏曲終焉.きくお','AT'),('DerSchneid.Ωμεγα','AT')}
rows=[]
for idx,r in enumerate(manifest):
 if not r['recent_three_years'] or (r['id'],r['difficulty']) in excluded:continue
 folder=OUT/f'{idx:02}-{r["difficulty"]}';folder.mkdir(exist_ok=True)
 source=json.loads((ROOT/r['chart']['path']).read_text());notes=[];events=[]
 for li,l in enumerate(source['judgeLineList']):
  factor=1.875/l['bpm']; count=sum(len(l[k]) for k in ['notesAbove','notesBelow'])
  for side in ['notesAbove','notesBelow']:
   for n in l[side]:notes.append(dict(line=li,kind={1:'tap',2:'drag',3:'hold',4:'flick'}[n['type']],seconds=n['time']*factor,end_seconds=(n['time']+n['holdTime'])*factor,x=n['positionX'],side=side,speed=n['speed']))
  for channel in ['judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents']:
   for e in l[channel]:
    a,b=e['startTime']*factor,e['endTime']*factor
    delta=abs(e['end']-e['start'])/(180 if channel=='judgeLineRotateEvents' else 1)
    if channel=='judgeLineMoveEvents':delta+=abs(e['end2']-e['start2'])
    if 0<=a<b and delta>.03:events.append(dict(line=li,channel=channel,start=a,end=b,delta=delta,note_bearing=count>0))
 duration=max(n['end_seconds'] for n in notes);notes.sort(key=lambda n:n['seconds'])
 candidates=[]
 for start in range(4,max(5,int(duration)-12),4):
  ns=[n for n in notes if start<=n['seconds']<start+12];held=sum(min(start+12,n['end_seconds'])-max(start,n['seconds']) for n in notes if n['kind']=='hold' and n['end_seconds']>start and n['seconds']<start+12)
  score=len(ns)+held*8+len(set(n['kind'] for n in ns))*6
  candidates.append((score,start))
 arrangement=max(candidates)[1]
 # Meaningful motion: largest aggregate change over a 4s neighborhood, not arbitrary percentage.
 motion=[]
 for e in events:
  if e['start']>duration-2:continue
  center=(e['start']+min(e['end'],e['start']+6))/2
  s=max(0,min(duration-12,center-4));score=sum(x['delta']*(2 if x['note_bearing'] else 1) for x in events if s<=x['start']<s+8)
  motion.append((score,s))
 visual=max(motion)[1] if motion else max(0,duration/2-6)
 windows=[dict(role='arrangement',start=round(arrangement,3),end=round(min(duration,arrangement+12),3)),dict(role='visual-transition',start=round(visual,3),end=round(min(duration,visual+12),3))]
 rec=dict(id=r['id'],title=r['title'],difficulty=r['difficulty'],constant=r['constant'],date=r['latest_creation_or_rechart_date'],source_sha256=r['chart']['sha256'],source_url=r['chart']['url'],level_source=r['level_source'],date_source=r['date_source'],offset=source['offset'],folder=str(folder),windows=windows,native_status='pending')
 for w in windows:
  ns=[n for n in notes if w['start']<=n['seconds']<w['end']]; w['types']=dict(Counter(n['kind'] for n in ns));w['heads']=len(ns);w['note_bearing_lines']=sorted(set(n['line'] for n in ns));w['decoded_sample']=ns[:24];w['movement_events']=[e for e in events if e['start']<w['end'] and e['end']>w['start']][:24]
 (folder/'notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2))
 try:
  engine=Engine();c=engine.chart_import(str(ROOT/r['chart']['path']));native=engine.chart_export(c['chart_ref'],c['digest'],format='phichain_native')['chart'];(folder/'chart.json').write_text(json.dumps(native,ensure_ascii=False,separators=(',',':')))
  (folder/'music.ogg').symlink_to(ROOT/r['music']['path']) if not (folder/'music.ogg').exists() else None
  (folder/'meta.json').write_text(json.dumps(dict(name=r['title'],composer=r['composer'],charter=r['charter'],illustrator='Neutral black study background',level=f'{r["difficulty"]} {r["constant"]}'),ensure_ascii=False))
  rec['native_status']='exported_without_source_repair';rec['native_sha256']=hashlib.sha256((folder/'chart.json').read_bytes()).hexdigest()
 except ValueError as err:rec['native_status']='explicit_compatibility_refusal';rec['native_error']=str(err)
 rows.append(rec);(OUT/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(r['title'],r['difficulty'],rec['native_status'],flush=True)
print('Total',len(rows))
