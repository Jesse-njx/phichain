"""Behavioral controls and data invariants, not a transcription accuracy score."""
import json
from pathlib import Path
import numpy as np
from analyze import features,drum_candidates,SR
OUT=Path(__file__).resolve().parent
results={}
silence=np.zeros(SR*3,dtype=np.float32)
f=features(silence);assert not drum_candidates(f,f);results['digital_silence_events']=0
# A finite decaying percussion-like signal should preserve detected times under
# global gain changes, including a quiet input. This guards against a fixed dB gate.
rng=np.random.default_rng(20261102);y=silence.copy()
for time in [.5,1.2,2.1]:
 n=int(.12*SR);y[int(time*SR):int(time*SR)+n]+=rng.normal(0,1,n)*np.exp(-np.arange(n)/SR/.018)
def detected(y):
 f=features(y);return [n['time_seconds'] for n in drum_candidates(f,f) if not n['rejection_reasons']]
full=detected(y);quiet=detected(y*.01)
assert len(full)==3 and np.allclose(full,quiet,atol=1e-6),(full,quiet)
results['gain_invariance']=dict(gain=.01,detected_full=full,detected_quiet=quiet)
# Source leakage must not create hits in a digitally silent mixture.
assert all(n['rejection_reasons'] for n in drum_candidates(features(y),features(silence)))
results['silent_mix_rejects_source_residual']=True
t=np.arange(SR*3)/SR;tone=np.sin(t*2*np.pi*237)*.2
tone_hits=[x for x in detected(tone) if .2<x<2.8]
assert not tone_hits,tone_hits
results['stationary_tone_interior_drum_events']=0
a=json.loads((OUT/'analysis.json').read_text());events=a['events'];duration=a['source']['duration_seconds']
assert len(a['tracks'])==2 and set(e['track'] for e in events)=={0,1}
assert len({e['id'] for e in events})==len(events)
for e in events:
 assert 0<=e['time_seconds']<=e['display_end_seconds']<=e['end_seconds']<=duration
 assert 0<=e['intensity']<=100 and not e['rejection_reasons']
 if e['track']==1:assert e['evidence']['learned_onset']>=a['parameters']['onset_threshold']
for track in [0,1]:
 row=[e['time_seconds'] for e in events if e['track']==track];assert np.all(np.diff(row)>0)
melody=[e for e in events if e['track']==1];drums=np.array([e['time_seconds'] for e in events if e['track']==0])
results['melody_events_over_30ms_from_nearest_drum']=sum(bool(np.min(abs(drums-e['time_seconds']))>.03) for e in melody)
results['events']=len(events);results['tracks']=2
results['scope']='Synthetic negative/positive controls and serialization invariants; no human-labeled acoustic precision or recall measurement.'
(OUT/'analysis-verification.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
