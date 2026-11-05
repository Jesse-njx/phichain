"""Check an existing official timing grid against decoded positive spectral flux."""
import pathlib,json,hashlib
import numpy as np
R=pathlib.Path(__file__).resolve().parents[1]
source=R/'corpus/chart/RetributionCycleofRedemption.ArdolfvsDaily天利.0/IN.json'
audio=R/'corpus/music/RetributionCycleofRedemption.ArdolfvsDaily天利.ogg'
c=json.loads(source.read_text());p=np.array(json.loads((R/'design/onset-peaks.json').read_text()))
ts=np.array(sorted(set(n['time']/32*60/l['bpm'] for l in c['judgeLineList'] for side in ['notesAbove','notesBelow'] for n in l[side] if n['type']==1)))
rows=[]
for off in [-.08,-.04,0,.04,.08]:
 ds=np.array([min(abs(p[:,0]-(t+off))) for t in ts]);rows.append(dict(offset_s=off,distinct_source_tap_times=len(ts),median_nearest_peak_distance_s=float(np.median(ds)),fraction_within_35ms=float(np.mean(ds<.035))))
report=dict(status='DIGITAL_TIMING_EVIDENCE_ONLY',source_chart_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),audio_decode='ffmpeg mono22050Hz float32',frame_size=2048,hop=256,peak_definition='positive spectral flux local maximum within±2frames exceeding local75thpercentile within±86frames',time_unit_conversion='official time /32 beats *60/line.bpm',audio_duration_s=173.79120181405895,candidate_offsets=rows,limitations=['Nearest spectral flux peak does not establish voice identity or every attack correctness.','Many high-energy passages contain frequent peaks, increasing accidental proximity.','No human auditory listening or physical playtest has occurred.'])
(R/'design/timing-evidence.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps(rows,indent=2))
