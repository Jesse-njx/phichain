import pathlib,json,math,bisect,collections
from PIL import Image,ImageDraw,ImageFont
P=pathlib.Path('../research/overnight-study/corpus');R=P.parent/'research';A=R/'supplemental-atlas';A.mkdir(exist_ok=True)
M=json.loads((P/'supplemental-manifest.json').read_text());metrics=json.loads((P/'supplemental-metrics.json').read_text());colors={1:'#59cffa',2:'#f8d748',3:'#62d7ff',4:'#fb7798'}
font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',14);big=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',18)
def prepared(l):
 o={};fac=1.875/l['bpm']
 for k in ['judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents','speedEvents']:
  es=l.get(k,[]);o[k]=(es,[e['startTime']*fac for e in es])
 es,st=o['speedEvents'];floor=[];pos=0
 for e in es:floor.append(pos);pos+=(e['endTime']-e['startTime'])*fac*e['value']
 o['floor']=floor;o['fac']=fac;return o
def val(o,k,t,second=False):
 es,st=o[k]
 if not es:return 0
 i=max(0,bisect.bisect_right(st,t)-1);e=es[i];a=e.get('start2' if second else 'start',0);b=e.get('end2' if second else 'end',0);dur=(e['endTime']-e['startTime'])*o['fac'];f=max(0,min(1,(t-st[i])/dur)) if dur else 1
 return a+(b-a)*f
def floor(o,t):
 es,st=o['speedEvents']
 if not es:return 0
 i=max(0,bisect.bisect_right(st,t)-1);return o['floor'][i]+max(0,t-st[i])*es[i]['value']
def xy(o,t):return val(o,'judgeLineMoveEvents',t),1-val(o,'judgeLineMoveEvents',t,True),-math.radians(val(o,'judgeLineRotateEvents',t))
def clipped_line(dr,a,b,box,fill):
 x,y=a;dx=b[0]-x;dy=b[1]-y;lo,hi=0.,1.
 for p,q in [(-dx,x-box[0]),(dx,box[2]-x),(-dy,y-box[1]),(dy,box[3]-y)]:
  if p==0:
   if q<0:return
  else:
   v=q/p
   if p<0:lo=max(lo,v)
   else:hi=min(hi,v)
 if lo<=hi:dr.line((x+lo*dx,y+lo*dy,x+hi*dx,y+hi*dy),fill=fill,width=1)
index=[];sheet=None
for idx,(m,met) in enumerate(zip(M,metrics)):
 d=json.loads(pathlib.Path(m['chart']['path']).read_text());ls=[prepared(l) for l in d['judgeLineList']];W,H=1200,720
 im=Image.new('RGB',(W,H),'#10131d');dr=ImageDraw.Draw(im);name=f"{idx+1:02d} {m['title']} {m['difficulty']} {m['constant']}"
 dr.text((12,8),name,font=big,fill='white');dr.text((12,34),f"{met['note_count']} notes | Tap/Drag/Hold/Flick {list(met['types'].values())} | {met['line_count']} lines | schematic official-event sample; not gameplay simulation",font=font,fill='#9ba9be')
 duration=met['last_note_end_seconds'];peak=max(met['section_windows'],key=lambda w:w['notes'])['start']+4
 samples=[duration*.1,duration*.3,duration*.5,peak,duration*.75,duration*.93]
 tw,th=194,110
 for ci,(label,col) in enumerate([('Tap',colors[1]),('Drag',colors[2]),('Hold (tail)',colors[3]),('Flick',colors[4])]):dr.text((700+ci*116,8),label,font=font,fill=col)
 for si,t in enumerate(samples):
  ox=12+si*198;oy=67;dr.rectangle((ox,oy,ox+tw,oy+th),outline='#566176');dr.text((ox,oy+th+4),f'{t:.2f}s',fill='white',font=font)
  for li,(l,o) in enumerate(zip(d['judgeLineList'],ls)):
   x,y,r=xy(o,t);x=ox+x*tw;y=oy+y*th;alpha=val(o,'judgeLineDisappearEvents',t)
   if alpha>0:
    dx=tw*math.cos(r);dy=tw*math.sin(r);clipped_line(dr,(x-dx,y-dy),(x+dx,y+dy),(ox,oy,ox+tw,oy+th),'#60758b')
   for side in ['notesAbove','notesBelow']:
    for n in l.get(side,[]):
     nt=n['time']*o['fac'];end=nt+n.get('holdTime',0)*o['fac']
     if not (t-.05<=nt<=t+1.2 or n['type']==3 and nt<=t<=end):continue
     lateral=n['positionX']*.05625*tw
     # Schematic approach: head-speed semantics differ for holds.
     dist=(n['floorPosition']-floor(o,t))*(1 if n['type']==3 else n.get('speed',1))*th*.6
     if n['type']==3 and nt<=t:dist=0
     if side=='notesBelow':dist=-dist
     nx=x+lateral*math.cos(r)+dist*math.sin(r);ny=y+lateral*math.sin(r)-dist*math.cos(r)
     if not (ox<=nx<=ox+tw and oy<=ny<=oy+th):continue
     c=colors[n['type']];dr.ellipse((nx-2,ny-2,nx+2,ny+2),fill=c)
     if n['type']==3:dr.line((nx,ny,nx-math.sin(r)*15,ny+math.cos(r)*15),fill=c,width=2)
 # Canonical arrangement view: all sources collapsed to one approach axis, retaining line-local x.
 ox,oy,pw,ph=12,248,1176,170;dr.text((12,220),'Canonical arrangement: raw line-local x collapsed to one axis; source line relationships and approach directions require separate review.',font=font,fill='#9ba9be');dr.rectangle((ox,oy,ox+pw,oy+ph),outline='#566176')
 for li,(l,o) in enumerate(zip(d['judgeLineList'],ls)):
  for side in ['notesAbove','notesBelow']:
   for n in l.get(side,[]):
    nt=n['time']*o['fac'];px=ox+nt/duration*pw;py=oy+(1-max(0,min(1,.5+n['positionX']/18)))*ph
    dr.ellipse((px-1,py-1,px+1,py+1),fill=colors[n['type']])
    if n['type']==3:dr.line((px,py,px+n.get('holdTime',0)*o['fac']/duration*pw,py),fill=colors[n['type']],width=1)
 for tick in range(0,math.ceil(duration),20):
  xx=ox+tick/duration*pw;dr.text((xx,oy+ph+3),str(tick)+'s',font=font,fill='#9ba9be')
 # Full contact timeline: judgments positions evaluated at each note's own time (no fixed-line approximation).
 ox,oy,pw,ph=12,480,1176,170;dr.text((12,450),'Presented contacts: line position and angle at each note onset; tails mark duration at initial x and do not follow moving hold contacts.',font=font,fill='#9ba9be');dr.rectangle((ox,oy,ox+pw,oy+ph),outline='#566176')
 for li,(l,o) in enumerate(zip(d['judgeLineList'],ls)):
  for side in ['notesAbove','notesBelow']:
   for n in l.get(side,[]):
    nt=n['time']*o['fac'];x,y,r=xy(o,nt);x+=n['positionX']*.05625*math.cos(r)
    px=ox+nt/duration*pw;py=oy+(1-max(0,min(1,x)))*ph
    dr.ellipse((px-1,py-1,px+1,py+1),fill=colors[n['type']])
    if n['type']==3:dr.line((px,py,px+n.get('holdTime',0)*o['fac']/duration*pw,py),fill=colors[n['type']],width=1)
 for tick in range(0,math.ceil(duration),20):
  xx=ox+tick/duration*pw;dr.line((xx,oy+ph,xx,oy+ph+4),fill='#9ba9be');dr.text((xx,oy+ph+4),str(tick)+'s',font=font,fill='#9ba9be')
 dr.text((12,686),'Chart time (offset excluded); local/world x axes clamped; snapshots = 10/30/50%, densest 8s bin center, 75/93%; 1.2s horizon; schematic tails.',font=font,fill='#9ba9be')
 fname=f'{idx+1:02d}-{m["difficulty"]}.png';im.save(A/fname);index.append(dict(title=name,image=f'supplemental-atlas/{fname}',samples=samples))
 if idx%3==0:sheet=Image.new('RGB',(1200,2160),'#10131d')
 sheet.paste(im,(0,(idx%3)*720))
 if idx%3==2 or idx==len(M)-1:sheet.save(A/f'sheet-{idx//3+1:02d}.png')
 print(name,flush=True)
(A/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2))
(R/'supplemental-atlas.html').write_text('<!doctype html><meta charset="utf-8"><title>Phigros corpus atlas</title><style>body{background:#10131d;color:white;font-family:sans-serif}img{max-width:100%}summary{cursor:pointer;padding:10px}</style><h1>Supplementary reference atlas</h1><p>Automated official-format JSON visualization. Canonical rhythm/lateral arrangement is separate from presented contacts. Chart-time axes omit offset. Six schematic approach snapshots per chart; not complete hold paths or official rendering. This is a static sampling, not complete gameplay review.</p>'+''.join(f'<details><summary>{x["title"]}</summary><img src="{x["image"]}"></details>' for x in index))
