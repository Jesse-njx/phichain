"""Measured local renderer adapter runs; subprocess work is distinct from MCP time."""
import datetime,json,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
renderer='/Users/jesse/Projects/PhiChain/apps/PhiChain.app/Contents/MacOS/phichain-renderer'
folder=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'release-v2')
specs=[('ending-review',168,173.7912,1280,720),('reset-review',102,115,1280,720),('sparse-melodic-review',82,90,1280,720),('carrier-review',82,97,1280,720),('dense-wide-review',47,67,1260,540),('fullsong',0,173.7912,1280,720)]
records=[]
for name,start,end,w,h in specs:
    target=folder/(name+'.mp4');args=[renderer,str(folder),'-o',str(target),'--from',str(start),'--to',str(end),'--width',str(w),'--height',str(h),'--fps','30','--no-telemetry']
    began=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.perf_counter();p=subprocess.run(args,capture_output=True,text=True)
    row=dict(name=name,command=args,started_utc=began,elapsed_s=time.perf_counter()-t,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
    records.append(row);(folder/'render-receipts.json').write_text(json.dumps(records,indent=2));print(json.dumps({k:row[k] for k in ['name','elapsed_s','exit_code']}),flush=True)
    if p.returncode:raise SystemExit(p.returncode)
