"""Convert immutable reference charts for native PhiChain review; no chart edits."""
from pathlib import Path
import json, subprocess, os
from analyze_librosa import SONGS, ROOT
from PIL import Image,ImageDraw,ImageFont
REPO=ROOT.parents[1]
env=dict(os.environ,CARGO_MANIFEST_DIR=str(REPO/'phichain-renderer'))
converter=REPO/'target/debug/phichain-converter'
if not converter.exists():converter=REPO/'../apps/PhiChain.app/Contents/MacOS/phichain-converter'
font=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',16)
for title,filename,index,gaps in SONGS:
 if index is None:continue
 key=title.lower().replace(' ','-').replace("'",'')
 folder=ROOT/'references'/key;folder.mkdir(parents=True,exist_ok=True)
 if not (folder/'chart.json').exists():
  subprocess.run([str(converter),f'/tmp/phigros-research-{index}.json',str(folder/'chart.json'),'--from','official','--to','phichain','--no-easing-fitting','--round','6','--no-telemetry'],env=env,check=True)
 (folder/'meta.json').write_text(json.dumps(dict(name=title,composer='',charter='Original Phigros chart — reference',illustrator='',level='IN')))
 if not (folder/'music.ogg').exists():(folder/'music.ogg').symlink_to(ROOT/'audio'/filename)
 for j,(a,b) in enumerate(gaps):
  video=folder/f'gap-{j+1}.mp4';start=max(0,a-1);end=b+1
  if not video.exists():
   subprocess.run([str(REPO/'target/debug/phichain-renderer'),str(folder),'-o',str(video),'--from',str(start),'--to',str(end),'--width','960','--height','540','--fps','30','--hide-hit-effect','--no-telemetry'],env=env,check=True,timeout=180)
  times=[a-.2,a+1,a+(b-a)*.33,a+(b-a)*.66,b-.35,b+.25]
  sheet=Image.new('RGB',(1440,600),'#121827');draw=ImageDraw.Draw(sheet)
  for k,t in enumerate(times):
   img=folder/f'gap-{j+1}-frame-{k+1}.png'
   subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t-start),'-i',str(video),'-frames:v','1',str(img)],check=True)
   sheet.paste(Image.open(img).resize((480,270)),(k%3*480,k//3*300+30));draw.text((k%3*480+10,k//3*300+5),f'{t:.3f}s',font=font,fill='white')
  sheet.save(folder/f'gap-{j+1}-sheet.jpg')
  print('RENDERED',title,j+1,flush=True)
