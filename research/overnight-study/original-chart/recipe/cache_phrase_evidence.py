"""Cache musical timing evidence without source coordinates or authored notes."""
import pathlib,json,hashlib,collections,subprocess
import numpy as np
R=pathlib.Path(__file__).resolve().parents[2]
source=R/'corpus/chart/RetributionCycleofRedemption.ArdolfvsDaily天利.0/IN.json';audio=R/'corpus/music/RetributionCycleofRedemption.ArdolfvsDaily天利.ogg'
c=json.loads(source.read_text());bybeat=collections.defaultdict(list)
for l in c['judgeLineList']:
 for side in ['notesAbove','notesBelow']:
  for n in l[side]:
   bybeat[n['time']/32].append(dict(kind=n['type'],duration=n['holdTime']/32))
a=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(audio),'-f','f32le','-ac','1','-ar','22050','-']),dtype='<f4');nfft=2048;hop=256;sr=22050
frames=np.lib.stride_tricks.sliding_window_view(a,nfft)[::hop];spec=abs(np.fft.rfft(frames*np.hanning(nfft),axis=1));times=(np.arange(len(spec))*hop+nfft/2)/sr;freq=np.fft.rfftfreq(nfft,1/sr)
fluxes={}
for name,lo,hi in [('low_register',30,180),('middle_register',180,1800),('high_register',1800,10000)]:
 sub=spec[:,(freq>=lo)&(freq<hi)];f=np.r_[0,np.maximum(sub[1:]-sub[:-1],0).sum(axis=1)];peaks=[]
 for i in range(2,len(f)-2):
  if f[i]==max(f[i-2:i+3]) and f[i]>np.percentile(f[max(0,i-86):i+87],75):peaks.append((times[i],f[i]))
 fluxes[name]=np.array(peaks)
sections=[]
for i,s in enumerate(json.loads((R/'design/proposed-phrase-map.json').read_text())['sections']):
 start,end=s['beat_start'],s['beat_end'];sourceevents=[];newaudio=[]
 for b,ns in sorted(bybeat.items()):
  if not start<=b<end:continue
  kinds=sorted(set(n['kind'] for n in ns));holds=[n['duration'] for n in ns if n['kind']==3 and n['duration']>=.5]
  sourceevents.append(dict(beat=b,kind_evidence=kinds,sustained_durations=holds,source_head_count=len(ns)))
 for j in range(int(np.ceil(start*4)),int(np.ceil(end*4))):
  b=j/4;t=b*60/225;matches={}
  for name,p in fluxes.items():
   k=int(abs(p[:,0]-t).argmin());distance=abs(p[k,0]-t)
   if distance<=.025:matches[name]=dict(nearest_peak_s=round(float(p[k,0]),6),distance_ms=round(float(distance*1000),2),positive_flux=round(float(p[k,1]),3))
  if matches:newaudio.append(dict(beat=b,register_evidence=matches,already_in_source=b in bybeat))
 sections.append(dict(id=f'phrase-{i:02d}',beat_start=start,beat_end=end,source_articulation_events=sourceevents,quantized_audio_attack_candidates=newaudio,proposed_roles=s['proposed_roles'],status='EVIDENCE_CANDIDATES_NOT_AUTHORED_NOTES'))
out=dict(song='Retribution ~ Cycle of Redemption ~',bpm=225,offset_s=0,source_chart_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),source_coordinates_excluded=True,evidence_method='official timing/kinds/durations and register-banded positive spectral flux; instrument labels provisional',sections=sections)
p=R/'original-chart/evidence/phrase_events.json';p.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
print('cached',len(sections),'phrases; source articulation events',sum(len(s['source_articulation_events']) for s in sections),'audio candidates',sum(len(s['quantized_audio_attack_candidates']) for s in sections),'bytes',p.stat().st_size)
