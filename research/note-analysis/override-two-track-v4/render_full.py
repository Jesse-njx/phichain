"""Render only guarded native snapshots, then label and join the full-song video."""
import json,sys,shutil,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0,str(ROOT/'tools/phichain-mcp'))
from agent_server import AgentServer


def main():
    adapter=AgentServer(OUT/'endpoint.json',str(ROOT/'target/debug/phichain-renderer'));adapter.initialized=True
    c=adapter.execute('editor_context',{});guard={k:c[k] for k in ['session','revision']}
    expected=json.loads((OUT/'verification.json').read_text())['revision']
    assert c['revision']==expected and c['project_path']==str(OUT/'project')
    duration=c['audio_duration_seconds'];ranges=[(s,min(s+12,duration)) for s in range(0,int(duration)+1,12)]
    parts=OUT/'native-parts';parts.mkdir(exist_ok=True)
    # Verify a representative middle passage first; reuse it in the final join.
    for start,end in [(48,60)]+[r for r in ranges if r!=(48,60)]:
        dest=parts/f'{start:03d}.mp4';receipt=parts/f'{start:03d}.json'
        if dest.exists() and receipt.exists() and json.loads(receipt.read_text()).get('captured_revision')==expected:continue
        print('RENDER',start,end,flush=True)
        response=adapter.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'preview_passage','arguments':{**guard,'from_seconds':start,'to_seconds':end}}})
        if response.get('error') or response.get('result',{}).get('isError'):raise RuntimeError(str(response)[:3000])
        result=response['result']['structuredContent'];assert not result.get('live_revision_changed')
        result['captured_revision']=expected;receipt.write_text(json.dumps(result,indent=2));shutil.copy2(result['video_path'],dest)
    concat=parts/'concat.txt';concat.write_text(''.join(f"file '{s:03d}.mp4'\n" for s,e in ranges))
    native=OUT/'override-two-track-native-full.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(native)],check=True)
    subprocess.run([str(ROOT/'../research/music-flow-study/.venv/bin/python'),str(OUT/'make_labels.py')],check=True)
    filters="[0:v][1:v]overlay=0:0[v];[v][2:v]overlay=0:0:enable='between(t,38.75,58.5)+between(t,85.25,128.25)'[out]"
    output=OUT/'override-two-track-full.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(native),'-loop','1','-i',str(OUT/'voice-labels.png'),'-loop','1','-i',str(OUT/'climax-label.png'),
                    '-i',str(OUT/'project/music.wav'),'-filter_complex',filters,'-map','[out]','-map','3:a','-t',str(duration),'-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)],check=True)
    current=adapter.execute('editor_context',{});assert current['revision']==expected
    (OUT/'render-verification.json').write_text(json.dumps(dict(revision=expected,live_revision_changed=False,parts=len(ranges),full_video=str(output),
        scope='All imagery from native guarded renders; added text labels only. Original canonical music replaces simultaneous game hit sounds. No chart or timing edits in postproduction.'),indent=2))
    print('DONE',str(output),flush=True)


if __name__=='__main__':main()
