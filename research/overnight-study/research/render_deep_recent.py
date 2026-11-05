"""Strictly render additional source clips; resumable, exact commands logged."""
from pathlib import Path
import subprocess,json,time,sys
from PIL import Image,ImageDraw,ImageFont
BASE=Path('/Users/jesse/Projects/PhiChain/research/overnight-study/research/deep-recent');renderer=Path('/Users/jesse/Projects/PhiChain/apps/PhiChain.app/Contents/MacOS/phichain-renderer')
font=ImageFont.truetype('/Users/jesse/Projects/PhiChain/phichain/assets/font/MiSans-Regular.ttf',15)
rows=json.loads((BASE/'manifest.json').read_text()); receipts=[]
if (BASE/'render-receipts.json').exists():receipts=json.loads((BASE/'render-receipts.json').read_text())
for r in rows:
 if r['native_status']!='exported_without_source_repair':continue
 folder=Path(r['folder'])
 for w in r['windows']:
  output=folder/f'{w["role"]}.mp4';log=folder/f'{w["role"]}.log'
  args=[str(renderer),str(folder),'-o',str(output),'--from',str(w['start']+r['offset']),'--to',str(w['end']+r['offset']),'--width','960','--height','540','--fps','30','--no-telemetry']
  if not output.exists():
   at=time.perf_counter()
   with log.open('w') as stream:completed=subprocess.run(args,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
   receipts.append(dict(id=r['id'],difficulty=r['difficulty'],role=w['role'],command=args,exit_code=completed.returncode,wall_seconds=time.perf_counter()-at,log_path=str(log)));(BASE/'render-receipts.json').write_text(json.dumps(receipts,indent=2))
   if completed.returncode:print('FAILED',r['title'],w['role'],flush=True);continue
  sheetpath=folder/f'{w["role"]}-sheet.png'
  if sheetpath.exists():continue
  sheet=Image.new('RGB',(1440,610),'#10141b');draw=ImageDraw.Draw(sheet)
  for j in range(6):
   p=folder/f'{w["role"]}-{j}.png';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(j*2),'-i',str(output),'-frames:v','1','-vf','scale=480:270',str(p)],check=True)
   if not p.exists():continue
   x=j%3*480;y=j//3*305;sheet.paste(Image.open(p),(x,y+35));draw.text((x+5,y+4),f'{r["title"]} {r["difficulty"]} | {w["start"]+r['offset']+j*2:.3f}s audio',font=font,fill='white')
  sheet.save(sheetpath);print('SHEET',r['title'],r['difficulty'],w['role'],flush=True)
