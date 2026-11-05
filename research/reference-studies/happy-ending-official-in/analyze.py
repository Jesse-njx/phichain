"""Read-only original-IN geometry and same-song comparison with rejected drafts."""
from pathlib import Path
from bisect import bisect_right
from collections import Counter
import json,math,hashlib
P=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
prov=json.loads((P/'provenance.json').read_text());source=Path(prov['source'])
c=json.loads(source.read_text());lines=c['judgeLineList'];SPB=60/219
channels={'x':('judgeLineMoveEvents','start','end'),'y':('judgeLineMoveEvents','start2','end2'),
          'angle':('judgeLineRotateEvents','start','end'),'alpha':('judgeLineDisappearEvents','start','end'),
          'speed':('speedEvents','value','value')}
cache={}
for i,l in enumerate(lines):
    assert l['bpm']==219
    for k,(name,a,z) in channels.items():
        events=sorted(l[name],key=lambda e:e['startTime'])
        cache[i,k]=([e['startTime']/32 for e in events],events,a,z)
def value(i,k,b):
    ss,es,a,z=cache[i,k];e=es[max(0,bisect_right(ss,b)-1)];lo=e['startTime']/32;hi=e['endTime']/32
    u=max(0,min(1,(b-lo)/(hi-lo))) if hi>lo else 1
    return e[a]+(e[z]-e[a])*u
def pose(i,b):
    return {'x':(value(i,'x',b)-.5)*1350,'y':(value(i,'y',b)-.5)*900,
        'angle':value(i,'angle',b),'alpha':value(i,'alpha',b),'speed':value(i,'speed',b)}
types={1:'tap',2:'drag',3:'hold',4:'flick'};notes=[]
for i,l in enumerate(lines):
    for field in ('notesAbove','notesBelow'):
        for index,n in enumerate(l[field]):
            b=n['time']/32;p=pose(i,b);r=math.radians(p['angle']);x=n['positionX']*75
            sx=p['x']+x*math.cos(r);sy=p['y']+x*math.sin(r)
            notes.append({'id':f'{i}-{field}-{index}','line':i,'beat':b,'seconds':b*SPB,'kind':types[n['type']],
                'duration':n['holdTime']/32,'x':x,'screen_x':sx,'screen_y':sy,
                'alpha':p['alpha'],'angle':p['angle'],'speed':n['speed'],'line_speed':p['speed'],
                'above':field=='notesAbove','on_screen_at_judgment':abs(sx)<=675 and abs(sy)<=450,'on_visible_receiver_at_judgment':p['alpha']>.01 and abs(sx)<=675 and abs(sy)<=450})
notes.sort(key=lambda n:(n['beat'],n['line'],n['x']))
def stats(rows):
    beats=Counter(n['beat'] for n in rows)
    return {'notes':len(rows),'types':dict(Counter(n['kind'] for n in rows)),
       'onset_groups':len(beats),'simultaneous_groups':sum(v>1 for v in beats.values()),
       'hold_beats_total':sum(n['duration'] for n in rows if n['kind']=='hold')}
drafts={}
for key in 'ABCDE':
    p=ROOT/'../charts/happy-ending/happy-ending-five-authors'/key/'proposal/proposal.json';d=json.loads(p.read_text())
    drafts[key]=d
summary=[]
for lo,hi in [(0,48),(48,72),(72,104),(104,112),(112,128),(128,168),(168,184),(184,208),(208,224),(224,248),(248,256),(256,288),(288,320),(320,348),(348,368),(368,384),(384,416),(416,464),(464,480),(480,512),(512,552),(552,560),(560,584)]:
    ns=[n for n in notes if lo<=n['beat']<hi];visible=[n for n in ns if n['on_screen_at_judgment']]
    row={'beats':[lo,hi],'seconds':[round(lo*SPB,3),round(hi*SPB,3)],'official':stats(ns),
      'on_screen_judgment_heads':len(visible),'receiver_note_counts':dict(Counter(n['line'] for n in visible)),
      'official_judgment_y_range':[round(min(n['screen_y'] for n in visible),1),round(max(n['screen_y'] for n in visible),1)] if visible else None,
      'drafts':{key:stats([n for n in d['actions'] if lo<=n['beat']<hi]) for key,d in drafts.items()}}
    summary.append(row)
    print(row['beats'],'official',row['official']['types'],'lines',row['receiver_note_counts'],'y',row['official_judgment_y_range'],'E',row['drafts']['E']['types'])
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'official':stats(notes),
  'on_screen_judgment_heads':stats([n for n in notes if n['on_screen_at_judgment']]),
  'official_lines':len(lines),'drafts':{k:stats(d['actions']) for k,d in drafts.items()},'sections':summary,
  'limits':'Line alpha affects the line sprite, not note visibility. Source geometry at judgment is not full visible-lifetime, contact-tolerance or human-fingering validation. Official segmented linear events are sampled as authored. All official line clocks are219BPM.'}
(P/'evidence.json').write_text(json.dumps(report,indent=2))
(P/'judgment-heads.json').write_text(json.dumps(notes,indent=2))
assert report['source_sha256']==prov['source_sha256']
