import os,logging
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba');logging.disable(logging.WARNING)
from pathlib import Path
import numpy as np
from basic_pitch.note_creation import output_to_notes_polyphonic,model_frames_to_time
P=Path(__file__).resolve().parent.parent/'override-voices-v3'
for source in ['vocals','other']:
 z=np.load(P/f'{source}-model-output.npz'); frames=z['note'];times=model_frames_to_time(len(frames))
 print(source)
 for threshold in [.5,.6,.7]:
  n=output_to_notes_polyphonic(frames.copy(),z['onset'].copy(),threshold,.4,7,False,1600,90,False,energy_tol=3)
  values=[]
  for s,e,p,a in n:
   sl=frames[s:e];dominance=np.mean(sl[:,p-21]>=np.max(sl,axis=1)*.95)
   values.append([a,dominance])
  v=np.array(values);print(threshold,len(n),'mean act',np.percentile(v[:,0],[25,50,75]),'dominant',sum((v[:,0]>.5)&(v[:,1]>.65)))
