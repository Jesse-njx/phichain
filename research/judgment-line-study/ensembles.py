"""Mine formations and simultaneous carrier relationships without modifying charts."""
from analyze import *

def main():
    records=json.loads((ROOT/'inventory.json').read_text())['charts'];out=[]
    for ci,rec in enumerate(records):
        d=json.loads(Path(rec['path']).read_text());ls=[Line(l,d['formatVersion']) for l in d['judgeLineList']];chords=collections.defaultdict(list)
        for li,l in enumerate(ls):
            for n in l.notes:chords[round(n['t'],4)].append((li,n))
            ns=[n for n in l.notes if n['type']!=3]
            if len(ns)<6:continue
            for start in np.arange(0,ns[-1]['t'],2):
                group=[n for n in ns if start<=n['t']<start+3]
                if len(group)<6:continue
                ts=np.array([n['t'] for n in group]);local=np.array([n['positionX'] for n in group]);pose=l.pose(ts)
                a=np.deg2rad(pose[2]);hx=pose[0]+local/18*np.cos(a);hy=pose[1]+local/18*16/9*np.sin(a)
                f=features(ts,pose);tags=[]
                if max(extent(hx),extent(hy))>.2 and extent(local)<.15:tags.append('travelling-hit-station')
                if max(extent(hx),extent(hy))<.055 and extent(local)>.5 and (max(f['x_span'],f['y_span'])>.15 or f['rotation_span']>25):tags.append('compensated-landing')
                if max(extent(hx),extent(hy))<.055 and np.max(np.abs(local))<.2 and f['rotation_span']>25:tags.append('pivot-locked-landing')
                stable=max(f['x_span'],f['y_span'])<.02 and f['rotation_span']<3
                unique=np.unique(ts,return_index=True)[1];unique.sort();tt=ts[unique];xx=local[unique]
                if stable and len(unique)>=6 and extent(xx)>3:
                    rv=reversals(xx,.12);speed=np.array([n['speed'] for n in group]);
                    if rv>=3:tags.append('zigzag-note-formation')
                    elif rv==1:tags.append('arched-note-formation')
                    if extent(speed)>.5:tags.append('speed-fanned-formation')
                if tags:
                    f.update(landing_span=[extent(hx),extent(hy)],local_x_span=extent(local),ensemble_count=len(group))
                    out.append(dict(chart=rec['id'],category='note',lines=[li],start=max(0,float(ts[0])-.8),end=float(ts[-1]),tags=tags,score=min(len(group),30)/6+f['rotation_span']/90+max(f['x_span'],f['y_span']),features=f,whole_line_empty=False,ensemble=[dict(line=li,side=n['side'],index=n['index']) for n in group]))
        for t,group in chords.items():
            if len(group)<2 or t<.3:continue
            # Maximum eight objects keeps formation mining from turning drag walls into an O(n^2) task.
            if len(group)>8:continue
            for ii,(li,n) in enumerate(group):
                if n['type']==3:continue
                for lj,m in group[ii+1:]:
                    if li==lj or m['type']==3:continue
                    ts=np.linspace(max(0,t-.5),t,31);p=ls[li].pose(ts);q=ls[lj].pose(ts)
                    x,y,dd=ls[li].path(n,ts);u,v,ee=ls[lj].path(m,ts)
                    valid=(x>=0)&(x<=1)&(y>=0)&(y<=1)&(u>=0)&(u<=1)&(v>=0)&(v<=1)&(dd*(1 if n['side']=='notesAbove' else -1)>=-1e-6)&(ee*(1 if m['side']=='notesAbove' else -1)>=-1e-6)
                    if np.sum(valid)<12 or not valid[-1]:continue
                    ids=np.where(valid)[0];k=int(ids[0]);dx=(x[-1]-x[k])*16/9;dy=y[-1]-y[k];du=(u[-1]-u[k])*16/9;dv=v[-1]-v[k]
                    len1=math.hypot(dx,dy);len2=math.hypot(du,dv)
                    if min(len1,len2)<.1:continue
                    cosine=(dx*du+dy*dv)/(len1*len2);landing=math.hypot((x[-1]-u[-1])*16/9,y[-1]-v[-1]);initial=math.hypot((x[k]-u[k])*16/9,y[k]-v[k]);tags=[]
                    if cosine<-.5:tags.append('opposed-approach-chord')
                    if abs(cosine)<.25:tags.append('orthogonal-approach-chord')
                    if landing<.06 and initial>.2:tags.append('converging-to-one-station')
                    if initial<.12 and landing>.25:tags.append('splitting-from-one-region')
                    if cosine>.9 and abs(len1-len2)>.25:tags.append('differential-speed-chord')
                    if (np.max(p[3])<=.01 and np.min(q[3])>.5) or (np.max(q[3])<=.01 and np.min(p[3])>.5):tags.append('visible-anchor-hidden-partner')
                    if not tags:continue
                    f=features(ts[k:],tuple(a[k:] for a in p));f.update(approach_cosine=cosine,landing_separation=landing,initial_separation=initial,partner=features(ts[k:],tuple(a[k:] for a in q)))
                    out.append(dict(chart=rec['id'],category='note',lines=[li,lj],start=float(ts[k]),end=float(ts[-1]),tags=tags,score=3*(1-cosine)+abs(initial-landing)*3,features=f,whole_line_empty=False,ensemble=[dict(line=li,side=n['side'],index=n['index']),dict(line=lj,side=m['side'],index=m['index'])]))
        if ci%60==0:print(ci+1,rec['title'],len(out),flush=True)
    buckets=collections.defaultdict(list)
    for c in out:
        for tag in c['tags']:buckets[tag].append(c)
    selected=[];seen=set();counts={}
    for tag,cs in buckets.items():
        counts[tag]={'candidates':len(cs),'charts':len(set(c['chart'] for c in cs))};per=collections.Counter();kept=[]
        for c in sorted(cs,key=lambda c:c['score'],reverse=True):
            if per[c['chart']]>=4:continue
            if any(k['chart']==c['chart'] and k['lines']==c['lines'] and abs(k['start']-c['start'])<5 for k in kept):continue
            kept.append(c);per[c['chart']]+=1;ident=(c['chart'],tuple(c['lines']),c['start'],c['end'])
            if ident not in seen:selected.append(c);seen.add(ident)
            if len(kept)>=100:break
    dump('ensemble-candidates.json',selected);dump('ensemble-counts.json',counts);print('Done',len(out),len(selected))

if __name__=='__main__':main()
