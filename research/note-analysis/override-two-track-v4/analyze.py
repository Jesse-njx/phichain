"""Conservative two-role evidence, with explicit rejection and a no-note state.

Uses cached source/model outputs; thresholds are provisional, not precision labels.
No chart-density budget, grid completion, or deliberate arrangement rests.
"""
import os,logging,json,hashlib
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba')
logging.disable(logging.WARNING)
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa
from scipy.signal import find_peaks,resample_poly
from scipy.ndimage import median_filter,uniform_filter1d
from basic_pitch.note_creation import output_to_notes_polyphonic,model_frames_to_time

OUT=Path(__file__).resolve().parent
PREV=OUT.parent/'override-voices-v3'
SR,HOP,FFT=22050,110,1024
DT=HOP/SR
PARAMS=dict(onset_threshold=.65,frame_threshold=.4,min_note_frames=7,energy_tolerance_frames=3,
            infer_onsets=False,melodia_trick=False,vocal_min_activation=.5,other_min_activation=.52,
            min_dominance_fraction=.8,other_min_margin_fraction=.6,source_floor_db=-28,
            min_source_mix_ratio=.12,drum_attack_floor_fraction=.12,drum_local_excess_fraction=.12,
            drum_prominence_fraction=.12,drum_min_spacing_seconds=.065)


def features(y):
    s=np.abs(librosa.stft(y,n_fft=FFT,hop_length=HOP))
    rms=librosa.feature.rms(S=s,frame_length=FFT,hop_length=HOP)[0]
    # Linear magnitude changes preserve the amplitude of weak residuals.
    flux=np.maximum(np.diff(s,axis=1,prepend=s[:,:1]),0).sum(0)
    ref=max(float(np.percentile(rms,95)),1e-10)
    return dict(rms=rms,flux=flux,ref=ref)


def drum_candidates(f,mix):
    flux=f['flux'];ref=max(float(np.percentile(flux,99)),1e-10)
    base=median_filter(flux,size=101)
    peaks,props=find_peaks(flux,height=base+ref*PARAMS['drum_local_excess_fraction'],
        prominence=ref*PARAMS['drum_prominence_fraction'],distance=round(PARAMS['drum_min_spacing_seconds']/DT))
    result=[]
    for i,k in enumerate(peaks):
        why=[]
        energy=float(np.max(f['rms'][k:min(k+7,len(flux))]))
        if energy<f['ref']*10**(-24/20):why.append('source_below_audibility_proxy_floor')
        if flux[k]<ref*PARAMS['drum_attack_floor_fraction']:why.append('weak_absolute_attack')
        if mix['rms'][k]<mix['ref']*10**(-45/20):why.append('mix_near_silence')
        ratio=float(energy/max(mix['rms'][k],1e-9))
        if ratio<.1:why.append('weak_source_contribution')
        a,b,c=flux[k-1:k+2];den=a-2*b+c
        delta=float(np.clip(.5*(a-c)/den,-.5,.5)) if abs(den)>1e-9 else 0
        result.append(dict(time_seconds=(k+delta)*DT,end_seconds=(k+delta)*DT,source='drums',pitches=[],
            rejection_reasons=why,evidence=dict(linear_attack=float(flux[k]/ref),source_rms_ratio=energy/f['ref'],source_mix_rms_ratio=ratio,
                local_attack_excess=float((flux[k]-base[k])/ref),prominence=float(props['prominences'][i]/ref)),model_activation=None))
    return result


def merge_phrases(notes,gap=.45):
    spans=[]
    for n in sorted(notes,key=lambda n:n['time_seconds']):
        s,e=n['time_seconds']-.12,n['end_seconds']+.12
        if spans and s-spans[-1][1]<=gap:spans[-1][1]=max(spans[-1][1],e)
        else:spans.append([max(0,s),e])
    return spans


def main():
    align=json.loads((PREV/'alignment.json').read_text());path=Path(align['canonical_source'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==align['canonical_sha256']
    y,sr=sf.read(path,dtype='float32');assert sr==44100
    duration=len(y)/sr;mix=features(resample_poly(y.mean(1),1,2));ac={}
    for source in ['vocals','other','drums']:
        p=PREV/'aligned-stems'/f'{source}.wav';y,sr=sf.read(p,dtype='float32');assert sr==44100
        ac[source]=features(resample_poly(y.mean(1),1,2))
    candidates=[]
    for source in ['vocals','other']:
        z=np.load(PREV/f'{source}-model-output.npz');frames=z['note'];onsets=z['onset'];t=model_frames_to_time(len(frames))
        raw=output_to_notes_polyphonic(frames.copy(),onsets.copy(),PARAMS['onset_threshold'],PARAMS['frame_threshold'],
            PARAMS['min_note_frames'],False,1600,90,False,energy_tol=PARAMS['energy_tolerance_frames'])
        for s,e,p,activation in raw:
            if not 0<=t[s]<min(t[e],duration):continue
            pitch=p-21;f=frames[s:e];column=f[:,pitch]
            strongest=np.max(f,axis=1);competitor=np.max(np.concatenate([f[:,:max(0,pitch-1)],f[:,pitch+2:]],axis=1),axis=1)
            dominance=float(np.mean(column>=strongest*.95));margin=float(np.mean(column>=competitor*1.2))
            active_fraction=float(np.mean(column>=.4))
            k0=max(0,round(t[s]/DT));k1=min(len(mix['rms']),round(t[e]/DT)+1)
            src=ac[source];energy=float(np.median(src['rms'][k0:k1]));ratio=float(energy/max(float(np.median(mix['rms'][k0:k1])),1e-9))
            why=[]
            if activation<PARAMS['vocal_min_activation' if source=='vocals' else 'other_min_activation']:why.append('weak_sustained_pitch_activation')
            if active_fraction<.7:why.append('unstable_pitch_support')
            if dominance<PARAMS['min_dominance_fraction']:why.append('not_dominant_pitch')
            if source=='other' and margin<PARAMS['other_min_margin_fraction']:why.append('ambiguous_polyphonic_role')
            if energy<src['ref']*10**(PARAMS['source_floor_db']/20):why.append('source_below_audibility_proxy_floor')
            if ratio<PARAMS['min_source_mix_ratio']:why.append('weak_source_contribution')
            if float(np.median(mix['rms'][k0:k1]))<mix['ref']*10**(-45/20):why.append('mix_near_silence')
            candidates.append(dict(time_seconds=float(t[s]),end_seconds=float(min(t[e],duration)),source=source,pitches=[int(p)],model_activation=float(activation),
                rejection_reasons=why,evidence=dict(learned_onset=float(onsets[s,pitch]),dominance_fraction=dominance,margin_fraction=margin,
                    active_pitch_fraction=active_fraction,source_rms_ratio=energy/src['ref'],source_mix_rms_ratio=ratio)))
    # Vocal phrase occupancy persists across syllabic gaps. Do not turn every
    # gap between vocal notes into an opportunity to promote accompaniment.
    vocal=[n for n in candidates if n['source']=='vocals' and not n['rejection_reasons']]
    phrases=merge_phrases(vocal)
    for n in candidates:
        if n['source']=='other' and any(s<n['end_seconds'] and e>n['time_seconds'] for s,e in phrases):
            n['rejection_reasons'].append('vocal_phrase_owns_melody_role')
    # Require a phrase witness, rather than accepting an isolated residual pitch.
    eligible=[n for n in candidates if not n['rejection_reasons']]
    for n in eligible:
        neighbors=[m for m in eligible if m is not n and m['source']==n['source'] and abs(m['time_seconds']-n['time_seconds'])<=.8]
        if not neighbors and n['end_seconds']-n['time_seconds']<.25:n['rejection_reasons'].append('isolated_short_pitch_without_phrase_context')
    # Explicit competition on overlapping notes; unlike v3, empty groups are valid.
    accepted=[]
    for n in sorted([n for n in candidates if not n['rejection_reasons']],key=lambda n:n['model_activation'],reverse=True):
        if any(max(n['time_seconds'],m['time_seconds'])<min(n['end_seconds'],m['end_seconds'])-.03 for m in accepted):
            n['rejection_reasons'].append('competing_melody_hypothesis')
        else:accepted.append(n)
    candidates.extend(drum_candidates(ac['drums'],mix))
    candidates.sort(key=lambda n:(n['time_seconds'],n['source']))
    events=[]
    for i,n in enumerate(candidates):
        n['id']=f'evidence-{i:05d}';n['accepted']=not n['rejection_reasons']
        if not n['accepted']:continue
        e=dict(n);e['track']=0 if n['source']=='drums' else 1;e['confidence']=None
        evidence=n['evidence'];energy=float(np.clip((20*np.log10(max(evidence['source_rms_ratio'],1e-9))+30)/30,0,1))
        f=ac[n['source']];k=min(len(f['flux'])-1,round(n['time_seconds']/DT));attack=float(np.clip(f['flux'][k]/max(np.percentile(f['flux'],99),1e-9),0,1))
        e['intensity']=round(100*(.65*energy+.35*attack),1);e['intensity_basis']=dict(relative_energy=energy,attack=attack)
        e['role']='drums' if e['track']==0 else 'main_melody_estimate'
        e['reasons']=['Linear-amplitude source attack with local contrast and activity gates'] if e['track']==0 else ['Direct learned onset; no inferred onset or residual pitch filling','Sustained dominant pitch and source-activity evidence','Vocal foreground phrase' if n['source']=='vocals' else 'Unambiguous instrumental candidate outside vocal phrases']
        events.append(e)
    for track in [0,1]:
        row=[e for e in events if e['track']==track]
        for i,e in enumerate(row):
            e['display_end_seconds']=max(e['time_seconds'],min(e['end_seconds'],row[i+1]['time_seconds']-.008 if i+1<len(row) else duration))
            e['display_type']='hold' if e['display_end_seconds']-e['time_seconds']>=.18 else 'tap'
    old=json.loads((PREV/'analysis.json').read_text())
    tracks=[dict(index=i,name=name,count=sum(e['track']==i for e in events)) for i,name in enumerate(['Drums','Main melody estimate'])]
    result=dict(schema_version=3,title='Override — two-role conservative evidence',source=old['source'],tracks=tracks,events=events,
        climax_regions=old['climax_regions'],climax_provenance=old['climax_provenance'],parameters=PARAMS,
        vocal_phrase_intervals=phrases,method='Source-separated cached Basic Pitch logits, direct-onset decoding, dominance/activity/phrase abstention; independent linear-amplitude drum attacks.',
        limitations=['Unvalidated conservative heuristic; fewer events do not establish precision.','Ambiguous instrumental phrases are omitted, so melody recall can be low.',
        'Vocal priority is a role assumption, not a trained main-melody classifier.','Source audibility proxies do not establish human audibility.','Confidence is uncalibrated/null; intensity is an acoustic proxy.'])
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2));(OUT/'candidate-audit.json').write_text(json.dumps(candidates,indent=2))
    from collections import Counter
    summary=dict(total=len(events),tracks=tracks,sources=dict(Counter(e['source'] for e in events)),decoded_candidates=len(candidates),
        rejection_reasons=dict(Counter(r for n in candidates for r in n['rejection_reasons'])),old_total=len(old['events']))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
