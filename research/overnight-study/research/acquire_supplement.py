import pathlib,json,urllib.request,urllib.parse,hashlib,concurrent.futures
P=pathlib.Path('../research/overnight-study/corpus');D={x[0]:x[1:] for l in (P/'difficulty.tsv').read_text().splitlines() if (x:=l.split('\t'))};info={x[0]:x for l in (P/'info.tsv').read_text().splitlines() if (x:=l.split('\t'))}
spec=[('HorizonBlue.NothingButRequiemfeatAikapinChiyoko','IN'),('Shadow.SumaiLightvs姜米條','AT'),('FULiAUTOBUSTER.MYUKKE','IN'),('FULiAUTOSHOOTER.MYUKKE','IN'),('Cleyera.Riya','IN'),('NOONEYESMAN.MYUKKE','IN')];out=[]
def get(branch,path):
 u='https://raw.githubusercontent.com/7aGiven/Phigros_Resource/'+branch+'/'+urllib.parse.quote(path);o=P/'supplemental'/branch/path;o.parent.mkdir(parents=True,exist_ok=True);b=urllib.request.urlopen(u,timeout=45).read();o.write_bytes(b);return dict(url=u,path=str(o),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
for id,d in spec:
 i=2 if d=='IN' else 3;x=info[id];row=dict(id=id,title=x[1],difficulty=d,constant=float(D[id][i]),supplemental=True,reason='User reference outside main IN16/AT17 corpus',chart=get('chart',id+'.0/'+d+'.json'),music=get('music',id+'.ogg'));out.append(row);print(row['title'],row['constant'],flush=True)
(P/'supplemental-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
