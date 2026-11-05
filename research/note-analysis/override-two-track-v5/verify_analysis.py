"""Behavioral controls for pitch continuity and periodic primary-drum roles."""
import json
from pathlib import Path
import numpy as np
from pitch_path import decode
P=Path(__file__).resolve().parent
n=180;t=np.arange(n)*.01161;f=np.zeros((n,88));o=np.zeros_like(f);activity=np.ones(n,dtype=bool)
# Legato: the second note has no transient. Both real pitch states must survive.
f[10:65,60-21]=.7;f[65:120,64-21]=.65;o[10,60-21]=.9
notes,_=decode(f,o,t,activity);assert [x['pitches'][0] for x in notes]==[60,64],notes
assert len(decode(np.zeros_like(f),o,t,activity)[0])==0
# Strong onsets in an unrelated lower-energy competing pitch must not split lead.
f[:]=0;o[:]=0;f[10:150,60-21]=.7;f[10:150,67-21]=.2;o[[40,80,120],67-21]=.9
assert len(decode(f,o,t,activity)[0])==1
# A real same-pitch rearticulation must be represented even without a pitch change.
o[80,60-21]=.9
assert len(decode(f,o,t,activity)[0])==2
assert len(decode(f,o,t,np.zeros(n,dtype=bool))[0])==0
# Brief one-frame pitch excursions (e.g. a model glitch) must not add a note.
f[70,67-21]=.95
assert all(e['pitches']==[60] for e in decode(f,o,t,activity)[0])
a=json.loads((P/'analysis.json').read_text());events=a['events'];duration=a['source']['duration_seconds']
assert set(e['track'] for e in events)=={0,1} and len({e['id'] for e in events})==len(events)
for e in events:
 assert 0<=e['time_seconds']<=e['display_end_seconds']<=e['end_seconds']<=duration
 assert 0<=e['intensity']<=100 and not e['rejection_reasons']
for track in (0,1):assert np.all(np.diff([e['time_seconds'] for e in events if e['track']==track])>0)
d=[e for e in events if e['track']==0];m=[e for e in events if e['track']==1];period=a['drum_rhythm']['period_seconds'];diff=np.diff([e['time_seconds'] for e in d]);integer_error=abs(diff/period-np.round(diff/period));assert max(integer_error)<1e-9
assert all(e['evidence']['local_linear_attack']>=.1 for e in d)
# Track independence is retained. No melody event is snapped to the drum grid.
dt=np.array([e['time_seconds'] for e in d]);independent=sum(bool(np.min(abs(dt-e['time_seconds']))>.03) for e in m)
old=json.loads((P.parent/'override-two-track-v4/analysis.json').read_text());om=[e for e in old['events'] if e['track']==1]
matched=sum(any(abs(e['time_seconds']-v['time_seconds'])<=.06 and e['pitches']==v['pitches'] for e in m) for v in om)
result=dict(controls=['legato pitch change without onset retained','zero pitch evidence emits no notes','secondary pitch attack does not split sustained lead','same-pitch rearticulation retained','inactive source emits no notes','one-frame pitch glitch does not create a note'],
 events=len(events),drum_events=len(d),melody_events=len(m),max_drum_integer_period_error=float(max(integer_error)),melody_over_30ms_from_nearest_drum=independent,
 previous_melody_same_pitch_start_matches_within_60ms=matched,previous_melody_total=len(om),
 scope='Behavioral controls and output invariants; not acoustic precision/recall validation. V4 matching is diagnostic, not ground truth.')
(P/'analysis-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
