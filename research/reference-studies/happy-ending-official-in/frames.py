from pathlib import Path
from PIL import Image,ImageDraw
import subprocess,io
P=Path(__file__).resolve().parent;R=Path('/Users/jesse/Projects/PhiChain/phichain');O=P/'official-IN.mp4';E=R/'../charts/happy-ending/happy-ending-five-authors/E/preview/E.mp4'
F=P/'frames';F.mkdir(exist_ok=True)
def frame(v,t,w=384,h=216):
    data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(v),'-frames:v','1','-vf',f'scale={w}:{h}','-f','image2pipe','-vcodec','png','-'])
    return Image.open(io.BytesIO(data))
def sheet(v,beats,name,cols=4):
    w,h=384,216;out=Image.new('RGB',(w*cols,240*((len(beats)+cols-1)//cols)),(22,24,26));d=ImageDraw.Draw(out)
    for i,b in enumerate(beats):
        x=(i%cols)*w;y=(i//cols)*240;t=b*60/219;out.paste(frame(v,t),(x,y));d.text((x+5,y+h+4),f'beat {b:g} / {t:.3f}s',fill='white')
    out.save(F/name)
sheet(O,[19,40,49,74,105.5,130,145.5,185,225.5,280,300,326,354,465.5,523,557],'official-overview.jpg')
for start in [72,184,224,348,552]:sheet(O,[start+i*.25 for i in range(12)],f'official-{start}-sequence.jpg')
beats=[74,130,185,225.5,300,354,481,557]
out=Image.new('RGB',(768,240*len(beats)),(22,24,26));d=ImageDraw.Draw(out)
for i,b in enumerate(beats):
    for j,(v,label) in enumerate([(O,'OFFICIAL IN'),(E,'REJECTED E')]):
        out.paste(frame(v,b*60/219),(j*384,i*240));d.text((j*384+5,i*240+220),f'{label} beat{b:g} / {b*60/219:.3f}s',fill='white')
out.save(F/'official-vs-E.jpg');print(F)
