import json,pathlib,subprocess,concurrent.futures,math
import numpy as np
P=pathlib.Path('../research/overnight-study/corpus');R=P.parent/'research';A=R/'audio';A.mkdir(exist_ok=True)
M=json.loads((P/'manifest.json').read_text())+json.loads((P/'supplemental-manifest.json').read_text())
def song(row):
 id,path=row
 if (A/(id+'.json')).exists():return id,json.loads((A/(id+'.json')).read_text())
 a=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',path,'-f','f32le','-ac','1','-ar','22050','-']),dtype='<f4');sr=22050;hop=256;nfft=2048
 frames=np.lib.stride_tricks.sliding_window_view(a,nfft)[::hop];spec=np.abs(np.fft.rfft(frames*np.hanning(nfft),axis=1)).astype(np.float32);times=(np.arange(len(spec))*hop+nfft/2)/sr;flux=np.r_[0,np.maximum(spec[1:]-spec[:-1],0).sum(axis=1)]
 ix=np.where((flux[2:-2]>=flux[:-4])&(flux[2:-2]>=flux[1:-3])&(flux[2:-2]>=flux[3:-1])&(flux[2:-2]>=flux[4:]))[0]+2
 peaks=np.array([times[i] for i in ix if flux[i]>np.percentile(flux[max(0,i-86):i+87],75)])
 sections=[]
 for t in range(0,math.ceil(len(a)/sr),8):
  block=a[t*sr:(t+8)*sr];mask=(times>=t)&(times<t+8);sections.append(dict(start=t,end=t+8,rms=float(np.sqrt(np.mean(block**2))) if len(block) else 0,flux_mean=float(np.mean(flux[mask])) if mask.any() else 0,onset_peak_count=int(((peaks>=t)&(peaks<t+8)).sum())))
 data=dict(id=id,duration=len(a)/sr,sample_rate=sr,fft_size=nfft,hop_samples=hop,onset_peak_seconds=peaks.tolist(),sections=sections);(A/(id+'.json')).write_text(json.dumps(data,ensure_ascii=False));return id,data
if __name__=='__main__':
 jobs={m['id']:m['music']['path'] for m in M};cache={};errors=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex:
  fs={ex.submit(song,row):row[0] for row in jobs.items()}
  for f in concurrent.futures.as_completed(fs):
   try:id,data=f.result();cache[id]=data;print('audio',id,flush=True)
   except Exception as e:errors.append(dict(id=fs[f],error=str(e)))
 results=[]
 for m in M:
  if m['id'] not in cache:continue
  data=cache[m['id']];peaks=np.array(data['onset_peak_seconds']);d=json.loads(pathlib.Path(m['chart']['path']).read_text());ns=[dict(n,seconds=n['time']*1.875/l['bpm']+d.get('offset',0),duration=n['holdTime']*1.875/l['bpm']) for l in d['judgeLineList'] for side in ['notesAbove','notesBelow'] for n in l[side]]
  def dist(ts):
   if not len(ts) or not len(peaks):return {}
   ix=np.searchsorted(peaks,ts);gap=np.minimum(abs(peaks[np.maximum(0,ix-1)]-ts),abs(peaks[np.minimum(len(peaks)-1,ix)]-ts));return dict(distinct_onsets=len(ts),median_nearest_peak_ms=float(np.median(gap)*1000),p90_nearest_peak_ms=float(np.percentile(gap,90)*1000),fraction_within_35ms=float(np.mean(gap<=.035)),fraction_within_70ms=float(np.mean(gap<=.07)))
  timing={str(k):dist(np.unique([n['seconds'] for n in ns if n['type']==k])) for k in range(1,5)}
  taps=np.unique([n['seconds'] for n in ns if n['type']==1]);offset_sensitivity={str(delta):dist(taps+delta) for delta in [-.1,-.06,-.03,0,.03,.06,.1]}
  rows=[]
  for sec in data['sections']:
   sel=[n for n in ns if sec['start']<=n['seconds']<sec['end']];rows.append(dict(sec,notes=len(sel),types={str(k):sum(n['type']==k for n in sel) for k in range(1,5)},active_hold_seconds=sum(max(0,min(sec['end'],n['seconds']+n['duration'])-max(sec['start'],n['seconds'])) for n in ns if n['type']==3)))
  def corr(key):
   x=np.array([r[key] for r in rows]);y=np.array([r['notes'] for r in rows]);return float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 and np.std(y)>0 else None
  results.append(dict(id=m['id'],title=m['title'],difficulty=m['difficulty'],supplemental=m.get('supplemental',False),chart_offset_seconds=d.get('offset',0),timing_by_note_type=timing,tap_offset_sensitivity=offset_sensitivity,sections=rows,section_note_density_vs_rms_correlation=corr('rms'),section_note_density_vs_flux_correlation=corr('flux_mean')))
 (R/'audio-crosscheck.json').write_text(json.dumps(dict(method='Mono22050Hz; FFT2048/Hop256; positive spectral flux; local maximum±2 frames and above local75thpercentile±86frames. Onset peaks are structural detection, not beat or instrument truth; distinct note times prevent chords overweighting timing. Eight-second fixed bins; chart offsets included.',song_count=len(cache),chart_count=len(results),errors=errors,charts=results),ensure_ascii=False,indent=2));print('DONE',len(cache),len(results),errors,flush=True)
