import json,numpy as np
from pathlib import Path
from scipy.optimize import minimize_scalar
P=Path(__file__).resolve().parent;A=json.loads((P.parent/'override-two-track-v4/analysis.json').read_text())
d=[e for e in A['events'] if e['source']=='drums'];t=np.array([e['time_seconds'] for e in d]);w=np.array([e['evidence']['linear_attack'] for e in d]);strong=w>.65
for sub in [1,2]:
 def coherence(bpm):
  z=np.exp(2j*np.pi*t/(60/bpm/sub));return abs(np.sum(w*w*z))/sum(w*w)
 grid=np.linspace(202,206,4001);best=grid[np.argmax([coherence(b) for b in grid])];r=minimize_scalar(lambda bpm:-coherence(bpm),bounds=(best-.002,best+.002),method='bounded');period=60/r.x/sub
 phase=float(np.angle(np.sum(w*w*np.exp(2j*np.pi*t/period)))*period/(2*np.pi)%period)
 dist=(t-phase+period/2)%period-period/2
 print(dict(sub=sub,bpm=r.x,phase=phase,period=period,coherence=-r.fun,strong_fit_ms=np.percentile(abs(dist[strong])*1000,[50,90,95]).tolist(),fit_fraction=float(np.mean(abs(dist)<.025))))
 print('block percent matched',[round(float(np.mean(abs(dist[(t>=s)&(t<s+16)])<.025)),3) for s in range(0,128,16)])
 if sub==1:(P/'rhythm-fit.json').write_text(json.dumps(dict(bpm=r.x,phase=phase,period=period,coherence=-r.fun),indent=2))
