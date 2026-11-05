"""Read-only audio/chart research. Never authors or edits a chart."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'mpl-cache'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT/'numba-cache'))
import json, hashlib
import numpy as np
import librosa
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SONGS = [
 ('Crush BETA','CrushBETA.shadow_bling.ogg',0,[(99.496875,110.1)]),
 ("Aphrodite's Child",'AphroditesChildshortver.RUQOA.ogg',1,[(61.875,70.78125),(151.875,163.4765625)]),
 ('Frozen Heart','FrozenHeart.A39沙包P.ogg',2,[(21.405405,33.081081),(174.486486,184.864865)]),
 ('BRAIN HACKER','BRAINHACKER.SOMON.ogg',4,[(62.278481,74.43038)]),
 ('Ranbu','亂舞.NekockLK.ogg',6,[(50.816327,61.836735),(110.204082,121.22449)]),
 ('Override','/Users/jesse/Music/PhiChain/Override-opening/music.mp3',None,[]),
]

def main():
 (ROOT/'librosa').mkdir(exist_ok=True)
 for title,filename,index,gaps in SONGS:
  key=title.lower().replace(' ','-').replace("'",'')
  out=ROOT/'librosa'/f'{key}.json'
  if out.exists():
   print('cached',key,flush=True);continue
  path=Path(filename) if filename.startswith('/') else ROOT/'audio'/filename
  print('Analyzing',title,flush=True)
  sr=22050;hop=256
  y,_=librosa.load(path,sr=sr,mono=True)
  S=np.abs(librosa.stft(y,n_fft=2048,hop_length=hop))
  H,P=librosa.decompose.hpss(S)
  rms=librosa.feature.rms(S=S)[0]
  hrms=librosa.feature.rms(S=H)[0];prms=librosa.feature.rms(S=P)[0]
  t=librosa.frames_to_time(np.arange(S.shape[1]),sr=sr,hop_length=hop)
  onset=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop)
  centroid=librosa.feature.spectral_centroid(S=S,sr=sr)[0]
  chroma=librosa.feature.chroma_stft(S=H**2,sr=sr,hop_length=hop)
  mfcc=librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S**2,sr=sr),ref=np.max),n_mfcc=13)
  tempo,beats=librosa.beat.beat_track(onset_envelope=onset,sr=sr,hop_length=hop,trim=False)
  onsets=librosa.onset.onset_detect(onset_envelope=onset,sr=sr,hop_length=hop,units='time')
  # Two-second before/after feature contrast; candidate boundaries, not labels.
  feat=np.vstack([mfcc,chroma*20])
  feat=(feat-np.mean(feat,axis=1,keepdims=True))/(np.std(feat,axis=1,keepdims=True)+1e-6)
  half=round(sr*2/hop);cum=np.cumsum(feat,axis=1)
  novelty=np.zeros(len(t))
  for j in range(half,len(t)-half):
   novelty[j]=np.linalg.norm((cum[:,j+half]-cum[:,j])/half-(cum[:,j]-cum[:,j-half])/half)
  novelty=gaussian_filter1d(novelty,round(.2*sr/hop))
  peaks,_=find_peaks(novelty,distance=int(3*sr/hop),prominence=.7)
  chart=None
  if index is not None:
   chart=json.loads(Path(f'/tmp/phigros-research-{index}.json').read_text())
   bpm=chart['judgeLineList'][0]['bpm']
  else: bpm=204
  def window(a,b):
   mask=(t>=a)&(t<b)
   return {'from':round(a,4),'to':round(b,4),'rms_dbfs':round(float(20*np.log10(np.sqrt(np.mean(rms[mask]**2))+1e-10)),2),
    'harmonic_rms_dbfs':round(float(20*np.log10(np.sqrt(np.mean(hrms[mask]**2))+1e-10)),2),
    'percussive_rms_dbfs':round(float(20*np.log10(np.sqrt(np.mean(prms[mask]**2))+1e-10)),2),
    'onset_strength_mean':round(float(onset[mask].mean()),3),'detected_onsets_per_second':round(float(np.sum((onsets>=a)&(onsets<b))/(b-a)),2),
    'centroid_hz':round(float(centroid[mask].mean()),1)}
  details=[]
  for a,b in gaps:
   context=8*60/bpm
   windows={'before':window(max(0,a-context),a),'gap':window(a,b),'after':window(b,min(len(y)/sr,b+context))}
   for k in range(3):windows[f'gap_third_{k+1}']=window(a+(b-a)*k/3,a+(b-a)*(k+1)/3)
   details.append({'from':a,'to':b,'windows':windows,'nearby_changes':[{'seconds':round(float(t[p]),3),'strength':round(float(novelty[p]),3)} for p in peaks if a-5<t[p]<b+5]})
  data={'title':title,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duration':len(y)/sr,'librosa_version':librosa.__version__,
   'method':'22050 Hz mono, 2048 FFT, 256 hop; median HPSS is harmonic/percussive texture separation, not instrument separation. Onset rate is a feature, not playable note count. Boundaries are 2s-window MFCC/chroma contrasts.',
   'estimated_tempo':float(np.asarray(tempo).ravel()[0]),'chart_bpm':bpm,'beats':librosa.frames_to_time(beats,sr=sr,hop_length=hop).tolist(),
   'onsets':onsets.tolist(),'candidate_changes':[{'seconds':round(float(t[p]),3),'strength':round(float(novelty[p]),3)} for p in peaks],
   'gaps':details,'four_second_windows':[window(a,min(a+4,len(y)/sr)) for a in np.arange(0,len(y)/sr,4)]}
  out.write_text(json.dumps(data,indent=2,ensure_ascii=False))
  np.savez_compressed(ROOT/'librosa'/f'{key}.npz',time=t,rms=rms,harmonic_rms=hrms,percussive_rms=prms,onset=onset,centroid=centroid,chroma=chroma,novelty=novelty)
  fig,axes=plt.subplots(4,1,figsize=(15,9),sharex=True)
  for v,label in [(rms,'Mix'),(hrms,'Harmonic texture'),(prms,'Percussive texture')]:axes[0].plot(t,20*np.log10(gaussian_filter1d(v,10)+1e-8),label=label,lw=.8)
  axes[0].set_ylim(-65,0);axes[0].set_ylabel('RMS dBFS');axes[0].legend(loc='lower left',ncol=3)
  axes[1].plot(t,gaussian_filter1d(onset,8));axes[1].set_ylabel('Onset strength')
  axes[2].imshow(chroma,origin='lower',aspect='auto',extent=[0,t[-1],0,12],cmap='magma');axes[2].set_ylabel('Chroma')
  axes[3].plot(t,novelty);axes[3].set_ylabel('Feature change');axes[3].set_xlabel('Audio seconds')
  for ax in axes:
   for a,b in gaps:ax.axvspan(a,b,color='cyan',alpha=.18)
   ax.grid(alpha=.2)
  fig.suptitle(title+' — cyan = no-hit intervals (including hold tails)');fig.tight_layout();fig.savefig(ROOT/'librosa'/f'{key}.png',dpi=140);plt.close(fig)
  print('Saved',out, 'tempo',data['estimated_tempo'], 'gaps',details,flush=True)

if __name__=='__main__':main()
