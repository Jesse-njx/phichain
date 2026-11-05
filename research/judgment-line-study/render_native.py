"""Render immutable source conversions for representative evidence, never a live edit."""
from pathlib import Path
import json, os, subprocess, time, sys

ROOT=Path(__file__).resolve().parent
REPO=Path('/Users/jesse/Projects/PhiChain/phichain')
TAGS=['side-entry','turning-approach','half-turn-hook','spinning-approach','serpentine-carriage','moving-pivot-hook','stop-and-release','reverse-scroll','invisible-carrier','settle-before-hit','transported-hold','pivoted-hold','pivot-locked-landing','compensated-landing','zigzag-note-formation','arched-note-formation','speed-fanned-formation','opposed-approach-chord','orthogonal-approach-chord','visible-anchor-hidden-partner','travelling-blade','strobe-line','offscreen-pivot-wipe','parallel-opening','rotating-rails','scissor-crossing','moving-line-comb','radial-line-fan']

def main():
    bank=json.loads((ROOT/'bank.json').read_text());out=ROOT/'native';out.mkdir(exist_ok=True);projects=ROOT/'native-projects';projects.mkdir(exist_ok=True)
    silence=projects/'silence.wav'
    if not silence.exists():subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=22050:cl=mono','-t','360','-c:a','pcm_s16le',str(silence)],check=True)
    receipts=[];baseline=ROOT/'native-receipts.json';shard=int(sys.argv[sys.argv.index('--shard')+1]) if '--shard'in sys.argv else None
    receipt_path=ROOT/(f'native-receipts-part{shard}.json' if shard is not None else 'native-receipts.json')
    if receipt_path.exists():receipts=json.loads(receipt_path.read_text())
    elif baseline.exists():receipts=json.loads(baseline.read_text())
    stats={r['id']:r for r in json.loads((ROOT/'chart-statistics.json').read_text())};env=dict(os.environ);env['CARGO_MANIFEST_DIR']=str(REPO/'phichain-renderer')
    for c in bank:
        if shard is not None and int(c['chart'][1:])%2!=shard:continue
        tag=c['mechanism'];cid=c['id'];rec=c['source'];folder=projects/c['chart'];folder.mkdir(exist_ok=True)
        start=max(0,c['start']-.25);end=c['end']+.4
        previous=next((r for r in receipts if r.get('success') and r['source_sha256']==rec['sha256'] and r['mechanism']==tag and abs(r['chart_seconds'][0]-start)<1e-5 and abs(r['chart_seconds'][1]-end)<1e-5),None)
        if previous:continue
        r={'id':cid,'mechanism':tag,'source_sha256':rec['sha256'],'source_path':rec['path'],'native_project':str(folder),'success':False};at=time.monotonic()
        try:
            chart=folder/'chart.json'
            valid_chart=False
            if chart.exists():
                try:json.loads(chart.read_text());valid_chart=True
                except (ValueError,OSError):pass
            if not valid_chart:
                args=[str(REPO/'target/release/phichain-converter'),'--from','official','--to','phichain',rec['path'],str(chart),'--no-easing-fitting','--round','6','--no-telemetry'];r['converter_command']=args
                cp=subprocess.run(args,capture_output=True,timeout=120);(folder/'convert.log').write_bytes(cp.stdout+cp.stderr)
                if cp.returncode:raise RuntimeError('converter failed; see convert.log')
            # Conversion is a disposable research snapshot. No source file or live project is changed.
            (folder/'meta.json').write_text(json.dumps({'name':rec['title'],'composer':'','charter':'Original source; research rendering','illustrator':'','level':rec['difficulty']}))
            audio=Path(rec.get('music_path',''))
            original=audio.is_file();audio=audio if original else silence;dest=folder/('music'+audio.suffix)
            if not dest.exists():dest.symlink_to(audio)
            r['audio']='matching local source audio' if original else 'silent reference; no matching local audio used'
            r['chart_seconds']=[start,end];asset=f'{c["chart"]}-{round(c["start"]*1000)}-{round(c["end"]*1000)}';video=out/(asset+'.mp4')
            args=[str(REPO/'../apps/PhiChain.app/Contents/MacOS/phichain-renderer'),str(folder),'-o',str(video),'--from',str(start),'--to',str(end),'--width','960','--height','540','--fps','30','--hide-hit-effect','--no-telemetry'];r['renderer_command']=args
            with (out/(asset+'.log')).open('w') as log:cp=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=150)
            if cp.returncode:raise RuntimeError('renderer failed; see native log')
            r['success']=video.is_file() and video.stat().st_size>0;r['video']=str(video);r['review_status']='rendered; awaiting frame review'
        except Exception as exc:r['error']=str(exc)
        r['wall_seconds']=round(time.monotonic()-at,2);receipts.append(r);receipt_path.write_text(json.dumps(receipts,ensure_ascii=False,indent=2));print(cid,tag,r['success'],r['wall_seconds'],r.get('error',''),flush=True)

if __name__=='__main__':main()
