"""Read-only source measurements and excerpts of existing native reference renders."""
from pathlib import Path
import json,math,bisect,hashlib,subprocess,io
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
specs=[
 ('verruckt-relay','Verruckt.Raimukun.0',238,77,89,'../research/reference-studies/verruckt-two-finger/reference.mp4'),
 ('schneid-pair-waves','DerSchneid.Ωμεγα.0',222,126,142,'../research/reference-studies/der-schneid-in/der-schneid-IN.mp4'),
 ('schneid-scene-handoff','DerSchneid.Ωμεγα.0',222,286,306,'../research/reference-studies/der-schneid-in/der-schneid-IN.mp4'),
 ('schneid-breath','DerSchneid.Ωμεγα.0',222,238,258,'../research/reference-studies/der-schneid-in/der-schneid-IN.mp4')]
records=[]
for key,song,bpm,lo,hi,video in specs:
    source=ROOT/'../research/arrangement-training/raw'/song/'IN.json';raw=source.read_bytes();chart=json.loads(raw);lines=chart['judgeLineList'];cache={}
    for i,l in enumerate(lines):
        assert l['bpm']==bpm
        for kind in ['judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents']:
            es=sorted(l[kind],key=lambda e:e['startTime']);cache[i,kind]=([e['startTime']/32 for e in es],es)
    def val(i,kind,field,t):
        starts,es=cache[i,kind];e=es[max(0,bisect.bisect_right(starts,t)-1)];a=e['startTime']/32;b=e['endTime']/32;u=max(0,min(1,(t-a)/(b-a))) if b>a else 1
        end='end2' if field=='start2' else 'end';return e[field]+(e[end]-e[field])*u
    samples=[]
    for step in range((hi-lo)*16+1):
        t=lo+step/16;visible=[]
        for i,l in enumerate(lines):
            x=(val(i,'judgeLineMoveEvents','start',t)-.5)*1350;y=(val(i,'judgeLineMoveEvents','start2',t)-.5)*900
            angle=val(i,'judgeLineRotateEvents','start',t);alpha=val(i,'judgeLineDisappearEvents','start',t);r=math.radians(angle)
            intersects=abs(-math.sin(r)*x+math.cos(r)*y)<=abs(math.sin(r))*675+abs(math.cos(r))*450
            if alpha>.05 and intersects:
                visible.append({'line':i,'x':x,'y':y,'angle':angle,'alpha':alpha,'heads_in_excerpt':sum(lo<=n['time']/32<hi for field in ['notesAbove','notesBelow'] for n in l[field])})
        samples.append({'beat':t,'lines':visible})
    duration=(hi-lo)*60/bpm;out=P/'clips'/f'{key}.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(lo*60/bpm),'-i',str(ROOT/video),'-t',str(duration),'-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)],check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'],check=True,capture_output=True)
    beats=[lo+(hi-lo)*i/16 for i in range(16)];w,h=384,216
    sheet=Image.new('RGB',(4*w,4*(h+24)),(20,20,24));draw=ImageDraw.Draw(sheet)
    for i,b in enumerate(beats):
        r=subprocess.run(['ffmpeg','-v','error','-ss',str((b-lo)*60/bpm),'-i',str(out),'-frames:v','1','-vf',f'scale={w}:{h}','-f','image2pipe','-vcodec','png','-'],check=True,capture_output=True)
        im=Image.open(io.BytesIO(r.stdout));x=i%4*w;y=i//4*(h+24);sheet.paste(im,(x,y));draw.text((x+5,y+h+4),f'{key} beat{b:g} / {b*60/bpm:.3f}s',fill='white')
    sheet.save(P/'frames'/f'{key}.jpg')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()
    records.append({'key':key,'source':str(source),'source_sha256':hashlib.sha256(raw).hexdigest(),'native_video':video,'beats':[lo,hi],'seconds':[lo*60/bpm,hi*60/bpm],'samples':samples,'note':'Visibility is source alpha plus infinite-line viewport intersection approximation; native frames are visual evidence. Musical instrument/emotion claims are not inferred.'})
    print(key,flush=True)
(P/'evidence.json').write_text(json.dumps(records,indent=2))
