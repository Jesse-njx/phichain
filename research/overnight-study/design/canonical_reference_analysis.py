"""Analysis-only projection of official hit positions onto their dominant playing axis.
Never exports a chart. Keep source identity and special-geometry flags.
"""
import pathlib,json,math,bisect,collections
from PIL import Image,ImageDraw,ImageFont
R=pathlib.Path(__file__).resolve().parents[1]
SPECS=json.loads((R/'design/deep_reference_specs.json').read_text())
SPECS += [dict(name='der-schneid-ending',id='DerSchneid.Ωμεγα',difficulty='AT',start=133,end=151,question='Main playing locus, technical carriers, empty lines, and exaggerated final hold bars')]
COL={1:'#55cfff',2:'#ffe169',3:'#72e2f2',4:'#ff6b8c'}
try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',17)
except OSError:font=ImageFont.load_default()
def val(events,t,start='start',end='end',default=0):
 es=[e for e in events if e['startTime']<=t]
 if not es:return default
 e=max(es,key=lambda e:e['startTime']);dt=e['endTime']-e['startTime'];u=1 if dt<=0 else min(1,max(0,(t-e['startTime'])/dt))
 return e.get(start,default)*(1-u)+e.get(end,default)*u
def pose(c,i,sec):
 l=c['judgeLineList'][i];t=sec*l['bpm']/60*32
 if c['formatVersion']==1:
  ex=val(l['judgeLineMoveEvents'],t,default=440265);x=math.floor(ex/1000)/880;y=(ex%1000)/530
 else:
  x=val(l['judgeLineMoveEvents'],t,default=.5);y=val(l['judgeLineMoveEvents'],t,'start2','end2',.5)
 theta=math.radians(val(l['judgeLineRotateEvents'],t));a=val(l['judgeLineDisappearEvents'],t,default=0)
 return (x-.5)*1350,(y-.5)*759.375,theta,a
reports=[]
for spec in SPECS:
 c=json.loads((R/'corpus/chart'/f"{spec['id']}.0"/f"{spec['difficulty']}.json").read_text())
 ns=[]
 for i,l in enumerate(c['judgeLineList']):
  for side in ['notesAbove','notesBelow']:
   for n in l[side]:
    sec=n['time']/32*60/l['bpm'];dur=n['holdTime']/32*60/l['bpm']
    if sec+dur<spec['start'] or sec>spec['end']:continue
    x,y,rot,a=pose(c,i,sec);nx=n['positionX']/18*1350
    ns.append(dict(time=sec,duration=dur,kind=n['type'],line=i,side=side,local_x=nx,world_x=x+nx*math.cos(rot),world_y=y+nx*math.sin(rot),rotation_deg=math.degrees(rot),opacity=a,speed=n['speed']))
 heads=[n for n in ns if spec['start']<=n['time']<spec['end']];dominant=collections.Counter(n['line'] for n in heads).most_common(1)[0][0]
 for n in ns:
  mx,my,mr,ma=pose(c,dominant,n['time']);dx=n['world_x']-mx;dy=n['world_y']-my
  n['canonical_x']=dx*math.cos(mr)+dy*math.sin(mr);n['perpendicular_offset']=abs(-dx*math.sin(mr)+dy*math.cos(mr));n['special_geometry']=n['perpendicular_offset']>30 or abs(n['rotation_deg']-math.degrees(mr))>15
 kinds=dict(collections.Counter(n['kind'] for n in heads));empty=[i for i,l in enumerate(c['judgeLineList']) if not l['notesAbove'] and not l['notesBelow']]
 report=dict(**spec,heads=len(heads),types=kinds,dominant_engine_line=dominant,engine_lines_with_heads=sorted(set(n['line'] for n in heads)),global_empty_lines=empty,special_geometry_heads=sum(n['special_geometry'] for n in heads),longest_hold_s=max((n['duration'] for n in ns if n['kind']==3),default=0),records=ns)
 reports.append(report)
 w=1540;h=640;im=Image.new('RGB',(w,h),'#111722');d=ImageDraw.Draw(im)
 d.text((18,12),f"{spec['name']} | {spec['difficulty']} official {spec['start']}–{spec['end']}s | analysis-only hit-axis projection",font=font,fill='white')
 d.text((18,38),f"heads {len(heads)} | dominant engine line {dominant} | off-row/angled carrier flags {report['special_geometry_heads']} | retain source identity",font=font,fill='#b2c3d9')
 x0=95;x1=1505;y0=90;y1=480
 tx=lambda t:x0+(t-spec['start'])/(spec['end']-spec['start'])*(x1-x0)
 yy=lambda x:y1-(x+675)/1350*(y1-y0)
 for lane in [-600,-300,0,300,600]:
  y=yy(lane);d.line((x0,y,x1,y),fill='#354355');d.text((12,y-10),str(lane),font=font,fill='#b2c3d9')
 for t in range(int(spec['start']),int(spec['end'])+1):
  x=tx(t);d.line((x,y0,x,y1),fill='#293747');d.text((x-14,y1+6),str(t),font=font,fill='#b2c3d9')
 for n in sorted(ns,key=lambda n:n['kind']!=3):
  x=tx(n['time']);y=yy(max(-660,min(660,n['canonical_x'])));co=COL[n['kind']]
  if n['kind']==3:d.line((max(x0,x),y,min(x1,tx(n['time']+n['duration'])),y),fill=co,width=4)
  if n['time']<spec['start']:continue
  if n['kind']==4:d.polygon([(x,y-5),(x-5,y+4),(x+5,y+4)],fill=co)
  elif n['kind']==2:d.rectangle((x-3,y-3,x+3,y+3),fill=co)
  else:d.ellipse((x-4,y-4,x+4,y+4),fill=co)
  if n['special_geometry']:d.ellipse((x-7,y-7,x+7,y+7),outline='#ffffff',width=1)
 d.text((15,530),'Blue circle = fresh tap; yellow square = drag contact; cyan bar = hold duration; red triangle = flick. White ring = off-row/angled carrier (inspect roles).',font=font,fill='white')
 d.text((15,559),'Projection preserves actual hit-position along dominant axis; it is NOT a playable rearrangement and cannot erase gimmick difficulty.',font=font,fill='#b2c3d9')
 d.text((15,588),'Do not count each drag as a fresh strike. Holds and travelling drags occupy contacts; carrier identity and source side remain in JSON.',font=font,fill='#b2c3d9')
 im.save(R/'design'/f"{spec['name']}-canonical.png")
 print(spec['name'], 'heads',len(heads),'types',kinds,'main',dominant,'special',report['special_geometry_heads'],'empty',empty)
(R/'design/deep-reference-projection.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False))
