"""Task-local client for the existing guarded editor bridge; no chart store."""
import sys,json
from pathlib import Path
ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0,str(ROOT/'tools/phichain-mcp'))
import server
ENDPOINT=ROOT/'.phichain-mcp.json'
def call(name,args):
 server.validate(args,server.BY_NAME[name]['inputSchema'])
 result=server.call_editor(ENDPOINT,name,args)
 if 'error' in result:raise RuntimeError(json.dumps(result))
 return result
def context():return call('get_context',{})
def guard(c):return {k:c[k] for k in ['session','revision']}
if __name__=='__main__':
 name=sys.argv[1]
 args=json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv)>2 else {}
 result=call(name,args)
 print(json.dumps(result,ensure_ascii=False,indent=2))
