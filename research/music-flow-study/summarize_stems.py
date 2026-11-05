from pathlib import Path
import json
import numpy as np,soundfile as sf
from analyze_librosa import SONGS,ROOT
out={}
for title,filename,index,gaps in SONGS:
 stem=Path(filename).stem;folder=ROOT/'demix/htdemucs'/stem
 if not all((folder/f'{n}.wav').exists() for n in ['drums','bass','vocals','other']):continue
 key=title.lower().replace(' ','-').replace("'",'')
 data=json.loads((ROOT/'librosa'/f'{key}.json').read_text())
 result={'title':title,'stems':{},'gap_comparisons':[]}
 powers={}
 for name in ['drums','bass','vocals','other']:
  y,sr=sf.read(folder/f'{name}.wav');powers[name]=np.mean(y*y,axis=1)
  result['stems'][name]=[{'seconds':float(t),'rms_dbfs':round(float(10*np.log10(powers[name][int(t*sr):int((t+.25)*sr)].mean()+1e-12)),3)} for t in np.arange(0,len(y)/sr-.25,.25)]
 def measure(a,b):return {name:round(float(10*np.log10(p[int(a*sr):int(b*sr)].mean()+1e-12)),2) for name,p in powers.items()}
 for gap in data['gaps']:
  result['gap_comparisons'].append({'from':gap['from'],'to':gap['to'],'windows':{k:measure(w['from'],w['to']) for k,w in gap['windows'].items()}})
 out[key]=result
(ROOT/'stem-analysis.json').write_text(json.dumps(out,indent=2,ensure_ascii=False))
for k,r in out.items():
 print(k)
 for g in r['gap_comparisons']:print(g)
