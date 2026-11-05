from pathlib import Path
import json,sys
from live import context,guard,call,server
ROOT=Path(__file__).resolve().parent
import motion
c=context()
section=call('read_section',{'start_beat':200,'end_beat':234})
orbit={l['id'] for l in c['lines'] if 'ORBIT' in l['name']}
ids=[n['id'] for n in section['notes'] if n['line_id'] in orbit]
if not (ROOT/'orbit-review.json').exists():
 data,images=motion.inspect(lambda n,a:server.call_editor(Path('/Users/jesse/Projects/PhiChain/phichain')/'.phichain-mcp.json',n,a),{**guard(c),'note_ids':ids,'from_seconds':58.,'to_seconds':70.,'frames':12},output_root=ROOT/'motion-review')
 (ROOT/'orbit-review.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 print('ORBIT',data.get('report_path'),flush=True)
for a,b in [(.35,12),(38,50),(87,99),(126,138)]:
 c=context()
 d=motion.preview_passage(lambda n,args:server.call_editor(Path('/Users/jesse/Projects/PhiChain/phichain')/'.phichain-mcp.json',n,args),{**guard(c),'from_seconds':a,'to_seconds':b},output_root=ROOT/'previews')
 (ROOT/f'preview-{a}.json').write_text(json.dumps(d,indent=2));print('PREVIEW',a,d.get('video_path'),flush=True)
