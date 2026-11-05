"""Create a fresh project using the native runtime; never reuse a populated project."""
import json,os,subprocess,sys,time
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0,str(ROOT/'tools/phichain-mcp'))
import server
endpoint=OUT/'endpoint.json'
assert not endpoint.exists() and not (OUT/'project').exists()
env=dict(os.environ,CARGO_MANIFEST_DIR=str(ROOT/'phichain-editor'))
with (OUT/'editor.log').open('w') as log:
    host=subprocess.Popen([str(ROOT/'target/debug/phichain'),'--headless','--mcp-endpoint',str(endpoint)],env=env,cwd=ROOT/'phichain-editor',stdout=log,stderr=log,start_new_session=True)
(OUT/'editor-process.json').write_text(json.dumps(dict(pid=host.pid)))
def call(name,args={}):
    r=server.call_editor(endpoint,name,args)
    if r.get('error'):raise RuntimeError(str(r))
    return r

def settled():
    until=time.monotonic()+30
    while time.monotonic()<until:
        r=call('editor_status')
        if r['pending'] is None:
            assert r['last_error'] is None,r
            return r
        time.sleep(.05)
    raise RuntimeError('Lifecycle timeout')
until=time.monotonic()+15
while not endpoint.exists():
    assert host.poll() is None and time.monotonic()<until
    time.sleep(.05)
s=call('editor_status');assert s['pid']==host.pid and s['headless'] and s['project'] is None
analysis=json.loads((OUT/'analysis.json').read_text())
call('create_project',dict(path=str(OUT/'project'),music_path=analysis['source']['path'],meta=dict(name='Override - Drums and Main Melody',level='Analysis / conservative',composer='',charter='Two-role analysis experiment',illustrator='')))
assert settled()['created_path']==str(OUT/'project')
call('open_project',dict(path=str(OUT/'project')));s=settled();assert s['project']
(OUT/'created-status.json').write_text(json.dumps(s,indent=2));print('Created and opened new native project',host.pid)
