import sys,json
from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'override-two-track-v4'))
from analyze import features,DT
s=P.parent/'override-voices-v3/aligned-stems/drums.wav';y,sr=sf.read(s,dtype='float32');f=features(resample_poly(y.mean(1),1,2));flux=f['flux'];ref=np.percentile(flux,99)
for half in [0,1]:
 tt=np.arange(.0251867+half*30/204,138.53,60/204)
 val=np.array([max(flux[max(0,round(t/DT)-2):round(t/DT)+3])/ref for t in tt])
 print('phase',half,'quantile',np.percentile(val,[0,1,5,10,25,50,75,99]).round(3))
 for s in range(0,128,16):
  v=val[(tt>=s)&(tt<s+16)];print(s,'median',round(float(np.median(v)),3),'min',round(float(min(v)),3),'strong',round(float(np.mean(v>.2)),3))
 if half==0:(P/'pulse-support.json').write_text(json.dumps([dict(time_seconds=float(t),attack=float(v)) for t,v in zip(tt,val)],indent=2))
