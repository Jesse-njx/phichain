"""Read-only source-chart research. Writes evidence only inside this study directory."""
from pathlib import Path
import bisect, collections, hashlib, json, math
import numpy as np

ROOT = Path(__file__).resolve().parent
CHANNELS = {'move':'judgeLineMoveEvents','rotate':'judgeLineRotateEvents','alpha':'judgeLineDisappearEvents','speed':'speedEvents'}

def dump(name, value):
    (ROOT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

class Line:
    def __init__(self, raw, version=3):
        self.raw=raw; self.fac=1.875/raw['bpm']; self.events={}; self.starts={}; self.arrays={}
        for key,field in CHANNELS.items():
            es=[dict(e) for e in raw.get(field,[])]; es.sort(key=lambda e:e['startTime'])
            if key=='move' and version==1:
                for e in es:
                    for k in ['start','end']:
                        v=e[k];e[k+'2']=(v%1000)/530;e[k]=math.floor(v/1000+.5)/880
            self.events[key]=es;self.starts[key]=np.array([e['startTime']*self.fac for e in es])
            self.arrays[key]={k:np.array([e.get(k,0) for e in es]) for k in ['start','end','start2','end2','value','floorPosition']}
            self.arrays[key]['end_seconds']=np.array([e['endTime']*self.fac for e in es])
        # Many original extractions omit speed-event floorPosition. Reconstruct the integral.
        es=self.events['speed']; cumulative=[];area=0.;last_time=0.;last_speed=0.
        for e in es:
            begin=e['startTime']*self.fac;end=e['endTime']*self.fac
            if begin>last_time:area+=(begin-last_time)*last_speed
            cumulative.append(area)
            area+=max(0,end-max(0,begin))*e['value'];last_time=end;last_speed=e['value']
        self.arrays['speed']['integrated_floor']=np.array(cumulative)
        self.notes=[]
        for side in ['notesAbove','notesBelow']:
            for i,n in enumerate(raw.get(side,[])):
                self.notes.append(dict(n, side=side, index=i, t=n['time']*self.fac, end=(n['time']+n['holdTime'])*self.fac))
        self.notes.sort(key=lambda n:n['t'])

    def values(self,key,ts,second=False):
        ts=np.asarray(ts,dtype=float);es=self.events[key]
        if not es:return np.zeros_like(ts)
        idx=np.clip(np.searchsorted(self.starts[key],ts,side='right')-1,0,len(es)-1)
        arr=self.arrays[key]
        if key=='speed':return arr['value'][idx]
        a=arr['start2' if second else 'start'];b=arr['end2' if second else 'end'];end=arr['end_seconds']
        dur=end[idx]-self.starts[key][idx];f=np.divide(ts-self.starts[key][idx],dur,out=np.ones_like(ts),where=dur!=0)
        return a[idx]+(b[idx]-a[idx])*np.clip(f,0,1)

    def floor(self,ts):
        ts=np.asarray(ts,dtype=float);es=self.events['speed']
        if not es:return np.zeros_like(ts)
        idx=np.clip(np.searchsorted(self.starts['speed'],ts,side='right')-1,0,len(es)-1)
        return self.arrays['speed']['integrated_floor'][idx]+(ts-self.starts['speed'][idx])*self.arrays['speed']['value'][idx]

    def pose(self,ts):
        return self.values('move',ts),self.values('move',ts,True),self.values('rotate',ts),self.values('alpha',ts),self.values('speed',ts)

    def path(self,n,ts):
        x,y,r,alpha,speed=self.pose(ts);a=np.deg2rad(r)
        # Reintegrating at the note time avoids accumulated f32 export error at judgment.
        # Stored note floors are audited separately, never silently assumed to be exact.
        d=(float(self.floor([n['t']])[0])-self.floor(ts))*.6*(1 if n['type']==3 else n['speed'])
        if n['type']==3:d=np.maximum(d,0)
        d*=1 if n['side']=='notesAbove' else -1
        # Normalized screen, y up, 16:9. /18 agrees with PhiChain's official importer.
        nx=x+n['positionX']/18*np.cos(a)-d*(9/16)*np.sin(a)
        ny=y+n['positionX']/18*(16/9)*np.sin(a)+d*np.cos(a)
        return nx,ny,d

def extent(x):return float(np.ptp(x))
def reversals(x,eps):
    dx=np.diff(x); signs=np.sign(dx[np.abs(dx)>eps]);return int(np.sum(signs[1:]!=signs[:-1])) if len(signs)>1 else 0
def line_visible(x,y,r):
    # Infinite centreline intersects 16:9 viewport, independent of offscreen pivot.
    a=np.deg2rad(r);distance=np.abs((x-.5)*(16/9)*np.sin(a)-(y-.5)*np.cos(a))
    reach=.5*(16/9)*np.abs(np.sin(a))+.5*np.abs(np.cos(a))
    return distance<=reach+.005

def features(ts,pose):
    x,y,r,a,v=pose
    normal_offset=-(x-.5)*(16/9)*np.sin(np.deg2rad(r))+(y-.5)*np.cos(np.deg2rad(r))
    return dict(x_span=extent(x),y_span=extent(y),rotation_span=extent(r),rotation_delta=float(r[-1]-r[0]),
        normal_offset_span=extent(normal_offset),
        x_delta=float(x[-1]-x[0]),y_delta=float(y[-1]-y[0]),x_reversals=reversals(x,.001),y_reversals=reversals(y,.001),rotation_reversals=reversals(r,.5),
        alpha_span=extent(a),alpha_min=float(np.min(a)),alpha_max=float(np.max(a)),alpha_delta=float(a[-1]-a[0]),
        alpha_edges=int(np.sum((a[1:]>.1)!=(a[:-1]>.1))),speed_min=float(np.min(v)),speed_max=float(np.max(v)),
        speed_delta=float(v[-1]-v[0]),speed_changes=int(np.sum(np.abs(np.diff(v))>.05)),
        zero_speed_samples=int(np.sum(np.abs(v)<.01)),negative_speed_samples=int(np.sum(v<-.01)),
        visible_fraction=float(np.mean((a>.05)&line_visible(x,y,r))),duration=float(ts[-1]-ts[0]),
        mean_angle=float(np.mean(r)),origin_start=[float(x[0]),float(y[0])],origin_end=[float(x[-1]),float(y[-1])])

def note_tags(f,n,nx,ny,pose,ts):
    tags=[];x,y,r,a,v=pose;rot=f['rotation_span'];move=max(f['x_span'],f['y_span']);dt=f['duration'];kind=n['type']
    # A recipe can match several mechanisms; selection chooses one principal label.
    if kind!=3:
        netx=float(nx[-1]-nx[0]);nety=float(ny[-1]-ny[0]);angle=abs(math.degrees(math.atan2(nety,netx)))
        stable=rot<5 and move<.025
        if stable and abs(netx)>.15 and abs(nety)<.07:tags.append('side-entry')
        if stable and abs(netx)>.10 and abs(nety)>.10:tags.append('diagonal-entry')
        if stable and nety>.18 and abs(netx)<.05:tags.append('rising-entry')
        if 20<rot<100 and f['rotation_reversals']==0:tags.append('turning-approach')
        if 100<=rot<250 and f['rotation_reversals']==0:tags.append('half-turn-hook')
        if rot>=250:tags.append('spinning-approach')
        if rot>15 and f['rotation_reversals']>=2:tags.append('pendulum-approach')
        if f['x_span']>.12 and rot<8:tags.append('lateral-carriage')
        if f['y_span']>.15 and rot<8:tags.append('elevator-approach')
        if f['x_span']>.12 and f['y_span']>.12 and rot<8:tags.append('diagonal-carriage')
        if f['x_reversals']>=2 and f['x_span']>.08:tags.append('serpentine-carriage')
        if rot>20 and move>.10:tags.append('moving-pivot-hook')
        if f['zero_speed_samples']>=3 and f['speed_max']>.4:tags.append('stop-and-release')
        if f['negative_speed_samples']>=2 and f['speed_max']>.2:tags.append('reverse-scroll')
        if f['speed_delta']>.8 and f['speed_min']>.05:tags.append('speed-up-entry')
        if f['speed_delta']<-.8 and f['speed_min']>.05:tags.append('braking-entry')
        if f['speed_changes']>=4 and f['speed_max']-f['speed_min']>.8:tags.append('stepped-scroll')
        if f['speed_max']>5 and f['duration']<.5:tags.append('late-fast-entry')
        if f['alpha_max']<=.01 and (move>.06 or rot>10 or stable and abs(netx)>.15):tags.append('invisible-carrier')
        if f['alpha_min']<=.01 and f['alpha_max']>.5 and (rot>10 or move>.06):tags.append('carrier-reveal')
        if n['side']=='notesBelow' and (rot>10 or move>.06):tags.append('below-side-transform')
        if extent(nx)>.15 and reversals(nx,.002)>=2:tags.append('screen-space-foldback')
        if len(ts)>12 and move>.12:
            tail=max(extent(x[-5:]),extent(y[-5:]));early=max(extent(x[:-5]),extent(y[:-5]))
            if tail<.008 and early>.12:tags.append('settle-before-hit')
    else:
        if move>.12 and rot<12:tags.append('transported-hold')
        if rot>25 and move<.08:tags.append('pivoted-hold')
        if rot>25 and move>.08:tags.append('orbiting-hold')
        if f['alpha_max']<=.01 and (move>.08 or rot>15):tags.append('invisible-hold-guide')
    return tags

def background_tags(f):
    tags=[];rot=f['rotation_span'];move=max(f['x_span'],f['y_span'])
    if f['visible_fraction']<.15:return []
    if rot<6 and f['normal_offset_span']<.04 and f['alpha_span']<.25:return []
    if f['x_span']>.12 and f['y_span']<.04 and rot<6:tags.append('horizontal-sweep')
    if f['y_span']>.12 and f['x_span']<.04 and rot<6:tags.append('vertical-sweep')
    if f['x_span']>.1 and f['y_span']>.1 and rot<6:tags.append('diagonal-sweep')
    if rot>20 and move<.035:tags.append('fixed-pivot-rotation')
    if rot>20 and move>.10:tags.append('travelling-blade')
    if f['x_reversals']>=2 and f['x_span']>.08:tags.append('lateral-shuttle')
    if f['y_reversals']>=2 and f['y_span']>.08:tags.append('vertical-bounce')
    if f['rotation_reversals']>=2 and rot>12:tags.append('rocking-line')
    if rot>330 and f['rotation_reversals']<=1:tags.append('windmill')
    if f['alpha_delta']>.6 and (move>.05 or rot>10):tags.append('fade-in-motion')
    if f['alpha_delta']<-.6 and (move>.05 or rot>10):tags.append('fade-out-motion')
    if f['alpha_edges']>=4:tags.append('strobe-line')
    elif f['alpha_edges']>=2:tags.append('single-flash')
    if f['alpha_span']>.3 and f['alpha_min']>.02:tags.append('breathing-line')
    if (max(abs(v) for v in f['origin_start']+f['origin_end'])>1.2) and move>.2:tags.append('offscreen-pivot-wipe')
    return tags

def scan():
    inventory=json.loads((ROOT/'inventory.json').read_text());records=inventory['charts'];candidates=[];summary=[];audit=[]
    for ci,rec in enumerate(records):
        raw=Path(rec['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==rec['sha256'],rec['path']
        d=json.loads(raw);lines=[Line(l,d['formatVersion']) for l in d['judgeLineList']]
        last=max([n['end'] for l in lines for n in l.notes]+[0]);stat=collections.Counter();stat['lines']=len(lines);stat['empty_lines']=sum(not l.notes for l in lines)
        stat['notes']=sum(len(l.notes) for l in lines);stat['events']=sum(sum(len(es) for es in l.events.values()) for l in lines)
        stat['bpm_variants']=len(set(l.raw['bpm'] for l in lines));stat['last_note_seconds']=last
        # Raw channel continuity audit; these are warnings, not source repairs.
        issues=[]
        for li,l in enumerate(lines):
            if l.notes:
                head_times=np.array([n['t'] for n in l.notes]);hp=l.pose(head_times)
                residual=np.abs(l.floor(head_times)-np.array([n['floorPosition'] for n in l.notes]))
                stat['note_floor_residual_over_001']+=int(np.sum(residual>.01))
                stat['max_note_floor_residual']=max(stat['max_note_floor_residual'],float(np.max(residual)))
                stat['hidden_at_judgment']+=int(np.sum(hp[3]<=.01))
                stat['below_side_notes']+=sum(n['side']=='notesBelow' for n in l.notes)
                stat['notes_on_negative_speed_at_head']+=int(np.sum(hp[4]<0))
                stat['notes_on_zero_speed_at_head']+=int(np.sum(hp[4]==0))
            for k,es in l.events.items():
                bad=sum(e['endTime']<e['startTime'] for e in es)
                overlaps=sum(e['startTime']<es[i-1]['endTime']-1e-6 for i,e in enumerate(es) if i)
                if bad or overlaps:issues.append([li,k,bad,overlaps])
            stat['lines_with_negative_speed']+=any(e['value']<0 and e['startTime']*l.fac<last for e in l.events['speed'])
            stat['lines_with_zero_speed']+=any(e['value']==0 and e['startTime']*l.fac<last for e in l.events['speed'])
            # Measure every note's final approach, and holds' full contact interval up to 8s for screening.
            for n in l.notes:
                hold=n['type']==3
                start=max(0,n['t'] if hold else n['t']-2);end=min(n['end'],n['t']+8) if hold else n['t']
                if end-start<.08:continue
                ts=np.linspace(start,end,33);pose=l.pose(ts);nx,ny,dist=l.path(n,ts)
                front=dist*(1 if n['side']=='notesAbove' else -1)
                visible=(nx>=-.04)&(nx<=1.04)&(ny>=-.04)&(ny<=1.04)&(front>=-1e-6)&(np.abs(dist)<3)
                # Require consecutive visible samples ending at the judgment/contact endpoint.
                if not visible[-1]:continue
                ix=len(ts)-1
                while ix>0 and visible[ix-1]:ix-=1
                if len(ts)-ix<4:continue
                ts=ts[ix:];pose=tuple(v[ix:] for v in pose);nx=nx[ix:];ny=ny[ix:]
                f=features(ts,pose);tags=note_tags(f,n,nx,ny,pose,ts)
                stat['screened_note_paths']+=1
                stat['notes_with_nonbaseline_tag']+=bool(tags)
                if not tags:continue
                pathlen=float(np.sum(np.hypot(np.diff(nx)*16/9,np.diff(ny))));chord=float(np.hypot((nx[-1]-nx[0])*16/9,ny[-1]-ny[0]))
                f.update(path_length_height_units=pathlen,path_excess=pathlen-chord,landing=[float(nx[-1]),float(ny[-1])])
                score=min(f['rotation_span'],720)/90+min(f['x_span']+f['y_span'],2)*3+min(f['path_excess'],5)*2+f['speed_changes']*.05
                candidates.append(dict(chart=rec['id'],category='note',lines=[li],start=float(ts[0]),end=float(ts[-1]),tags=tags,score=score,features=f,note={k:n[k] for k in ['side','index','type','t','end','positionX','speed']},whole_line_empty=False))
            # Empty lines are a conservative, unambiguous background-only pool.
            if not l.notes:
                for start in np.arange(0,max(0,last-1),1.5):
                    ts=np.linspace(start,min(start+3,last),61);f=features(ts,l.pose(ts));tags=background_tags(f)
                    if not tags:continue
                    score=min(f['rotation_span'],1080)/90+min(f['x_span']+f['y_span'],3)*3+f['alpha_edges']*.6
                    candidates.append(dict(chart=rec['id'],category='background',lines=[li],start=float(ts[0]),end=float(ts[-1]),tags=tags,score=score,features=f,whole_line_empty=True))
        # Multi-line background structures: only wholly empty lines, concurrent visibility.
        empty=[i for i,l in enumerate(lines) if not l.notes]
        for start in np.arange(0,max(0,last-2),2):
            ts=np.linspace(start,min(start+4,last),49);poses={i:lines[i].pose(ts) for i in empty};mid=len(ts)//2
            active=[i for i,p in poses.items() if np.mean((p[3]>.1)&line_visible(p[0],p[1],p[2]))>.65]
            for ai,i in enumerate(active):
                p=poses[i];f=features(ts,p)
                for j in active[ai+1:]:
                    q=poses[j];g=features(ts,q);delta=np.abs((p[2]-q[2]+90)%180-90);tags=[]
                    separation=np.hypot((p[0]-q[0])*16/9,p[1]-q[1]);sameangle=np.max(delta)<4
                    # Separation of parallel lines measured perpendicular to the line, not between pivots.
                    a=np.deg2rad(p[2]);normal=np.abs(-(p[0]-q[0])*16/9*np.sin(a)+(p[1]-q[1])*np.cos(a))
                    if sameangle and np.mean(normal)>.035:
                        if normal[-1]-normal[0]>.12:tags.append('parallel-opening')
                        if normal[0]-normal[-1]>.12:tags.append('parallel-closing')
                        if f['rotation_span']>20 and g['rotation_span']>20:tags.append('rotating-rails')
                        if extent(normal)>.10 and reversals(normal,.003)>=2:tags.append('breathing-corridor')
                        if extent(normal)<.025 and max(f['x_span'],f['y_span'])>.15:tags.append('parallel-conveyor')
                    if np.mean(separation)<.03 and np.max(delta)>20:
                        if extent(delta)>25:tags.append('hinged-fan')
                        if f['rotation_delta']*g['rotation_delta']< -400:tags.append('counter-rotating-cross')
                    if np.min(delta)<5 and np.max(delta)>40:tags.append('scissor-crossing')
                    if not tags:continue
                    ff=dict(f,partner=g,normal_gap_start=float(normal[0]),normal_gap_end=float(normal[-1]),angular_gap_span=extent(delta))
                    score=(min(f['rotation_span']+g['rotation_span'],720)/90+extent(normal)*5+extent(delta)/30)
                    candidates.append(dict(chart=rec['id'],category='background',lines=[i,j],start=float(ts[0]),end=float(ts[-1]),tags=tags,score=score,features=ff,whole_line_empty=True))
            if len(active)>=3:
                # Identify parallel combs and radial fans from visible empty lines at the midpoint.
                for anchor in active:
                    a=poses[anchor][2][mid];group=[i for i in active if abs((poses[i][2][mid]-a+90)%180-90)<4]
                    if len(group)<3:continue
                    r=math.radians(a);offsets=sorted(-poses[i][0][mid]*16/9*math.sin(r)+poses[i][1][mid]*math.cos(r) for i in group)
                    unique=[offsets[0]]
                    for v in offsets[1:]:
                        if v-unique[-1]>.025:unique.append(v)
                    if len(unique)>=3:
                        motion=sum(features(ts,poses[i])['rotation_span']+60*(extent(poses[i][0])+extent(poses[i][1])) for i in group)
                        if motion>20:
                            f=features(ts,poses[anchor]);f['parallel_count']=len(unique)
                            candidates.append(dict(chart=rec['id'],category='background',lines=group,start=float(ts[0]),end=float(ts[-1]),tags=['moving-line-comb'],score=motion/60+len(unique),features=f,whole_line_empty=True));break
                pivots=np.array([[poses[i][0][mid]*16/9,poses[i][1][mid]] for i in active])
                if np.max(np.linalg.norm(pivots-pivots.mean(0),axis=1))<.04:
                    angles=sorted(poses[i][2][mid]%180 for i in active)
                    if angles[-1]-angles[0]>60 and len(set(round(a/10) for a in angles))>=3:
                        f=features(ts,poses[active[0]]);f['ray_count']=len(active)
                        candidates.append(dict(chart=rec['id'],category='background',lines=active,start=float(ts[0]),end=float(ts[-1]),tags=['radial-line-fan'],score=len(active)+f['rotation_span']/90,features=f,whole_line_empty=True))
        summary.append(dict(rec,**stat));audit.append(dict(chart=rec['id'],event_issues=issues))
        if ci%20==0:print(ci+1,rec['title'],'candidates',len(candidates),flush=True)
    dump('chart-statistics.json',summary);dump('event-audit.json',audit)
    # Retain a bounded, diversified pool per mechanism rather than hundreds of thousands of overlapping rows.
    buckets=collections.defaultdict(list)
    for c in candidates:
        for tag in c['tags']:buckets[tag].append(c)
    selected=[];seen=set();counts={}
    for tag,cs in sorted(buckets.items()):
        counts[tag]=dict(candidates=len(cs),charts=len(set(c['chart'] for c in cs)))
        chart_count=collections.Counter(); kept=[]
        for c in sorted(cs,key=lambda c:c['score'],reverse=True):
            if chart_count[c['chart']]>=5:continue
            if any(k['chart']==c['chart'] and k['lines']==c['lines'] and abs(k['start']-c['start'])<5 for k in kept):continue
            kept.append(c);chart_count[c['chart']]+=1
            ident=(c['chart'],tuple(c['lines']),c['start'],c['end'],c.get('note',{}).get('index'))
            if ident not in seen:selected.append(c);seen.add(ident)
            if len(kept)>=120:break
    dump('candidate-pool.json',selected);dump('mechanism-counts.json',counts)
    print('Complete',len(summary),'charts',len(candidates),'raw candidates',len(selected),'retained',flush=True)

if __name__=='__main__':scan()
