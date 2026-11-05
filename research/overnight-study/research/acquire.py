import urllib.request,urllib.parse,json,pathlib,hashlib,concurrent.futures
P=pathlib.Path('../research/overnight-study/corpus');BASE='https://raw.githubusercontent.com/7aGiven/Phigros_Resource/'
D={x[0]:x[1:] for l in (P/'difficulty.tsv').read_text().splitlines() if (x:=l.split('\t'))}
M=[]
for l in (P/'info.tsv').read_text().splitlines():
 x=l.split('\t'); d=D.get(x[0],[])
 for k,i,level in [('IN',2,16),('AT',3,17)]:
  if len(d)>i and level<=float(d[i] or 0)<level+1:
   M.append(dict(id=x[0],title=x[1],composer=x[2],difficulty=k,constant=float(d[i]),has_AT=len(d)>3 and bool(d[3]),charter=x[3+i] if len(x)>3+i else None))
def get(branch,path):
 u=BASE+branch+'/'+urllib.parse.quote(path); out=P/branch/path;out.parent.mkdir(parents=True,exist_ok=True)
 try:
  b=urllib.request.urlopen(u,timeout=45).read();out.write_bytes(b)
  return dict(url=u,path=str(out),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e:return dict(url=u,error=str(e))
# prioritise the selected candidate
c='RetributionCycleofRedemption.ArdolfvsDaily天利'
print('candidate',get('chart',c+'.0/IN.json'),get('music',c+'.ogg'),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 fs={ex.submit(get,'chart',m['id']+'.0/'+m['difficulty']+'.json'):m for m in M}
 for f in concurrent.futures.as_completed(fs):fs[f]['chart']=f.result()
 ids={m['id'] for m in M};fs={ex.submit(get,'music',i+'.ogg'):i for i in ids};audio={}
 for f in concurrent.futures.as_completed(fs):audio[fs[f]]=f.result()
 for m in M:m['music']=audio[m['id']]
(P/'manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2))
print('charts',len(M),'missing',sum('error' in m['chart'] for m in M),'audio missing',sum('error' in a for a in audio.values()),flush=True)
