"""Read-only source geometry and Tap-density analysis; no authored chart edits."""
from pathlib import Path
import json,bisect,math,collections,statistics
P=Path(__file__).parent
def ev(es,t,a='start',b='end',default=0):
    i=bisect.bisect_right([e['startTime'] for e in es],t)-1
    if i<0:return default
    e=es[i];u=max(0,min(1,(t-e['startTime'])/(e['endTime']-e['startTime']))) if e['endTime']!=e['startTime'] else 1
    return e.get(a,default)*(1-u)+e.get(b,default)*u
def flatten(d):
    ns=[]
    for li,l in enumerate(d['judgeLineList']):
        for k in ['judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents']:
            l[k].sort(key=lambda e:e['startTime'])
        for side in ['notesAbove','notesBelow']:
            for ix,n in enumerate(l.get(side,[])):
                t=n['time'];f=1.875/l['bpm'];cx=ev(l['judgeLineMoveEvents'],t,default=.5);cy=ev(l['judgeLineMoveEvents'],t,'start2','end2',.5)
                if d['formatVersion']==1:cx,cy=round(cx/1000)/880,(cx%1000)/530
                rot=ev(l['judgeLineRotateEvents'],t);r=math.radians(rot);x=n['positionX']*75
                ns.append(dict(t=t*f+d.get('offset',0),end=(t+n.get('holdTime',0))*f+d.get('offset',0),kind=n['type'],x=(cx-.5)*1350+x*math.cos(r),y=(cy-.5)*900+x*math.sin(r),local_x=x,line=li,side=side,source_tick=t,source_index=ix,rotation=rot,opacity=ev(l['judgeLineDisappearEvents'],t),bpm=l['bpm']))
    return sorted(ns,key=lambda n:(n['t'],n['line'],n['source_index']))
def groups(ns):
    out=[]
    for n in ns:
        if not out or n['t']-out[-1][0]['t']>.00015:out.append([n])
        else:out[-1].append(n)
    return out
def stats(ns,start,end):
    heads=[n for n in ns if start<=n['t']<end];tap=[n for n in heads if n['kind']==1];gs=groups(tap)
    return dict(start=round(start,6),end=round(end,6),tap_count=len(tap),tap_nps=len(tap)/(end-start),tap_onsets=len(gs),tap_multiplicity=dict(collections.Counter(len(g) for g in gs)),all_kinds=dict(collections.Counter(n['kind'] for n in heads)),tap_x_span=[round(min((n['x'] for n in tap),default=0),1),round(max((n['x'] for n in tap),default=0),1)],tap_y_span=[round(min((n['y'] for n in tap),default=0),1),round(max((n['y'] for n in tap),default=0),1)],tap_rotation_span=[round(min((n['rotation'] for n in tap),default=0),1),round(max((n['rotation'] for n in tap),default=0),1)])
reports=[]
for m in json.loads((P/'manifest.json').read_text()):
    d=json.loads(Path(m['path']).read_text());ns=flatten(d);(P/m['key']/'notes.json').write_text(json.dumps(ns,indent=2))
    taps=[n for n in ns if n['kind']==1];times=[n['t'] for n in taps]
    choices=sorted([(bisect.bisect_left(times,n['t']+8)-i,n['t']) for i,n in enumerate(taps)],reverse=True)
    windows=[]
    for count,t in choices:
        if any(abs(t-w['start'])<8 for w in windows):continue
        windows.append(stats(ns,t,t+8))
        if len(windows)==4:break
    report={**m,'note_count':len(ns),'kind_counts':dict(collections.Counter(n['kind'] for n in ns)),'dense_windows':windows}
    reports.append(report)
    print(m['key'],report['kind_counts'])
    for w in windows: print(' ',w)
(P/'analysis.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False))
