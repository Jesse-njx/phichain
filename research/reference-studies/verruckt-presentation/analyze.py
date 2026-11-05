"""Read-only evaluation of original Verruckt line events; never authors a chart."""
from pathlib import Path
import bisect, collections, hashlib, json, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/jesse/Projects/PhiChain/phichain')
SOURCE = ROOT/'../research/arrangement-training/raw/Verruckt.Raimukun.0/IN.json'
NATIVE = ROOT/'../research/overnight-study/design/reference-projects/verruckt-regular/chart.json'
raw = json.loads(SOURCE.read_text())
native = json.loads(NATIVE.read_text())
lines = raw['judgeLineList']
beat_seconds = 60/238
channels = {'x': ('judgeLineMoveEvents','start','end'),
            'y': ('judgeLineMoveEvents','start2','end2'),
            'rotation': ('judgeLineRotateEvents','start','end'),
            'opacity': ('judgeLineDisappearEvents','start','end'),
            'speed': ('speedEvents','value','value')}
cache = {(i,k): ([e['startTime']/32 for e in l[key]],l[key],a,z)
         for i,l in enumerate(lines) for k,(key,a,z) in channels.items()}
def value(i,k,b):
    starts,events,a,z=cache[i,k]
    e=events[max(0,bisect.bisect_right(starts,b)-1)]
    lo,hi=e['startTime']/32,e['endTime']/32
    t=max(0,min(1,(b-lo)/(hi-lo))) if hi!=lo else 1
    return e[a]+(e[z]-e[a])*t

def beat(b): return b[0]+b[1]/b[2]
nc={}
for i,l in enumerate(native['lines']):
    for k in channels:
        es=sorted([e for e in l['events'] if e['kind']==k],key=lambda e:beat(e['start_beat']))
        nc[i,k]=([beat(e['start_beat']) for e in es],es)
def ease(t,k):
    return {'linear':lambda:t,'ease_in_quad':lambda:t*t,'ease_out_quad':lambda:1-(1-t)**2,
            'ease_in_out_quad':lambda:2*t*t if t<.5 else 1-(-2*t+2)**2/2,
            'ease_in_cubic':lambda:t**3,'ease_out_cubic':lambda:1-(1-t)**3,
            'ease_in_sine':lambda:1-math.cos(t*math.pi/2),'ease_out_sine':lambda:math.sin(t*math.pi/2),
            'ease_in_out_sine':lambda:-(math.cos(math.pi*t)-1)/2}[k]()
def nv(i,k,b):
    starts,es=nc[i,k];e=es[max(0,bisect.bisect_right(starts,b)-1)];v=e['value']
    if v['type']=='constant':return v['value']
    lo,hi=beat(e['start_beat']),beat(e['end_beat'])
    t=max(0,min(1,(b-lo)/(hi-lo))) if hi!=lo else 1
    return v['start']+(v['end']-v['start'])*ease(t,v['easing']['type'])

notes=[]
for i,l in enumerate(lines):
    for side in ['notesAbove','notesBelow']:
        for n in l[side]:
            b=n['time']/32
            notes.append({'line':i,'beat':b,'second':b*beat_seconds,'type':n['type'],
                          'above':side=='notesAbove','local_x':n['positionX']*75,
                          **{k:value(i,k,b) for k in ['x','y','rotation','opacity']}})
note_matches=[]
for i,l in enumerate(native['lines']):
    a=sorted((n['beat'],n['type'],n['above'],round(n['local_x'],2)) for n in notes if n['line']==i)
    kinds={'tap':1,'drag':2,'hold':3,'flick':4}
    b=sorted((beat(n['beat']),kinds[n['kind']],n['above'],round(n['x'],2)) for n in l['notes'])
    note_matches.append(len(a)==len(b) and all(x[:3]==y[:3] and abs(x[3]-y[3])<=.010001 for x,y in zip(a,b)))

maxerr={k:0 for k in channels};worst={}
for i in range(24):
    for sec in np.arange(0,122,1/60):
        b=sec/beat_seconds
        for k in channels:
            v=value(i,k,b)
            if k=='x':v=(v-.5)*1350
            elif k=='y':v=(v-.5)*900
            elif k=='opacity':v*=255
            elif k=='speed':v*=4.5
            err=abs(v-nv(i,k,b))
            if err>maxerr[k]:maxerr[k]=err;worst[k]={'line':i,'second':sec}

def snapshot(b):
    return {'beat':b,'second':b*beat_seconds,'lines':[{'line':i,**{k:value(i,k,b) for k in channels}} for i in range(24)]}

def segments(i,k,lo,hi):
    # Merge adjacent source samples with the same direction; preserve reversals/rests.
    key,a,z=channels[k];result=[]
    for e in lines[i][key]:
        s=max(lo,e['startTime']/32);f=min(hi,e['endTime']/32)
        if f<=s:continue
        vs=value(i,k,s);vf=e[z] if f==e['endTime']/32 else value(i,k,f)
        sign=0 if abs(vf-vs)<1e-9 else (1 if vf>vs else -1)
        if result and result[-1]['sign']==sign and abs(result[-1]['end_beat']-s)<1e-6 and abs(result[-1]['end_value']-vs)<1e-5:
            result[-1].update(end_beat=f,end_value=vf)
        else:result.append(dict(start_beat=s,end_beat=f,start_value=vs,end_value=vf,sign=sign))
    return result

passages=[(0,36,'Opening'),(36,64,'First attacks'),(64,128,'Vertical responses'),
          (128,200,'Diagonal / fence transition'),(200,264,'Tilted plane'),
          (264,336,'Dual plane'),(336,456,'Vertical return'),(456,484,'Exit')]
summary=[]
for lo,hi,label in passages:
    ns=[n for n in notes if lo<=n['beat']<hi]
    summary.append({'label':label,'beats':[lo,hi],'seconds':[lo*beat_seconds,hi*beat_seconds],
                    'notes':len(ns),'note_lines':dict(collections.Counter(n['line'] for n in ns)),
                    'heads_with_own_carrier_alpha_below_point1':sum(n['opacity']<.1 for n in ns)})
early=[n for n in notes if 36<=n['beat']<64]
report={'source_path':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'cached_native_sha256':hashlib.sha256(NATIVE.read_bytes()).hexdigest(),
        'line_ids':'zero-based original source indices','bpm':238,'seconds_per_beat':beat_seconds,
        'note_count':len(notes),'line_count':24,'line_note_counts':dict(collections.Counter(n['line'] for n in notes)),
        'cached_native_note_time_type_side_x_matches_by_line':note_matches,
        'cached_native_60fps_max_channel_error':maxerr,'cached_native_worst_error_at':worst,
        'early_36_64_note_geometry':{'notes':len(early),'y_range':[min(n['y'] for n in early),max(n['y'] for n in early)],
                                   'rotation_range':[min(n['rotation'] for n in early),max(n['rotation'] for n in early)],
                                   'hidden_carrier_heads':sum(n['opacity']<.1 for n in early)},
        'sections':summary,
        'selected_snapshots':[snapshot(b) for b in [0,8,16,24,32,36,40,48,64,80,96,128,160,176,192,200,208,224,240,256,272,288,304,320,336,352,384,416,448,464,480]],
        'motion_runs':{f'line{i}_{k}_{lo}_{hi}':segments(i,k,lo,hi) for i,k,lo,hi in [(0,'y',0,36),(1,'x',128,176),(0,'rotation',200,264),(0,'y',264,280),(1,'rotation',280,296),(14,'x',80,88),(14,'opacity',80,88)]}}
(HERE/'evidence.json').write_text(json.dumps(report,indent=2))
(HERE/'judgment-heads.json').write_text(json.dumps(notes,indent=2))

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(4,1,figsize=(13,10),layout='constrained')
for ax,(lo,hi,k,ids,label) in zip(axes,[(76,88,'x',[13,14,15,16],'Staggered vertical-line positions'),
                                     (128,160,'x',[1],'Playable carrier lateral motion'),
                                     (204,264,'rotation',[0,2],'Primary and echo-plane rotation'),
                                     (264,336,'y',[0,1],'Opposing playable planes')]):
    bs=np.linspace(lo,hi,2400)
    for i in ids:
        vs=[]
        for b in bs:
            v=value(i,k,b)
            visible=k=='rotation' or (value(i,'opacity',b)>.01 and -.1<=v<=1.1)
            vs.append(v if visible else np.nan)
        ax.plot(bs*beat_seconds,vs,label=f'Line {i}')
    for b in range(lo,hi+1,4):ax.axvline(b*beat_seconds,color='#eeeeee',zorder=0)
    ax.set(title=label,ylabel=k+(' (degrees)' if k=='rotation' else ' (normalized)'),xlabel='Chart/audio seconds');ax.legend(ncol=4)
    if k in ['x','y'] and len(ids)>1:ax.set_ylim(-.1,1.1)
fig.savefig(HERE/'motion-profiles.png',dpi=150);plt.close(fig)
print(json.dumps({k:report[k] for k in ['note_count','line_count','cached_native_note_time_type_side_x_matches_by_line','cached_native_60fps_max_channel_error','early_36_64_note_geometry','sections']},indent=2))
