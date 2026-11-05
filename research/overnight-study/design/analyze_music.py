"""Digital evidence, not a substitute for listening or playtesting."""
import json, subprocess, pathlib, math
import numpy as np
from PIL import Image,ImageDraw
ROOT=pathlib.Path(__file__).resolve().parents[1]
audio=ROOT/'corpus/music/RetributionCycleofRedemption.ArdolfvsDaily天利.ogg'
a=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(audio),'-f','f32le','-ac','1','-ar','22050','-']),dtype='<f4')
sr=22050;hop=256;nfft=2048
frames=np.lib.stride_tricks.sliding_window_view(a,nfft)[::hop]
spec=abs(np.fft.rfft(frames*np.hanning(nfft),axis=1)).astype(np.float32)
times=(np.arange(len(spec))*hop+nfft/2)/sr
freq=np.fft.rfftfreq(nfft,1/sr)
flux=np.maximum(spec[1:]-spec[:-1],0).sum(axis=1);flux=np.r_[0,flux]
rows=[]
c=json.loads((ROOT/'corpus/chart/RetributionCycleofRedemption.ArdolfvsDaily天利.0/IN.json').read_text())
notes=[dict(n,line=i,beat=n['time']/32,time_s=n['time']/32*60/l['bpm'],duration_s=n['holdTime']/32*60/l['bpm']) for i,l in enumerate(c['judgeLineList']) for side in ['notesAbove','notesBelow'] for n in l[side]]
for bar in range(math.ceil(times[-1]/(16*60/225))):
 start=bar*16*60/225;end=(bar+1)*16*60/225;mask=(times>=start)&(times<end);block=a[int(start*sr):int(end*sr)]
 sel=[n for n in notes if start<=n['time_s']<end]
 bands={name:float(spec[mask][:,(freq>=lo)&(freq<hi)].mean()) for name,lo,hi in [('bass',30,180),('body',180,1800),('air',1800,10000)]}
 rows.append(dict(four_bar=bar,beat_start=bar*16,time_start=round(start,3),time_end=round(end,3),rms=round(float(np.sqrt((block**2).mean())),4),**{k:round(v,3) for k,v in bands.items()},official_count=len(sel),official_types={str(k):sum(n['type']==k for n in sel) for k in range(1,5)}))
(ROOT/'design/audio-four-bar-evidence.json').write_text(json.dumps(rows,indent=2))
peaks=[]
for i in range(2,len(flux)-2):
 if flux[i]==max(flux[i-2:i+3]) and flux[i]>np.percentile(flux[max(0,i-86):i+87],75):peaks.append((float(times[i]),float(flux[i])))
(ROOT/'design/onset-peaks.json').write_text(json.dumps(peaks))
# Spectrogram in 16-beat panels; the 225-BPM bar grid and onset energy are explicit.
w=1600;h=1040;im=Image.new('RGB',(w,h),'#10141b');d=ImageDraw.Draw(im)
d.text((20,12),'Retribution Cycle of Redemption — digital evidence, 225 BPM (4-bar / 16-beat blocks)',fill='white')
for panel in range(4):
 start=panel*48;end=min(start+48,times[-1]);ids=np.where((times>=start)&(times<end))[0]
 # Log frequency bins.
 fi=np.unique(np.clip(np.round(np.geomspace(3,900,160)).astype(int),0,spec.shape[1]-1))
 z=np.log10(spec[ids][:,fi]+.01).T;z=(z-z.min())/(z.max()-z.min());rgb=np.stack([z*.9,z*.5,z*.12+.08],axis=-1)
 tile=Image.fromarray(np.uint8(rgb*255)).resize((1500,170));y=50+panel*245;im.paste(tile,(60,y))
 for beat in range(math.ceil(start*225/60/16)*16,math.ceil(end*225/60/16)*16,16):
  t=beat*60/225;x=60+int((t-start)/(end-start)*1500);d.line((x,y,x,y+170),fill='#b2cddd');d.text((x+2,y+172),f'b{beat} {t:.1f}s',fill='white')
 fl=flux[ids];fl=fl/max(fl.max(),1);points=[(60+i*1500/max(1,len(ids)-1),y+225-v*35) for i,v in enumerate(fl)];d.line(points,fill='#ffdf99',width=1)
 d.text((5,y),f'{start}s',fill='white')
im.save(ROOT/'design/audio-evidence.png')
print(json.dumps(rows,indent=2));print('audio length',len(a)/sr)
