import json,pathlib,subprocess,os
r=pathlib.Path(__file__).resolve().parents[1]
exe=r.parents[1]/'../apps/PhiChain.app/Contents/MacOS/phichain-converter'
for s in json.loads((r/'design/deep_reference_specs.json').read_text()):
 p=r/'design/reference-projects'/s['name'];p.mkdir(exist_ok=True)
 subprocess.run([str(exe),str(r/'corpus/chart'/f"{s['id']}.0"/f"{s['difficulty']}.json"),str(p/'chart.json'),'--from','official','--to','phichain','--no-telemetry'],check=True)
 audio=p/'music.ogg'
 if not audio.exists():os.symlink((r/'corpus/music'/f"{s['id']}.ogg").resolve(),audio)
 (p/'meta.json').write_text(json.dumps(dict(name=s['id'].split('.')[0],composer=s['id'].split('.')[-1],charter='Official study only',illustrator='',level=s['difficulty']),ensure_ascii=False))
