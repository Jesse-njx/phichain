from pathlib import Path
import json,subprocess,shutil,math,sys
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).parent;R=P.parents[2]
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',16)
small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',12)
colors={1:'#55cfff',2:'#ffe169',3:'#89e0c3',4:'#ff798b'}
rows=json.loads((P/'analysis.json').read_text())
render=[]
choices={'cross':[82,25],'fighters':[115,45],'dream':[55,123],'cthugha-in':[98,144],'cthugha-at':[98,142],'terabyte':[41,135],'cycle':[145,157]}
for m in rows:
 p=P/m['key'];ns=json.loads((p/'notes.json').read_text())
 im=Image.new('RGB',(1600,1000),'#111722');dr=ImageDraw.Draw(im)
 for j,w in enumerate(m['dense_windows']):
  s=w['start'];e=w['end'];y0=j*250
  dr.text((15,y0+8),f"{m['key']} | audio {s:.3f}–{e:.3f}s | {w['tap_count']} Taps / {w['tap_onsets']} Tap onsets | x=actual judgment position",fill='white',font=font)
  tx=lambda t:75+(t-s)/8*1495
  yy=lambda x:y0+220-(x+675)/1350*170
  for x in [-450,-225,0,225,450]:
   y=yy(x);dr.line((75,y,1570,y),fill='#334251');dr.text((10,y-7),str(x),fill='#b4c6d5',font=small)
  for t in range(math.ceil(s),math.ceil(e)):
   dr.line((tx(t),y0+40,tx(t),y0+226),fill='#29323e');dr.text((tx(t),y0+228),str(t),fill='#b4c6d5',font=small)
  for n in ns:
   if n['kind']==3 and n['end']>s and n['t']<e:dr.line((tx(max(s,n['t'])),yy(n['x']),tx(min(e,n['end'])),yy(n['x'])),fill=colors[3],width=2)
   if s<=n['t']<e:
    x=tx(n['t']);y=yy(n['x']);co=colors[n['kind']]
    if n['kind']==1:dr.ellipse((x-3,y-3,x+3,y+3),fill=co)
    else:dr.rectangle((x-2,y-2,x+2,y+2),fill=co)
 im.save(p/'density-strips.png')
 if '--strips-only' in sys.argv:continue
 project=p/'render-project';project.mkdir(exist_ok=True)
 cmd=[str(R/'target/debug/phichain-converter'),str(p/'source.json'),str(project/'chart.json'),'--from','official','--to','phichain','--no-easing-fitting','--round','6','--no-telemetry']
 result=subprocess.run(cmd,capture_output=True,text=True);(p/'conversion.log').write_text(result.stdout+result.stderr)
 if result.returncode:raise RuntimeError(m['key']+' conversion failed')
 shutil.copy2(R/'../charts/silent/silent-180-sixteenths/project/illustration.jpg',project/'illustration.jpg')
 target=project/'music.ogg'
 if not target.exists():target.symlink_to(m['music_path'])
 (project/'meta.json').write_text(json.dumps({'name':m['id'].split('.')[0],'level':m['difficulty'],'composer':'Reference study','charter':'Original chart','illustrator':'Neutral study background'}))
 for i,s in enumerate(choices[m['key']]):render.append({'key':m['key'],'index':i,'start':s,'end':s+9,'project':str(project)})
if render:(P/'render-plan.json').write_text(json.dumps(render,indent=2))
print('Prepared views')
