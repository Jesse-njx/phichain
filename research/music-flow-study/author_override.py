"""Author this one study through PhiChain's guarded live bridge only."""
from pathlib import Path
from fractions import Fraction
import json, math
import numpy as np
from live import call,context,guard
ROOT=Path(__file__).resolve().parent
BPM=204.;OFFSET=.348;END=468.
NAMES=['01 · PULSE / left','02 · PULSE / right']+[f'{i+3:02} · FRAME / {i+1}' for i in range(4)]+[f'{i+7:02} · IMPACT / {i+1}' for i in range(2)]+[f'{i+9:02} · ORBIT / {i+1}' for i in range(8)]
def beat(v):
 f=Fraction(float(v)).limit_denominator(10000);w=f.numerator//f.denominator;return [w,(f-w).numerator,(f-w).denominator]
def event(kind,a,b,v,w=None,ease='ease_in_out_sine'):
 value={'type':'constant','value':float(v)} if w is None or abs(v-w)<1e-7 else {'type':'transition','start':float(v),'end':float(w),'easing':{'type':ease}}
 return {'kind':kind,'start_beat':beat(a),'end_beat':beat(b),'value':value}
def tracks(kind,points,ease='ease_in_out_sine'):
 p=sorted(dict(points).items())
 return [event(kind,a,b,v,w,ease) for (a,v),(b,w) in zip(p,p[1:]) if b>a]
def note(kind,b,x=0,hold=None):
 d={'kind':kind,'above':True,'beat':beat(b),'x':float(x),'speed':1.}
 if hold is not None:d['hold_beat']=beat(hold)
 return d
def phase(b):
 if b<40:return 'intro'
 if b<72:return 'bare'
 if b<128:return 'verse'
 if b<132:return 'suspense'
 if b<200:return 'chorus'
 if b<232:return 'orbit'
 if b<300:return 'verse2'
 if b<368:return 'chorus'
 if b<432:return 'final'
 return 'outro'
def commit(label,ops):
 c=context();assert c['project_path']==str(ROOT/'override-emotion'),c['project_path']
 request={**guard(c),'operations':ops}
 (ROOT/'receipts').mkdir(exist_ok=True)
 path=ROOT/'receipts'/f'{label}-request.json';path.write_text(json.dumps(request,ensure_ascii=False))
 result=call('apply_edits',request)
 (ROOT/'receipts'/f'{label}-result.json').write_text(json.dumps(result,ensure_ascii=False))
 print(label,len(ops),'operations',flush=True)

def main():
 c=context();assert c['project_path']==str(ROOT/'override-emotion')
 assert c['revision']=='3b93704b9c8ef883','Baseline changed; reread before rebuilding.'
 section=call('read_section',{'start_beat':0,'end_beat':500})
 assert len(section['notes'])==145
 (ROOT/'baseline-live-read.json').write_text(json.dumps(section))
 root=next(l for l in c['lines'] if l['order']==0)['id']
 ops=[{'op':'delete_line','id':l['id'],'cascade':True} for l in c['lines'] if l['id']!=root]
 ops += [{'op':'delete_note','id':n['id']} for n in section['notes'] if n['line_id']==root]
 ops += [{'op':'delete_event','id':e['id']} for e in section['events'] if e['line_id']==root]
 ops += [{'op':'update_line','id':root,'name':NAMES[0],'parent_id':None}]
 ops += [{'op':'create_line','name':n} for n in NAMES[1:]]
 meta=dict(c['meta']);meta.update(name='オーバーライド / OVERRIDE — Fractured Symmetry',level='Visual study · full song',charter='Codex × Jesse')
 ops += [{'op':'set_meta','meta':meta}]
 commit('01-carriers',ops)
 c=context();ids={l['name']:l['id'] for l in c['lines']}
 section=call('read_section',{'start_beat':0,'end_beat':500})
 ops=[{'op':'delete_event','id':e['id']} for e in section['events']]
 if ops:commit('02-defaults',ops)
 events={n:[] for n in NAMES};notes={n:[] for n in NAMES}
 # Shared playable lines stay low and readable; their angle and separation change by phrase.
 for side in range(2):
  n=NAMES[side];sign=-1 if side==0 else 1
  pts={k:[] for k in ['x','y','rotation','opacity']}
  for b in sorted(set([0,4,8,40,72,128,130,132,200,204,206,222,224,228,232,296,298,300,368,432,440,444,448,456,460,464,468]+list(range(8,465,8)))):
   ph=phase(b);sway=math.sin(b/8*math.pi)
   if ph=='intro':x=sign*(45+25*min(b/8,1));y=-170;rot=sign*(6 if b>=8 else 0);alpha=210
   elif ph=='bare':x=sign*38;y=-190;rot=sign*3;alpha=180
   elif ph=='verse':x=sign*75;y=-175;rot=sign*(7+4*math.cos(b/8*math.pi));alpha=210
   elif ph=='suspense':x=sign*20;y=-70;rot=sign*28;alpha=160
   elif ph in ['chorus','final']:x=sign*(100 if ph=='chorus' else 135);y=-145 if ph=='chorus' else -115;rot=sign*((12 if ph=='chorus' else 18)+5*math.cos(b/8*math.pi));alpha=230
   elif ph=='orbit':x=sign*90;y=-180;rot=sign*8;alpha=0 if 206<=b<222 else 190
   elif ph=='verse2':x=sign*55;y=-190;rot=sign*(5+3*math.cos(b/8*math.pi));alpha=185
   else:x=sign*70;y=-175;rot=sign*6;alpha=180 if b<440 else 0
   if b==468:alpha=0
   for k,v in [('x',x),('y',y),('rotation',rot),('opacity',alpha)]:pts[k].append((b,v))
  for k,p in pts.items():events[n]+=tracks(k,p)
  events[n]+=[event('speed',0,END,4.2)]
 # Quiet frame lines become a wider diamond in the refrain. No playable notes on these lines.
 for j in range(4):
  n=NAMES[2+j];pts={k:[] for k in ['x','y','rotation','opacity']}
  for b in sorted(set([0,2,8,40,72,128,130,132,200,204,208,224,232,296,298,300,368,432,440,448,460,464,468]+list(range(0,469,8)))):
   ph=phase(b);chorus=ph in ['chorus','final'];wide=1.15 if ph=='final' else 1
   theta=(j*90)+(22*math.sin(b*math.pi/32) if chorus else 5*math.sin(b*math.pi/32))
   radius=(270 if chorus else 235)*wide
   x=radius*math.cos(math.radians(theta));y=radius*.68*math.sin(math.radians(theta))
   rot=theta+90
   alpha=46 if chorus else (12 if ph in ['bare','verse2'] else 25)
   if ph=='orbit':alpha=20
   if b in [0,130,298,468] or b>=464:alpha=0
   for k,v in [('x',x),('y',y),('rotation',rot),('opacity',alpha)]:pts[k].append((b,v))
  for k,p in pts.items():events[n]+=tracks(k,p)
  events[n]+=[event('speed',0,END,0)]
 # Two accent strokes: brief, motivated by phrase entrances, never constant flashing.
 for j in range(2):
  n=NAMES[6+j];sg=-1 if j==0 else 1
  events[n]+=[event('x',0,END,0),event('y',0,END,0),event('speed',0,END,0)]
  alpha=[(0,0)];rot=[(0,sg*28)]
  for b in [8,40,72,132,148,164,180,200,232,300,316,332,348,368,384,400,416,432]:
   alpha.extend([(b-.25,0),(b,85 if b in [132,300,368] else 48),(b+.75,0)])
   rot.extend([(b-.25,sg*16),(b,sg*28),(b+1.5,sg*43)])
  alpha.append((END,0));rot.append((END,sg*43));events[n]+=tracks('opacity',alpha,'linear')+tracks('rotation',rot,'ease_out_cubic')
 # Select audio attacks, then thin them by musical section. This is intentionally moderate, not a difficulty target.
 analysis=json.loads((ROOT/'librosa/override.json').read_text());z=np.load(ROOT/'librosa/override.npz')
 candidates={}
 for t in analysis['onsets']:
  b=round((t-OFFSET)*BPM/60*2)/2
  if b<0 or b>464 or abs((OFFSET+b*60/BPM)-t)>.045:continue
  score=float(np.interp(t,z['time'],z['onset']));candidates[b]=max(score,candidates.get(b,0))
 chosen=[]
 for b,score in sorted(candidates.items()):
  ph=phase(b)
  if 204<=b<224 or b>=440 or 128<=b<132 or 296<=b<300:continue
  if b%1 and (ph in ['bare','verse2'] or score<1.8):continue
  if ph=='intro' and b%1 and b<8:continue
  if chosen and b-chosen[-1]<.5:continue
  chosen.append(b)
 motif=[-240,-80,100,240,120,-100,-230,0]
 for i,b in enumerate(chosen):
  side=i%2;ph=phase(b);x=motif[int(b)%8]
  if side==1:x=-x
  if ph in ['bare','verse2']:x*=.75
  kind='flick' if b%16 in [14,15] and ph in ['chorus','final'] else ('drag' if b%1 else 'tap')
  notes[NAMES[side]].append(note(kind,b,x))
 # Paired accents on the two large refrain returns, kept at different landing positions.
 for b in [132,300,368]:
  for side in range(2):
   notes[NAMES[side]]=[n for n in notes[NAMES[side]] if n['beat']!=beat(b)]
   notes[NAMES[side]].append(note('flick',b,-210 if side==0 else 210))
 # Eight ordinary playable notes form a rotating rosette, then resolve in two-note pairs.
 # They are visible early with unchanged future judgments; line speed is zero during suspension.
 for j in range(8):
  n=NAMES[8+j];pts={k:[(0,1500 if k=='y' else 0)] for k in ['x','y','rotation','opacity']};speeds=[]
  prev=0
  for scene,(begin,release) in enumerate([(204,224),(440,460)]):
   hit=release+(j//2)*1.;approach=hit-2
   # Keep the next scene's note far away throughout the previous scene's visible lifetime.
   if prev>0:
    speeds.append(event('speed',prev,begin-2,4))
    speeds.append(event('speed',begin-2,approach,0))
   elif prev<approach:speeds.append(event('speed',prev,approach,0))
   speeds.append(event('speed',approach,hit,4));prev=hit
   distance=101.25*4*2*60/BPM
   for b in [begin-2,begin,begin+4,begin+8,begin+12,begin+16,approach]:
    if b>approach:continue
    a=j*45+((b-begin)/(release-begin))*135+(15 if scene else 0)
    rad=190+20*math.sin((b-begin)*math.pi/8)
    px=rad*math.cos(math.radians(a));py=rad*.8*math.sin(math.radians(a))
    angle=a-90
    x=px+math.sin(math.radians(angle))*distance
    y=py-math.cos(math.radians(angle))*distance
    if b==begin-2:y=1500
    for k,v in [('x',x),('y',y),('rotation',angle),('opacity',0)]:pts[k].append((b,v))
   landing_x=(-1 if j%2==0 else 1)*(220-35*(j//2))
   for k,v in [('x',landing_x),('y',-150),('rotation',0),('opacity',0)]:
    pts[k].extend([(hit-1,v),(hit+.25,v),(hit+1,1500 if k=='y' else v)])
   notes[n].append(note('drag' if j<6 else 'flick',hit))
  if prev<END:speeds.append(event('speed',prev,END,0))
  for k,p in pts.items():
   p.append((END,p[-1][1]));events[n]+=tracks(k,p)
  events[n]+=speeds
 # All operations reference carriers just read from the live editor. No serialized chart is authored here.
 ops=[]
 for n in NAMES:
  for e in events[n]:ops.append({'op':'create_event','line_id':ids[n],'event':e})
  for no in sorted(notes[n],key=lambda x:x['beat'][0]+x['beat'][1]/x['beat'][2]):ops.append({'op':'create_note','line_id':ids[n],'note':no})
 for i in range(0,len(ops),800):
  call('read_section',{'start_beat':0,'end_beat':500})
  commit(f'{3+i//800:02}-content',ops[i:i+800])
 c=context();(ROOT/'authored-context.json').write_text(json.dumps(c,indent=2,ensure_ascii=False))
 print('AUTHORED',c['note_count'],'notes',c['event_count'],'events',len(c['lines']),'lines',flush=True)
if __name__=='__main__':main()
