"""Organize pretrained source transcriptions into independently timed voice estimates."""
import os,json,hashlib
from pathlib import Path
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba')
import numpy as np
import soundfile as sf
import librosa
from scipy.signal import find_peaks,resample_poly
from scipy.ndimage import median_filter,uniform_filter1d

OUT=Path(__file__).resolve().parent
SR,HOP,FFT=22050,110,1024
STEP=HOP/SR
TRACKS=['Vocal melody estimate','Instrumental upper voice estimate','Harmonic support estimate','Bass line estimate','Drum attacks']


def acoustic(name):
    y,sr=sf.read(OUT/'aligned-stems'/f'{name}.wav',dtype='float32')
    y=resample_poly(y.mean(1),1,2)
    spec=np.abs(librosa.stft(y,n_fft=FFT,hop_length=HOP))
    mel=librosa.feature.melspectrogram(S=spec*spec,sr=SR,n_fft=FFT,n_mels=32)
    log=np.log(np.maximum(mel,1e-8)).T
    flux=np.maximum(np.diff(log,axis=0,prepend=log[:1]),0).mean(1)
    rms=librosa.feature.rms(S=spec,frame_length=FFT,hop_length=HOP)[0]
    env=flux/max(float(np.percentile(flux,95)),1e-8)
    peaks,_=find_peaks(env,height=median_filter(env,size=61)+.2,prominence=.2,distance=round(.045/STEP))
    peaks=peaks[rms[peaks]>max(float(rms.max())*.025,1e-6)]
    times=[]
    for k in peaks:
        a,b,c=flux[k-1:k+2];den=a-2*b+c
        f=float(np.clip(.5*(a-c)/den,-.5,.5)) if abs(den)>1e-9 else 0
        times.append((k+f)*STEP)
    db=20*np.log10(np.maximum(rms,1e-9))
    local=uniform_filter1d(db,round(.6/STEP))
    active=db[db>db.max()-45]
    ref=np.percentile(active,95)
    return dict(peaks=np.array(times),rms=rms,db=db,local=local,energy_ref=ref,env=env)


def groups(notes):
    grouped=[]
    for n in sorted(notes,key=lambda n:(n['start_seconds'],n['midi_pitch'])):
        if not grouped or n['start_seconds']-grouped[-1][0]['start_seconds']>.025:grouped.append([])
        grouped[-1].append(n)
    return grouped


def voice(grouped,kind):
    # One note per onset group, chosen as a smooth salient line across context.
    # This is an explicit heuristic, NOT a pretrained main-melody classifier.
    prev=[];paths=[];last=None
    for i,g in enumerate(grouped):
        pitches=np.array([n['midi_pitch'] for n in g])
        score=np.log(np.maximum([n['activation'] for n in g],.01))
        if kind=='upper':score+=.025*np.clip(pitches-60,-24,24)
        if kind=='bass':score-=.015*np.clip(pitches-45,-24,24)
        if kind=='vocal':score-=.008*np.maximum(pitches-84,0)
        if i and g[0]['start_seconds']-grouped[i-1][0]['start_seconds']<.65:
            costs=prev[:,None]-.035*np.minimum(abs(last[:,None]-pitches[None,:]),24)
            back=np.argmax(costs,axis=0);score+=costs[back,np.arange(len(g))]
        else:
            back=np.full(len(g),int(np.argmax(prev)) if len(prev) else -1)
        paths.append(back);prev=score;last=pitches
    chosen=[];j=int(np.argmax(prev))
    for i in range(len(grouped)-1,-1,-1):
        chosen.append(grouped[i][j]);j=int(paths[i][j])
    return chosen[::-1]


def main():
    align=json.loads((OUT/'alignment.json').read_text());duration=align['canonical_samples']/align['sample_rate']
    evidence={n:acoustic(n) for n in ['vocals','bass','other','drums']}
    raw={n:json.loads((OUT/f'{n}-transcription.json').read_text())['notes'] for n in ['vocals','bass','other']}
    for name in raw:
        raw[name]=[n for n in raw[name] if 0<=n['start_seconds']<min(n['end_seconds'],duration)]
    vg,bg,og=groups(raw['vocals']),groups(raw['bass']),groups(raw['other'])
    vocal,bass,upper=voice(vg,'vocal'),voice(bg,'bass'),voice(og,'upper')
    upper_ids={n['id'] for n in upper}
    events=[]

    def add(notes,source,track,kind):
        first=min(n['start_seconds'] for n in notes);end=min(duration,max(n['end_seconds'] for n in notes))
        ev=evidence[source];close=ev['peaks'][abs(ev['peaks']-first)<=.025]
        t=float(close[np.argmin(abs(close-first))]) if len(close) else first
        t=max(0,min(t,end-.001))
        frame=min(len(ev['rms'])-1,round(t/STEP))
        relative=float(np.clip((ev['db'][frame]-ev['energy_ref']+36)/36,0,1))
        accent=float(np.clip((ev['db'][frame]-ev['local'][frame]+3)/12,0,1))
        attack=float(np.clip(ev['env'][frame],0,1))
        events.append(dict(id=f'voice-event-{len(events):05d}',source=source,track=track,
            time_seconds=t,transcribed_start_seconds=first,end_seconds=end,
            pitches=sorted(set(n['midi_pitch'] for n in notes)),source_note_ids=[n['id'] for n in notes],
            event_kind=kind,role=TRACKS[track],role_status='heuristic_estimate',
            model_activation=float(np.mean([n['activation'] for n in notes])),confidence=None,
            intensity=round(100*(.5*relative+.3*attack+.2*accent),1),
            intensity_basis=dict(relative_source_energy=relative,attack=attack,local_accent=accent),
            reasons=['Pretrained pitch-note evidence on aligned '+source+' source',
                     'Source-local attack refinement within 25 ms' if len(close) else 'Transcribed pitch onset preserved without forcing an attack match',
                     kind]))

    for n in vocal:add([n],'vocals',0,'dominant_vocal_pitch_line')
    for n in upper:add([n],'other',1,'salient_smooth_upper_pitch_line')
    for g in og:
        remaining=[n for n in g if n['id'] not in upper_ids]
        if remaining:add(remaining,'other',2,'remaining_simultaneous_pitch_group')
    for n in bass:add([n],'bass',3,'dominant_bass_pitch_line')
    for t in evidence['drums']['peaks']:
        if not 0<=t<duration:continue
        ev=evidence['drums'];k=round(t/STEP)
        energy=float(np.clip((ev['db'][k]-ev['energy_ref']+36)/36,0,1));attack=float(np.clip(ev['env'][k],0,1))
        events.append(dict(id=f'voice-event-{len(events):05d}',source='drums',track=4,time_seconds=float(t),
            transcribed_start_seconds=None,end_seconds=float(t),pitches=[],source_note_ids=[],event_kind='percussive_attack',
            role=TRACKS[4],role_status='source_estimate',model_activation=None,confidence=None,
            intensity=round(100*(.6*energy+.4*attack),1),intensity_basis=dict(relative_source_energy=energy,attack=attack),
            reasons=['Independent drum-source attack; not merged with other source events']))
    # Keep independent transcribed attacks distinct when both propose snapping
    # to the same source peak. Refinement cannot cross original midpoints.
    for track in range(4):
        row=sorted([e for e in events if e['track']==track],key=lambda e:e['transcribed_start_seconds'])
        raw_times=np.array([e['transcribed_start_seconds'] for e in row])
        low=np.r_[0,(raw_times[:-1]+raw_times[1:])/2+.0001]
        high=np.r_[(raw_times[:-1]+raw_times[1:])/2-.0001,duration]
        for i,e in enumerate(row):
            t=float(np.clip(e['time_seconds'],low[i],min(high[i],e['end_seconds']-.001)))
            e['timing_refinement_guard_applied']=abs(t-e['time_seconds'])>1e-9
            e['time_seconds']=t
    events.sort(key=lambda e:(e['time_seconds'],e['track']))
    for track in range(5):
        row=[e for e in events if e['track']==track]
        for i,e in enumerate(row):
            # Display monophonic carrier durations without overwriting acoustic ends.
            end=min(e['end_seconds'],row[i+1]['time_seconds']-.008 if i+1<len(row) else duration)
            e['display_end_seconds']=max(e['time_seconds'],end)
            e['display_type']='hold' if end-e['time_seconds']>=.18 else 'tap'
            if track==1:
                active=any(v['time_seconds']-.12<=e['time_seconds']<=v['end_seconds']+.12 for v in events if v['track']==0)
                e['role']='instrumental_countervoice_candidate' if active else 'instrumental_lead_candidate'
    old_path=OUT.parent/'override/analysis.json';old=json.loads(old_path.read_text())
    assert old['source'].get('decoded_sha256')==align['canonical_sha256']
    data=dict(schema_version=2,title='Override — independent voice analysis',source=dict(path=align['canonical_source'],sha256=align['canonical_sha256'],duration_seconds=duration),
        tracks=[dict(index=i,name=n,count=sum(e['track']==i for e in events)) for i,n in enumerate(TRACKS)],events=events,
        climax_regions=old.get('climax_regions',[]),climax_provenance='Carried forward unchanged: earlier mix-energy/texture heuristic, not newly validated by transcription.',
        method='HTDemucs source estimates → Basic Pitch ONNX transcription → salient continuous voice estimates → independent source-local timing',
        limitations=['Instrumental upper voice vs harmonic support is heuristic; not a trained melody/accompaniment separator.',
                    'Dominant vocal and bass displays omit secondary simultaneous hypotheses; full pretrained outputs are retained separately.',
                    'Intensities are heuristic relative emphasis within each source, not calibrated across sources.',
                    'Source leakage, octave errors, missed notes and false notes remain possible. Confidence is intentionally uncalibrated/null.',
                    'No global event cap, cross-source time suppression, beat snapping, or gameplay selection. Holds visualize duration only.'])
    (OUT/'analysis.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    summary=dict(duration=duration,total_events=len(events),tracks=data['tracks'],holds=sum(e['display_type']=='hold' for e in events),
        climax_regions=data['climax_regions'],sources_transcribed={k:len(v) for k,v in raw.items()})
    (OUT/'full-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
