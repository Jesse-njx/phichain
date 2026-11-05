"""Render read-only converted source, preserving original chart and audio."""
from pathlib import Path
import os,subprocess,json,hashlib
P=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain');project=P/'native-reference';video=P/'official-IN.mp4'
env=dict(os.environ,CARGO_MANIFEST_DIR=str(ROOT/'phichain-renderer'))
cmd=[str(ROOT/'target/debug/phichain-renderer'),str(project),'-o',str(video),'--from=0','--to=162.198639456','--width','960','--height','540','--fps','60','--hide-hit-effect','--no-telemetry']
with (P/'render.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],capture_output=True,check=True)
(P/'render-receipt.json').write_text(json.dumps({'command':cmd,'full_decode':'passed','sha256':hashlib.sha256(video.read_bytes()).hexdigest()},indent=2))
print(video)
