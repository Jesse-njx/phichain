"""Select diverse measured recipes, export exact event evidence and diagnostic players."""
from analyze import *
from vocabulary import vocabulary
import functools, html

@functools.lru_cache(maxsize=5)
def load_chart(path):
    d=json.loads(Path(path).read_text());return d,[Line(l,d['formatVersion']) for l in d['judgeLineList']]

def signature(c):
    f=c['features'];rotation=f['rotation_span'];move=max(f['x_span'],f['y_span'])
    return (len(c['lines']), 'hidden' if f['alpha_max']<=.01 else 'gated' if f['alpha_min']<=.01 else 'visible',
        'pivot' if move<.035 else 'small-travel' if move<.2 else 'large-travel',
        'fixed' if rotation<8 else 'tilt' if rotation<60 else 'turn' if rotation<180 else 'spin',
        min(2,f['rotation_reversals']),min(2,f['x_reversals']+f['y_reversals']),
        ('horizontal' if abs(math.sin(math.radians(f['mean_angle'])))<.2 else 'vertical' if abs(math.cos(math.radians(f['mean_angle'])))<.2 else 'oblique') if c['category']=='background' and rotation<8 else ('background' if c['category']=='background' else 'reverse' if f['negative_speed_samples'] else 'stop' if f['zero_speed_samples'] else 'step' if f['speed_changes']>1 else 'steady'),
        min(2,f['alpha_edges']), c.get('note',{}).get('type',0), min(2,c.get('features',{}).get('ensemble_count',0)))

def flavor(c):
    f=c['features'];parts=[]
    if len(c['lines'])>=3:parts.append(f'{len(c["lines"])}-line field')
    elif len(c['lines'])==2:parts.append('paired carriers')
    else:parts.append('fixed pivot' if max(f['x_span'],f['y_span'])<.035 else 'travelling pivot')
    if f['rotation_span']>=250:parts.append('full-turn motion')
    elif f['rotation_span']>=90:parts.append('wide turn')
    elif f['rotation_span']>=15:parts.append('tilted motion')
    elif c['category']=='background':
        parts.append('horizontal stroke' if abs(math.sin(math.radians(f['mean_angle'])))<.2 else 'vertical stroke' if abs(math.cos(math.radians(f['mean_angle'])))<.2 else 'oblique stroke')
    if f['rotation_reversals']>=2 or f['x_reversals']+f['y_reversals']>=3:parts.append('repeated reversals')
    if f['alpha_max']<=.01:parts.append('hidden rail')
    elif f['alpha_edges']>=3:parts.append('flashed rail')
    elif f['alpha_span']>.5:parts.append('fading rail')
    if c['category']=='note':
        if f['negative_speed_samples']:parts.append('reverse scroll')
        elif f['zero_speed_samples']:parts.append('scroll pause')
    return ' / '.join(parts[:4])

def refine(c,rec):
    d,ls=load_chart(rec['path']);ts=np.linspace(c['start'],c['end'],max(16,int((c['end']-c['start'])*60)+1))
    # Exclude large frame discontinuities from smoothly named mechanisms.
    for li in c['lines']:
        p=ls[li].pose(ts)
        if np.max(np.abs(np.diff(p[0])))>.25 or np.max(np.abs(np.diff(p[1])))>.25 or np.max(np.abs(np.diff(p[2])))>50:return None
    if 'note'in c:
        li=c['lines'][0];n=next(n for n in ls[li].notes if n['side']==c['note']['side'] and n['index']==c['note']['index'])
        x,y,dist=ls[li].path(n,ts);side=1 if n['side']=='notesAbove' else -1
        ok=(x>=-.05)&(x<=1.05)&(y>=-.05)&(y<=1.05)&(dist*side>=-1e-6)
        if np.mean(ok)<.94:return None
        if n['type']==3 and max(extent(x),extent(y))<.08:return None
        f=features(ts,ls[li].pose(ts));tags=note_tags(f,n,x,y,ls[li].pose(ts),ts)
        c=dict(c);c['tags']=[tag for tag in c['tags'] if tag in tags]
        if not c['tags']:return None
        c['features']=dict(c['features'],**f)
    else:
        # Multi-line formations keep their group metrics; update primary pose metrics.
        f=features(ts,ls[c['lines'][0]].pose(ts));c=dict(c);c['features']=dict(c['features'],**f)
        formations={'zigzag-note-formation','arched-note-formation','speed-fanned-formation'}
        if max(f['x_span'],f['y_span'])>=.02 or f['rotation_span']>=3:
            c['tags']=[t for t in c['tags'] if t not in formations]
            if not c['tags']:return None
        if 'parallel-conveyor' in c['tags'] and any(extent(ls[i].pose(ts)[2])>=6 for i in c['lines']):
            c['tags']=[t for t in c['tags'] if t!='parallel-conveyor']
        if 'arched-note-formation' in c['tags']:
            refs=[next(n for n in ls[r['line']].notes if n['side']==r['side'] and n['index']==r['index']) for r in c['ensemble']]
            unique={round(n['t'],6):n['positionX'] for n in refs};xx=np.array([v for _,v in sorted(unique.items())]);dx=np.diff(xx)
            signs=np.sign(dx[np.abs(dx)>.12]);turns=np.where(signs[1:]!=signs[:-1])[0]
            valid=len(set(round(v,2) for v in xx))>=8 and len(turns)==1 and min(turns[0]+1,len(signs)-turns[0]-1)>=3 and np.max(np.abs(dx))<extent(xx)*.35
            if not valid:c['tags']=[t for t in c['tags'] if t!='arched-note-formation']
        if 'speed-fanned-formation' in c['tags']:
            visible_speeds=[set() for _ in ts]
            for ref in c['ensemble']:
                l=ls[ref['line']];n=next(n for n in l.notes if n['side']==ref['side'] and n['index']==ref['index']);xx,yy,dd=l.path(n,ts)
                valid=(ts<=n['t']+1e-6)&(xx>=0)&(xx<=1)&(yy>=0)&(yy<=1)&(dd*(1 if n['side']=='notesAbove' else -1)>=0)
                for k in np.where(valid)[0]:visible_speeds[k].add(round(n['speed'],1))
            if sum(len(s)>1 for s in visible_speeds)<12:c['tags']=[t for t in c['tags'] if t!='speed-fanned-formation']
        if not c['tags']:return None
        # A multi-line shape may only exist for a subinterval of the initial mining window.
        if 'moving-line-comb'in c['tags'] or 'radial-line-fan'in c['tags']:
            ps=[ls[i].pose(ts) for i in c['lines']];good=[]
            for k in range(len(ts)):
                angles=np.array([p[2][k] for p in ps]);xy=np.array([[p[0][k]*16/9,p[1][k]] for p in ps]);alpha=np.array([p[3][k] for p in ps])
                if 'moving-line-comb'in c['tags']:
                    delta=np.abs((angles-angles[0]+90)%180-90);a=math.radians(angles[0]);offsets=sorted(-xy[:,0]*math.sin(a)+xy[:,1]*math.cos(a));unique=[offsets[0]]
                    for v in offsets[1:]:
                        if v-unique[-1]>.025:unique.append(v)
                    good.append(max(delta)<4 and len(unique)>=3 and np.all(alpha>.05))
                else:
                    # Geometry can persist during intentional alpha flashes.
                    angle_bins=len(set(round((a%180)/10) for a in angles));good.append(np.max(np.linalg.norm(xy-xy.mean(0),axis=1))<.04 and angle_bins>=3)
            runs=[];start=None
            for k,ok in enumerate(good+[False]):
                if ok and start is None:start=k
                if not ok and start is not None:runs.append((start,k-1));start=None
            if not runs:return None
            a,b=max(runs,key=lambda r:r[1]-r[0])
            if ts[b]-ts[a]<.4:return None
            c['mining_window']=[c['start'],c['end']];c['start']=float(ts[a]);c['end']=float(ts[b]);ts=ts[a:b+1];f=features(ts,ls[c['lines'][0]].pose(ts));c['features']=dict(c['features'],**f)
        if c['category']=='background' and f['rotation_span']<6 and f['normal_offset_span']<.04 and f['alpha_span']<.25 and len(c['lines'])==1:return None
    return c

def select():
    recs={r['id']:r for r in json.loads((ROOT/'inventory.json').read_text())['charts']};pool=json.loads((ROOT/'candidate-pool.json').read_text())+json.loads((ROOT/'ensemble-candidates.json').read_text());voc=vocabulary()
    issues={r['chart']:{v[0] for v in r['event_issues']} for r in json.loads((ROOT/'event-audit.json').read_text())}
    refined=[]
    for cid in recs:
        if len(set(l['bpm'] for l in json.loads(Path(recs[cid]['path']).read_text())['judgeLineList']))>1:continue
        for c in (c for c in pool if c['chart']==cid):
            if any(i in issues[cid] for i in c['lines']):continue
            r=refine(c,recs[cid])
            if r:refined.append(r)
    dump('refined-candidates.json',refined)
    buckets=collections.defaultdict(list)
    for c in refined:
        for tag in c['tags']:buckets[tag].append(c)
    chosen=[];per=collections.Counter();bytag=collections.defaultdict(list)
    # First represent each mechanism; then add source-independent, compositionally different variants.
    for round_number in range(3):
        for tag in sorted(buckets,key=lambda k:(len(buckets[k]),k)):
            options=[]
            for c in buckets[tag]:
                if per[c['chart']]>=6:continue
                if any(k['chart']==c['chart'] for k in bytag[tag]):continue
                if any(signature(c)==signature(k) for k in bytag[tag]):continue
                if any(k['chart']==c['chart'] and set(k['lines'])&set(c['lines']) and not(c['end']+1<k['start'] or c['start']>k['end']+1) for k in chosen):continue
                f=c['features']
                # Favor interpretable moderate motion instead of numerically extreme outliers.
                score=min(c['score'],12)-per[c['chart']]*1.3
                if recs[c['chart']].get('music_path'):score+=.4
                if max(f['x_span'],f['y_span'])>2:score-=4
                if c['end']-c['start']<.2:score-=3
                options.append((score,c))
            if options:
                c=dict(max(options,key=lambda v:v[0])[1]);c['mechanism']=tag;chosen.append(c);bytag[tag].append(c);per[c['chart']]+=1
    chosen.sort(key=lambda c:(c['category']!='note',list(voc).index(c['mechanism']),c['chart'],c['start']))
    counts=collections.Counter()
    for c in chosen:
        prefix='N' if c['category']=='note' else 'B';counts[prefix]+=1;c['id']=prefix+str(counts[prefix]).zfill(3);c['name']=voc[c['mechanism']]['name']+' — '+flavor(c);c['source']=recs[c['chart']];c['definition']=voc[c['mechanism']];c['verification']='60 Hz decoded geometry; native rendering not yet checked'
    dump('bank.json',chosen);dump('vocabulary.json',voc)
    dump('selection-summary.json',dict(recipes=len(chosen),categories=dict(counts),mechanisms=len(bytag),charts=len(per),mechanism_recipes={k:len(v) for k,v in bytag.items()},unrepresented_definitions=sorted(set(voc)-set(bytag)),refined_candidates=len(refined)))
    print('Selected',len(chosen),dict(counts),'mechanisms',len(bytag),'charts',len(per),flush=True)

def export_evidence():
    bank=json.loads((ROOT/'bank.json').read_text());folder=ROOT/'evidence';folder.mkdir(exist_ok=True)
    for c in bank:
        d,ls=load_chart(c['source']['path']);evidence={'id':c['id'],'source_sha256':c['source']['sha256'],'source_path':c['source']['path'],'source_original_path':c['source']['original_path'],'source_url':c['source']['source_url'],'chart_seconds':[c['start'],c['end']],'audio_seconds':[c['start']+d.get('offset',0),c['end']+d.get('offset',0)],'format_version':d['formatVersion'],'line_indices_zero_based':c['lines'],'lines':[]}
        for li in c['lines']:
            l=ls[li];row={'index':li,'bpm':l.raw['bpm'],'ticks':[c['start']/l.fac,c['end']/l.fac],'beats':[c['start']/l.fac/32,c['end']/l.fac/32],'whole_chart_note_count':len(l.notes),'events':[],'notes':[]}
            for field in CHANNELS.values():
                es=d['judgeLineList'][li].get(field,[])
                ids=[i for i,e in enumerate(es) if e['startTime']*l.fac<=c['end'] and e['endTime']*l.fac>=c['start']]
                # If a channel has a gap, include its latest preceding event to document the held value.
                prev=[i for i,e in enumerate(es) if e['startTime']*l.fac<=c['start']]
                if prev:ids.append(max(prev,key=lambda i:es[i]['startTime']))
                for i in sorted(set(ids)):row['events'].append({'pointer':f'/judgeLineList/{li}/{field}/{i}','event':es[i]})
            refs=[]
            if 'note'in c and li==c['lines'][0]:refs=[c['note']]
            refs += [n for n in c.get('ensemble',[]) if n['line']==li]
            for n in refs:
                raw=d['judgeLineList'][li][n['side']][n['index']];row['notes'].append({'pointer':f'/judgeLineList/{li}/{n["side"]}/{n["index"]}','note':raw,'integrated_floor_residual':float(raw['floorPosition']-l.floor([raw['time']*l.fac])[0])})
            evidence['lines'].append(row)
        (folder/(c['id']+'.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print('Exact evidence exported',len(bank),flush=True)

if __name__=='__main__':select();export_evidence()
