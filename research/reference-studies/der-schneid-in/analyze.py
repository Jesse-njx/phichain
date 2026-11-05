"""Read-only source measurements for Der Schneid IN, with no arrangement edits."""
from pathlib import Path
from bisect import bisect_right
from collections import Counter
import json,math,statistics,hashlib
P=Path(__file__).resolve().parent;R=Path('/Users/jesse/Projects/PhiChain/phichain')
S=R/'../research/arrangement-training/raw/DerSchneid.Ωμεγα.0/IN.json'
c=json.loads(S.read_text());lines=c['judgeLineList'];spb=60/222
channels={'x':('judgeLineMoveEvents','start','end'),'y':('judgeLineMoveEvents','start2','end2'),'angle':('judgeLineRotateEvents','start','end'),'alpha':('judgeLineDisappearEvents','start','end'),'speed':('speedEvents','value','value')}
cache={}
for i,l in enumerate(lines):
 for k,(name,a,z) in channels.items():
  es=sorted(l[name],key=lambda e:e['startTime']);cache[i,k]=([e['startTime']/32 for e in es],es,a,z)
def val(i,k,b):
 ss,es,a,z=cache[i,k];e=es[max(0,bisect_right(ss,b)-1)];lo=e['startTime']/32;hi=e['endTime']/32
 t=max(0,min(1,(b-lo)/(hi-lo))) if hi>lo else 1
 return e[a]+(e[z]-e[a])*t

def pose(i,b):
 x=(val(i,'x',b)-.5)*1350;y=(val(i,'y',b)-.5)*900;angle=val(i,'angle',b);alpha=val(i,'alpha',b);r=math.radians(angle)
 intersects=abs(-math.sin(r)*x+math.cos(r)*y)<=abs(math.sin(r))*675+abs(math.cos(r))*450
 return dict(line=i,x=x,y=y,angle=angle,alpha=alpha,in_frame=intersects and alpha>.05)
notes=[]
for i,l in enumerate(lines):
 for side in ['notesAbove','notesBelow']:
  for n in l[side]:
   b=n['time']/32;p=pose(i,b);x=n['positionX']*75;r=math.radians(p['angle']);notes.append(dict(line=i,beat=b,seconds=b*spb,type=n['type'],duration=n['holdTime']/32,local_x=x,screen_x=p['x']+x*math.cos(r),screen_y=p['y']+x*math.sin(r),angle=p['angle'],alpha=p['alpha'],above=side=='notesAbove'))
notes.sort(key=lambda n:(n['beat'],n['line'],n['local_x']))
summary=[]
for lo in range(0,576,16):
 ns=[n for n in notes if lo<=n['beat']<lo+16];seen=Counter();pose_rows=[]
 for j in range(128):
  b=lo+j/8;ps=[pose(i,b) for i in range(len(lines))];ids=[p['line'] for p in ps if p['in_frame']];seen.update(ids)
 vis=[i for i,v in seen.items() if v>=16]
 summary.append(dict(beats=[lo,lo+16],seconds=[round(lo*spb,2),round((lo+16)*spb,2)],count=len(ns),types=dict(Counter(n['type'] for n in ns)),note_lines=dict(Counter(n['line'] for n in ns)),regularly_visible_lines=vis,main_mid_pose=pose(0,lo+8),head_y_range=[round(min(n['screen_y'] for n in ns),2),round(max(n['screen_y'] for n in ns),2)] if ns else None))
report=dict(source=str(S),source_sha256=hashlib.sha256(S.read_bytes()).hexdigest(),bpm=222,offset=c['offset'],notes=len(notes),types=dict(Counter(n['type'] for n in notes)),line_count=len(lines),first_last_beats=[notes[0]['beat'],notes[-1]['beat']],sections16=summary)
(P/'evidence.json').write_text(json.dumps(report,indent=2));(P/'judgment-heads.json').write_text(json.dumps(notes,indent=2))
for s in summary:
 p=s['main_mid_pose'];print(s['beats'],s['seconds'],'n',s['count'],'T/D/H/F',s['types'],'carriers',s['note_lines'],'vis',s['regularly_visible_lines'],'main',*[round(p[k],1) for k in ['x','y','angle','alpha']],'headsY',s['head_y_range'])
