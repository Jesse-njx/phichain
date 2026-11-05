"""12-second source-aware evidence probe, not a completed voice transcription."""
import os
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba')
from pathlib import Path
import json
import hashlib
import numpy as np
import soundfile as sf
import librosa
from scipy.signal import find_peaks,resample_poly,correlate
from scipy.ndimage import median_filter

OUT=Path(__file__).resolve().parent
START,END=48.,60.
SR,HOP,FFT=22050,110,1024
STEP=HOP/SR


def main():
    a=json.loads((OUT/'alignment.json').read_text()); original_sr=a['sample_rate']
    lag=a['stem_minus_pcm_samples']; streams=[]
    for name,source in a['stems'].items():
        path=Path(source['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
        with sf.SoundFile(path) as f:
            f.seek(round((START-.25)*original_sr)+lag)
            stereo=f.read(round((END-START+.5)*original_sr),dtype='float32')
        # Context avoids onset/filter-edge artifacts at the displayed clip boundary.
        sf.write(OUT/f'{name}-48-60.wav',stereo[round(.25*original_sr):-round(.25*original_sr)],original_sr)
        y=resample_poly(stereo.mean(1),1,2)
        s=np.abs(librosa.stft(y,n_fft=FFT,hop_length=HOP))
        mel=librosa.feature.melspectrogram(S=s*s,sr=SR,n_fft=FFT,n_mels=32)
        log=np.log(np.maximum(mel,1e-8)).T
        flux=np.maximum(np.diff(log,axis=0,prepend=log[:1]),0).mean(1)
        rms=librosa.feature.rms(S=s,frame_length=FFT,hop_length=HOP)[0]
        scale=max(float(np.percentile(flux,95)),1e-8)
        env=flux/scale
        baseline=median_filter(env,size=61)
        ix,_=find_peaks(env,height=baseline+.15,prominence=.15,distance=round(.04/STEP))
        ix=ix[rms[ix]>max(float(rms.max())*.025,1e-6)]
        events=[]
        for i,k in enumerate(ix):
            left,mid,right=flux[k-1:k+2];den=left-2*mid+right
            correction=float(np.clip(.5*(left-right)/den,-.5,.5)) if abs(den)>1e-9 else 0
            t=START-.25+(k+correction)*STEP
            if START<=t<END:
                events.append(dict(id=f'{name}-attack-{i:04d}',time_seconds=t,type='spectral_attack_candidate',
                    attack_strength=float(np.clip(env[k],0,1)*100),musical_role=None,
                    source=name,confidence=None,reason='Positive spectral change within a separated source; not proof of a new musical note.'))
        ac=correlate(env-env.mean(),env-env.mean(),mode='full',method='fft')[len(env)-1:]
        ac=ac/max(ac[0],1e-9)
        pi,_=find_peaks(ac,distance=round(.04/STEP));pi=pi[(pi*STEP>=.08)&(pi*STEP<=1.2)]
        best=sorted(pi,key=lambda k:ac[k],reverse=True)[:5]
        row=dict(source=name,role_status='unclassified',events=events,
            onset_repetition_candidates=[dict(period_seconds=float(k*STEP),autocorrelation=float(ac[k])) for k in best],
            repetition_caveat='Periods can be beat multiples/subdivisions or artifacts; no tempo or accompaniment role is assigned.')
        if name=='vocals':
            print('Tracking vocal pitch evidence',flush=True)
            f0,voiced,prob=librosa.pyin(y,fmin=90,fmax=1200,sr=SR,frame_length=1024,hop_length=220)
            contour=[]
            for i,(hz,is_voice,p) in enumerate(zip(f0,voiced,prob)):
                t=START-.25+i*220/SR
                if START<=t<END:
                    contour.append(dict(time_seconds=t,hz=float(hz) if np.isfinite(hz) and is_voice else None,
                        voiced_probability=float(p)))
            row['pitch_contour']=contour
            row['pitch_caveat']='Monophonic pYIN estimate on the vocal stem; not syllable segmentation, complete notes or proof of foreground role.'
        streams.append(row)
    # Keep both event identities even when attacks are nearly simultaneous.
    vocal=next(s for s in streams if s['source']=='vocals')['events']
    drums=next(s for s in streams if s['source']=='drums')['events']
    relations=[]
    if drums:
        for v in vocal:
            d=min(drums,key=lambda d:abs(d['time_seconds']-v['time_seconds']))
            relations.append(dict(vocal_event_id=v['id'],nearest_drum_event_id=d['id'],
                vocal_minus_drum_ms=(v['time_seconds']-d['time_seconds'])*1000,
                interpretation='Proximity relation only; events are neither merged nor snapped.'))
    data=dict(schema_version=1,range_seconds=[START,END],canonical_source_sha256=a['canonical_sha256'],
        stem_to_canonical_correction_seconds=-a['stem_minus_pcm_seconds'],source_separation_model='Existing htdemucs estimates',
        streams=streams,vocal_drum_timing_relations=relations,
        limitations=['Source separation is not musical-role separation.',
                    'other may contain foreground melody, chords, arpeggios and residual leakage together.',
                    'No global event cap, cross-source peak suppression, beat snapping or chart edits.',
                    'Independent source attacks still need phrase/note interpretation and leakage review.'])
    (OUT/'probe.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    offsets=np.array([r['vocal_minus_drum_ms'] for r in relations])
    counts={s['source']:len(s['events']) for s in streams}
    summary=dict(events_per_source=counts,vocal_attacks_with_nearest_drum_over_30ms=int(sum(abs(offsets)>.03*1000)),
                 vocal_attacks_total=len(vocal),merged_across_sources=0)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))


if __name__=='__main__':main()
