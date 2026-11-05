"""Make labelled contact sheets of official study renders only."""
from pathlib import Path
import subprocess, math, json
from PIL import Image,ImageDraw,ImageFont
r=Path(__file__).resolve().parent
try:font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',18)
except OSError:font=ImageFont.load_default()
specs=[('bounded-reference',12,15,4),('distorted-reference',94,20,5),('cycle-in-rest-reference',77,17,5)]
specs += [(s['name'],s['start'],s['end']-s['start'],4) for s in json.loads((r/'deep_reference_specs.json').read_text())]
specs += [('der-schneid-ending',133,18,5)]
for name,start,length,cols in specs:
 n=math.ceil(length/2);w=480;h=270;sheet=Image.new('RGB',(cols*w,math.ceil(n/cols)*(h+28)),'#10141b');d=ImageDraw.Draw(sheet)
 frames=r/'study-frames'/name;frames.mkdir(parents=True,exist_ok=True)
 for j in range(n):
  p=frames/f'{j:02}.png';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(j*2),'-i',str(r/f'{name}.mp4'),'-frames:v','1','-vf','scale=480:270',str(p)],check=True)
  if not p.exists():continue
  x=j%cols*w;y=j//cols*(h+28);sheet.paste(Image.open(p),(x,y+28));d.text((x+7,y+5),f'Official study | {start+j*2:.3f} s',font=font,fill='white')
 sheet.save(r/f'{name}-labelled.png')
 print(r/f'{name}-labelled.png')
