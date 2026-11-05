"""Apply the validated experimental baseline to Override; no chart writes."""
import json
from pathlib import Path
import sys
import hashlib
import subprocess
import os
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba')
import numpy as np
import librosa
from scipy.signal import find_peaks

OUT=Path(__file__).resolve().parent
ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
SR,HOP,FFT=22050,220,1024


def main():
    source=OUT/'project/music.wav'
    y=np.frombuffer(subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(source),'-ac','1','-ar',str(SR),'-f','f32le','-']),dtype='<f4').copy()
    duration=len(y)/SR
    s=np.abs(librosa.stft(y,n_fft=FFT,hop_length=HOP))
    mel=librosa.feature.melspectrogram(S=s*s,sr=SR,n_fft=FFT,n_mels=32)
    log=np.log(np.maximum(mel,1e-8)).T
    delta=np.maximum(np.diff(log,axis=0,prepend=log[:1]),0)
    flux=delta.mean(1)
    peaks,_=find_peaks(flux,distance=round(.04/(HOP/SR)))
    keep=np.sort(peaks[np.argsort(flux[peaks],kind='stable')[-min(len(peaks),int(duration*8)):]])
    freq=librosa.mel_frequencies(n_mels=34)[1:-1]
    masks=[freq<250,(freq>=250)&(freq<2500),freq>=2500]
    names=['Low-band change (<250 Hz)','Mid-band change (250–2500 Hz)','High-band change (>2500 Hz)']
    scale=max(float(np.percentile(flux[keep],95)),1e-9)
    events=[]
    for i,k in enumerate(keep):
        a,b,c=flux[k-1],flux[k],flux[k+1]
        den=a-2*b+c
        f=float(np.clip(.5*(a-c)/den,-.5,.5)) if abs(den)>1e-9 else 0
        raw=k*HOP/SR; corrected=(k+f)*HOP/SR
        bands=[float(delta[k,m].mean()) for m in masks]
        strength=float(np.clip(flux[k]/scale,0,1)*100)
        events.append(dict(id=f'override-onset-{i:05d}',raw_time_seconds=raw,time_seconds=corrected,
            correction_ms=(corrected-raw)*1000,track=int(np.argmax(bands)),band_change_evidence=bands,
            attack_strength=strength,musical_intensity=None,confidence=None,
            reason='Positive log-mel spectral change; quadratic peak interpolation',
            display_type='tap',display_type_is_musical_classification=False))
    data=dict(schema_version=1,source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),duration_seconds=duration),
        method='Spectral flux + quadratic interpolation; validation-selected baseline, no CNN',
        settings=dict(sample_rate=SR,hop=HOP,fft=FFT,candidate_cap_per_second=8,minimum_peak_distance_seconds=.04),
        tracks=[dict(index=i,name=n,count=sum(e['track']==i for e in events)) for i,n in enumerate(names)],
        limitations=['Frequency bands are evidence labels, not instruments or separated sources.',
                    'Attack strength is a relative acoustic proxy, not validated musical emphasis.',
                    'No sustain, beat snapping, climax prediction, or gameplay note selection in this experiment.',
                    'Whole-song event cap is inherited from the controlled timing benchmark.'],events=events)
    (OUT/'analysis.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps(dict(duration=duration,count=len(events),tracks=data['tracks'],max_correction_ms=max(abs(e['correction_ms']) for e in events)),ensure_ascii=False))


if __name__=='__main__':main()
