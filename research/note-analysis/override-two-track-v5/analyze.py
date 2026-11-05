"""Separate periodic main-drum evidence from a continuous foreground pitch path."""
import os,logging,json,hashlib,sys
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba');logging.disable(logging.WARNING)
from pathlib import Path
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
from scipy.ndimage import uniform_filter1d,binary_closing,binary_opening
from basic_pitch.note_creation import model_frames_to_time
from pitch_path import decode
OUT=Path(__file__).resolve().parent;V3=OUT.parent/'override-voices-v3';V4=OUT.parent/'override-two-track-v4'
# Import the unchanged acoustic feature routine without colliding with this module.
import importlib.util
spec=importlib.util.spec_from_file_location('v4_evidence',V4/'analyze.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
DT=v4.DT

def main():
    previous=json.loads((V4/'analysis.json').read_text());source=Path(previous['source']['path'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==previous['source']['sha256']
    y,sr=sf.read(source,dtype='float32');duration=len(y)/sr;mix=v4.features(resample_poly(y.mean(1),1,2));ac={}
    for name in ['vocals','other','drums']:
        y,sr=sf.read(V3/'aligned-stems'/f'{name}.wav',dtype='float32');ac[name]=v4.features(resample_poly(y.mean(1),1,2))
    decoded={};evidence={};paths={}
    for name in ['vocals','other']:
        z=np.load(V3/f'{name}-model-output.npz');t=model_frames_to_time(len(z['note']));indices=np.clip(np.round(t/DT).astype(int),0,len(mix['rms'])-1)
        ratio=ac[name]['rms'][indices]/np.maximum(mix['rms'][indices],1e-8)
        active=(ac[name]['rms'][indices]>ac[name]['ref']*10**(-28/20))&(ratio>.12)&(mix['rms'][indices]>mix['ref']*10**(-45/20))
        active=binary_closing(active,structure=np.ones(5))
        notes,path=decode(z['note'],z['onset'],t,active,floor=.34 if name=='vocals' else .36)
        decoded[name]=notes;paths[name]=path;evidence[name]=dict(t=t,frames=z['note'],onsets=z['onset'],active=active)
    # Source-role ownership is based on continuous vocal activity, not only the
    # few notes surviving a strong onset threshold. Short natural vowel gaps
    # remain in the same vocal phrase; instrumental sections use one other path.
    t=evidence['vocals']['t'];vocal=paths['vocals']>0
    vocal=binary_opening(vocal,structure=np.ones(4));vocal=binary_closing(vocal,structure=np.ones(24))
    candidates=[]
    for name,notes in decoded.items():
        for note in notes:
            note=dict(note,source=name,track=1,rejection_reasons=[])
            s,e=note['start_frame'],note['end_frame']
            if note['time_seconds']>=duration:continue
            note['end_seconds']=min(duration,note['end_seconds'])
            if name=='other' and np.mean(vocal[s:e])>.35:note['rejection_reasons'].append('vocal_foreground_owns_role')
            candidates.append(note)
    # In rare cross-source overlap, keep vocal notes and clip the instrumental
    # span; do not create a second melody lane or erase an entire vocal event.
    vocals=[n for n in candidates if n['source']=='vocals' and not n['rejection_reasons']]
    for n in candidates:
        if n['source']!='other' or n['rejection_reasons']:continue
        overlaps=[v for v in vocals if v['time_seconds']<n['end_seconds'] and v['end_seconds']>n['time_seconds']]
        if any(v['time_seconds']<=n['time_seconds'] for v in overlaps):n['rejection_reasons'].append('vocal_foreground_at_instrumental_start')
        elif overlaps:
            n['end_seconds']=min(v['time_seconds'] for v in overlaps)
            if n['end_seconds']-n['time_seconds']<.045:n['rejection_reasons'].append('insufficient_unmasked_duration')
    # Tempo/phase fit is global, then every proposed primary pulse is checked
    # against local source attack. No pulse is inserted in true low-activity gaps.
    olddrums=[e for e in previous['events'] if e['source']=='drums'];dt=np.array([e['time_seconds'] for e in olddrums]);weight=np.array([e['evidence']['linear_attack'] for e in olddrums])**2
    from scipy.optimize import minimize_scalar
    coherence=lambda bpm:abs(np.sum(weight*np.exp(2j*np.pi*dt/(30/bpm))))/sum(weight)
    grid=np.linspace(202,206,4001);best=grid[np.argmax([coherence(b) for b in grid])]
    opt=minimize_scalar(lambda b:-coherence(b),bounds=(best-.002,best+.002),method='bounded');sub=30/opt.x
    phase=float(np.angle(np.sum(weight*np.exp(2j*np.pi*dt/sub)))*sub/(2*np.pi)%sub)
    period=2*sub;flux=ac['drums']['flux'];ref=max(float(np.percentile(flux,99)),1e-9)
    offsets=[phase,phase+sub]
    def strength(offset):
        tt=np.arange(offset,duration,period)
        return float(np.median([max(flux[max(0,round(t/DT)-2):min(len(flux),round(t/DT)+3)]) for t in tt]))
    phase=max(offsets,key=strength)
    pulses=[]
    for t0 in np.arange(phase,duration,period):
        k=round(t0/DT);low=max(0,k-2);high=min(len(flux),k+3);pk=low+int(np.argmax(flux[low:high]));strength=float(flux[pk]/ref)
        why=[]
        if strength<.1:why.append('no_local_primary_drum_attack')
        if ac['drums']['rms'][pk]<ac['drums']['ref']*10**(-30/20):why.append('drum_source_inactive')
        if mix['rms'][pk]<mix['ref']*10**(-45/20):why.append('mix_near_silence')
        pulses.append(dict(time_seconds=float(t0),end_seconds=float(t0),source='drums',track=0,pitches=[],model_activation=None,
            rejection_reasons=why,evidence=dict(local_linear_attack=strength,nearest_peak_seconds=pk*DT,grid_offset_seconds=pk*DT-t0),
            boundary_kind='recurring_primary_drum_pulse'))
    candidates.extend(pulses);candidates.sort(key=lambda e:(e['time_seconds'],e['track']));events=[]
    for i,n in enumerate(candidates):
        n['id']=f'v5-evidence-{i:05d}';n['accepted']=not n['rejection_reasons']
        if not n['accepted']:continue
        e=dict(n);e['confidence']=None;k=min(len(mix['rms'])-1,round(e['time_seconds']/DT));f=ac[e['source']]
        end=min(len(f['rms']),max(k+1,round(e['end_seconds']/DT)))
        energy=float(np.clip((20*np.log10(max(float(np.median(f['rms'][k:end]))/f['ref'],1e-9))+30)/30,0,1))
        attack=float(np.clip(f['flux'][k]/max(np.percentile(f['flux'],99),1e-9),0,1));e['intensity']=round(100*(.65*energy+.35*attack),1)
        e['intensity_basis']=dict(relative_energy=energy,attack=attack)
        e['reasons']=['Globally recurring primary drum phase, confirmed by a local source attack'] if e['track']==0 else ['Continuous monophonic pitch path with an explicit silence state',e['boundary_kind'],'Vocal foreground' if e['source']=='vocals' else 'Instrumental foreground candidate']
        events.append(e)
    for track in [0,1]:
        row=[e for e in events if e['track']==track]
        for i,e in enumerate(row):
            e['display_end_seconds']=max(e['time_seconds'],min(e['end_seconds'],row[i+1]['time_seconds']-.008 if i+1<len(row) else duration))
            e['display_type']='hold' if e['display_end_seconds']-e['time_seconds']>=.18 else 'tap'
    tracks=[dict(index=i,name=name,count=sum(e['track']==i for e in events)) for i,name in enumerate(['Primary drum pulse','Main melody estimate'])]
    result=dict(schema_version=4,title='Override — recurring drum pulse and continuous melody',source=previous['source'],tracks=tracks,events=events,
        climax_regions=previous['climax_regions'],climax_provenance=previous['climax_provenance'],drum_rhythm=dict(bpm=float(opt.x),period_seconds=float(period),phase_seconds=phase,
            subdivision_coherence=float(-opt.fun),role='Primary recurring pulse, not all percussion attacks',unsupported_pulses=[p['time_seconds'] for p in pulses if p['rejection_reasons']]),
        method='Global drum recurrence with local evidence; framewise monophonic foreground pitch path with explicit silence and separate same-pitch onsets.',
        limitations=['The drum lane intentionally represents the recurring primary pulse; auxiliary percussion remains outside this role.',
                    'Melody path and vocal priority are heuristic, not human-validated transcription.','Short vibrato or source leakage can still create errors; instrumental foreground selection remains uncertain.',
                    'Climax and intensity remain unvalidated acoustic proxies; confidence is null.'])
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2));(OUT/'candidate-audit.json').write_text(json.dumps(candidates,indent=2))
    np.savez_compressed(OUT/'decoded-paths.npz',**paths)
    summary=dict(tracks=tracks,total=len(events),melody_sources={s:sum(e['source']==s for e in events) for s in ['vocals','other']},rhythm=result['drum_rhythm'],
        low_onset_melody_events=sum(e['track']==1 and e['learned_onset']<.65 for e in events))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
