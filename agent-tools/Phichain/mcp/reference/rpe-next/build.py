"""Build a documentation-only MCP mapping from a pinned native command snapshot."""
import copy
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
COMMIT = '274bc55866dc5893e68c95bb4107f79711f1aa1d'
BASE = f'https://github.com/kclg-YSJ/rpe-next/blob/{COMMIT}/'
TOOLS = json.loads((OUT / 'native-tools.json').read_text())
BY = {t['name']: t for t in TOOLS}
CORE = 'editor_context editor_entities chart_templates chart_read chart_query chart_patch chart_transform chart_generate chart_script line_manage bpm_set diagnose history project_save'.split()
REVIEW = 'editor_navigate editor_view preview_capture editor_capture'.split()
NATIVE = 'chart_tools trajectory_presets trajectory_generate trajectory_split curve_notes event_shake noise_circle noise_track noise_fit text_fit multi_line global_events'.split()
HOST = 'web_search web_fetch ask_user'.split()
FOCUS = CORE + REVIEW + NATIVE
SUPPORT = [t['name'] for t in TOOLS if t['name'] not in FOCUS + HOST]
S = '<session from editor_context>'
R = '<revision from latest read>'
EXAMPLES = {
 'editor_context': {},
 'editor_entities': {'kind':'line','query':'Chorus'},
 'chart_templates': {},
 'chart_read': {'path':'/judgeLineList/0/notes','offset':0,'limit':41},
 'chart_query': {'path':'/judgeLineList/0/notes','start':8,'end':16,'sort':'startTime','fields':['type','startTime','endTime','positionX']},
 'chart_patch': {'revision':R,'label':'Move one note horizontally','operations':[{'op':'set','path':'/judgeLineList/0/notes/0/positionX','value':120}]},
 'chart_transform': {'revision':R,'path':'/judgeLineList/0/notes','indices':[0,1,2],'expressions':{'/positionX':'-positionX'},'label':'Mirror three notes'},
 'chart_generate': {'revision':R,'path':'/judgeLineList/0/notes','count':8,'template':{'type':1,'above':1,'startTime':[8,0,1],'endTime':[8,0,1],'positionX':0,'alpha':255,'size':1,'speed':1,'yOffset':0,'visibleTime':999999,'isFake':0},'expressions':{'/startTime':'8+i/2','/endTime':'8+i/2','/positionX':'-210+60*i'},'label':'Eight evenly spaced taps'},
 'chart_script': {'revision':R,'dryRun':True,'label':'Move two existing notes to another line','source':'const source = chart.judgeLineList[0];\nconst target = chart.judgeLineList[1];\nconst picked = new Set(input.indices);\nconst moving = source.notes.filter((note, i) => picked.has(i));\nsource.notes = source.notes.filter((note, i) => !picked.has(i));\ntarget.notes.push(...moving);\napi.report({ moved: moving.length });','input':{'indices':[0,1]}},
 'line_manage': {'revision':R,'action':'parent','line':1,'parent':0},
 'bpm_set': {'revision':R,'entries':[{'beat':0,'bpm':120},{'beat':32,'bpm':150}]},
 'diagnose': {'offset':0,'limit':50},
 'history': {'action':'list'},
 'project_save': {},
 'editor_navigate': {'target':'line_beat','line':0,'value':8},
 'editor_view': {'line':0,'layer':0,'playback':'pause','preview':True},
 'preview_capture': {},
 'editor_capture': {'target':'timeline'},
 'chart_tools': {},
 'trajectory_presets': {},
 'trajectory_generate': {'revision':R,'line':0,'start':8,'end':12,'options':{'xExpression':'200*cos(2*pi*t)','yExpression':'80*sin(2*pi*t)'},'output':'trajectory'},
 'trajectory_split': {'revision':R,'line':0,'eventIndex':0},
 'curve_notes': {'revision':R,'line':0,'start':8,'end':12,'startX':-200,'endX':200,'type':3,'division':4,'density':1,'easingType':1},
 'event_shake': {'revision':R,'line':0,'track':'moveXEvents','start':8,'duration':4,'amplitude':30,'cycles':4,'decayEasing':1},
 'noise_circle': {'revision':R,'start':8,'duration':4,'centerX':0,'centerY':0,'radius':200,'width':100,'height':100},
 'noise_track': {'revision':R,'start':8,'end':12,'target':{'mode':'note','lineIndex':0,'noteIndex':0},'width':100,'height':100},
 'noise_fit': {'revision':R,'mode':'text','text':'A','first':8,'duration':4,'width':400,'analyzeOnly':True},
 'text_fit': {'revision':R,'text':'A','lines':[0,1,2,3],'beat':8,'analyzeOnly':True},
 'multi_line': {},
 'global_events': {'action':'list'},
}
NOTES = {
 'editor_context':'Native context returns the current revision, selection and time bases. Proposed wrapper additionally returns a session token. Selection indices and JSON paths are revision-scoped, not stable object IDs.',
 'chart_templates':'Read a complete native object template before generation. With command set, this returns a command definition. Retain native defaults and fields rather than inventing an incomplete note.',
 'chart_read':'Reads raw JSON via JSON Pointer. Array results retain original indices. It does not automatically include parent motion, preceding speed events, or all dependencies. Read those explicitly.',
 'chart_query':'Queries one array at a time. Time filtering uses the configured start/end fields; it is not a visible-lifetime query. Sorting changes result order, not source indices. This example is a beat range, not a note ordinal range.',
 'chart_patch':'Changes individual fields without resending whole notes. All operations validate on a copy and commit together. Raw JSON paths do not automatically repair line references; prefer line_manage for line structure.',
 'chart_transform':'Safe numeric expressions run in the host. i is the selected sequence index during transformation; N is selected count; u spans 0–1; beat and numeric object fields are available. indices and where intersect when both supplied. Time fields are converted back to native beat fractions.',
 'chart_generate':'Appends complete template copies with expression overrides. Obtain the actual template first; this example uses the pinned native note shape. count is 1–10,000. Creating objects is not a guarantee of playable or visually good charting.',
 'chart_script':'This is the most general write path: a Worker edits a copy of the complete chart; the host validates and commits once. No DOM, network, Node, credentials or workspace APIs. Default 10 s; allowed 100–30,000 ms. dryRun computes without committing. The move example assumes two existing lines and preserves note JSON fields; moving across differently transformed lines does not preserve screen-space motion automatically. Re-run with fresh guards and dryRun=false only after reviewing the plan. This is not a reusable prepared-plan token.',
 'line_manage':'ensure / duplicate / delete / reorder / parent maintain native references. Native line indices are zero-based. This is structural management, not automatic note choreography or screen-space compensation.',
 'history':'Native undo/redo acts on shared editor history. There is no required human/agent author match in this native schema. Session checking is proposed in the adapter; author-aware history would be a separate behavior change.',
 'project_save':'Native save has no revision argument. The adapter can check the proposed session before invoking it, but do not claim revision-guarded saving without implementing that additional guard.',
 'preview_capture':'Returns a captured preview image, not a trajectory report, passage video, or continuous correctness proof. An MCP adapter must translate native image results into MCP image content.',
 'editor_capture':'Captures the editor or specified area while excluding private regions. Unlike preview_capture, this can help an agent inspect selection and controls.',
 'editor_navigate':'Changes the shared playhead/workspace. Specify chart_seconds, music_seconds, global_beat or line_beat explicitly; named objects use name. Navigation never retimes the chart.',
 'editor_view':'Changes the human-visible editor state. Time seeking belongs to editor_navigate. It does not write note timings.',
 'trajectory_generate':'Uses the same native computation as manual authoring. output=trajectory retains a native aggregate trajectory; output=events splits into ordinary events. Existing conflicts reject unless replacement is explicitly enabled.',
 'noise_track':'Bakes sampled target motion into noise-area events. Later edits to the original note/line do not automatically update the result.',
 'noise_fit':'analyzeOnly reports fitting results without chart edits. Actual generation reuses the native fitting and validation path. Font/image prerequisites still apply.',
 'text_fit':'Uses existing target lines and native fitting checks. analyzeOnly is read-only; unmet coverage/tolerance returns generated=false. Success must be checked before reporting that a chart edit happened.',
 'global_events':'Access depends on action: list/read are read-only, replace writes via native validation and undo. Unknown registered types may be read-only.',
 'multi_line':'Workspace selection/editing mode only; does not modify chart content.',
}
H = html.escape

def code(v):
 return '<pre><code>'+H(json.dumps(v,indent=2,ensure_ascii=False))+'</code></pre>'

def schema(name):
 result=copy.deepcopy(BY[name]['inputSchema'])
 if name!='editor_context':
  result['properties']['session']={'type':'string','description':'PROPOSED MCP wrapper session token; checked and removed before native dispatch.'}
  result.setdefault('required',[]).append('session')
 return result

def arguments(name):
 return {**({'session':S} if name!='editor_context' else {}),**EXAMPLES[name]}

# Validate illustrative calls against the exported native schemas and proposed envelope.
# This intentionally checks shape only; no editor, generators, or scripts are executed.
def validate(v,s):
 if 'enum' in s: assert v in s['enum'], (v,s)
 typ=s.get('type')
 if typ=='object':
  assert isinstance(v,dict)
  assert set(s.get('required',[]))<=v.keys(), (v,s.get('required'))
  if s.get('additionalProperties') is False: assert set(v)<=s.get('properties',{}).keys()
  for k,x in v.items(): validate(x,s.get('properties',{}).get(k,{}))
 elif typ=='array':
  assert isinstance(v,list)
  assert len(v)>=s.get('minItems',0) and len(v)<=s.get('maxItems',float('inf'))
  for x in v: validate(x,s.get('items',{}))
 elif typ=='string': assert isinstance(v,str) and len(v)<=s.get('maxLength',float('inf'))
 elif typ=='boolean': assert isinstance(v,bool)
 elif typ in ('number','integer'):
  assert isinstance(v,(int,float)) and not isinstance(v,bool)
  if typ=='integer': assert isinstance(v,int)
  assert s.get('minimum',-float('inf'))<=v<=s.get('maximum',float('inf'))
assert len(TOOLS)==53 and len(set(BY))==53
assert set(EXAMPLES)==set(FOCUS)
for name in FOCUS: validate(arguments(name),schema(name))
css=(ROOT/'phichain/reference.css').read_text()
parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>rpe-next · Proposed live MCP reference</title><style>'+css+'</style></head><body>',
 '<header><div class="eyebrow">rpe-next / native Agent commands → live MCP</div><h1>Read. Transform. Commit.</h1><p>A faithful MCP mapping of the existing chart-authoring command layer. The external agent makes charting decisions; rpe-next executes native operations in the open editor.</p><div class="rail"><span>30 chart workflow tools</span><span>20 supporting commands</span><span>3 host responsibilities</span></div></header>',
 '<div class="layout"><aside>']
for anchor,label in [('start','Status & setup'),('workflow','Writing workflow'),('catalog','Tool inventory'),('core','Read & write'),('review','Review results'),('native','Native authoring helpers'),('comparison','What differs from PhiChain'),('limits','Units & recovery'),('support','Supporting command appendix'),('sources','Sources & verification')]:
 parts.append(f'<a class="major" href="#{anchor}">{label}</a>')
for name in FOCUS: parts.append(f'<a href="#tool-{name}">{name}</a>')
parts.append('''</aside><main><h2 id="start">A conversion proposal, not an installed server</h2>
<div class="notice">Documentation only. No rpe-next MCP server has been implemented, no editor connection is made, and no chart is modified. The inventory is a faithful mapping, not a recommendation to add 50 tools to PhiChain.</div>
<p>Based on rpe-next v0.13.0, commit <code>274bc55</code>, inspected on 2026-10-27. All 53 native Agent command definitions were collected by registering their definitions without executing their handlers. Descriptions and native schemas are preserved in <a href="native-tools.json">native-tools.json</a>.</p>
<p>Proposed connection: external Agent → MCP stdio adapter → authenticated local editor bridge → existing command registry → live editor session. The editor remains the source of truth. Its built-in chat/model loop would not be needed to author via MCP. Native manual tools remain available.</p>
<p>Setup would require implementing the stdio adapter, an editor-side transport, and result/approval/cancellation adapters. There is no working launch command or existing endpoint to configure yet. Browser connections would also need a local relay or another explicit transport; desktop bridging is a separate implementation choice.</p>
<h3>Existing behavior versus adapter work</h3><table><thead><tr><th>Already native</th><th>Requires MCP adaptation</th></tr></thead><tbody>
<tr><td>JSON schemas, prepare/apply separation, revision checks for chart writes, native validation and shared undo</td><td>tools/list and tools/call, transport authentication, connection lifecycle and error mapping</td></tr>
<tr><td>ask / dangerous / full permission modes; prepared plans rechecked after approval</td><td>Expose concrete plans to a user approval UI or explicitly configured policy. MCP annotations alone do not approve a plan.</td></tr>
<tr><td>Image capture, local model work, cancellation signals</td><td>MCP image content, signal propagation, disconnected-client handling and result limits</td></tr>
<tr><td>Chart revision based on immutable chart identity</td><td>Proposed session token on all calls except editor_context, checked and stripped before native dispatch. editor_context returns that token. This does not add native revision checks to commands that lack them.</td></tr>
</tbody></table>
<h2 id="workflow">How the agent actually writes a chart</h2><ol>
<li><code>editor_context</code>: identify session, revision, selected line/notes and timing bases.</li>
<li><code>chart_read</code> / <code>chart_query</code>: resolve exact source indices, read affected notes, native event tracks, parents and other dependencies. Retrieve <code>chart_templates</code> when creating objects.</li>
<li>Choose the smallest complete representation: <code>chart_patch</code> for fields, <code>chart_transform</code> for repeated numeric changes, <code>chart_generate</code> for template sequences, or <code>chart_script</code> for arbitrary algorithms and multi-array edits. Native generators are available when they match the task.</li>
<li>The native handler prepares a candidate chart. Host validation and permission checks run; session/chart validity is checked again before one native commit. A successful chart batch is one undo entry.</li>
<li>Read the changed data, run <code>diagnose</code>, navigate to relevant times and inspect actual <code>preview_capture</code> images. Correct through another fresh guarded operation.</li>
<li>Use <code>project_save</code> when requested. Ordinary chart edits remain in memory until normal save/autosave.</li></ol>
<p>Scripts can express moving notes between line arrays, editing several tracks together, or computing a whole motion sequence in one request. They do not automatically solve parent transforms, maintain judgment positions, or know what looks good. Those decisions still belong to the agent.</p>
<h3>Example: mirror exactly three existing notes</h3><p>Read line 0’s notes and relevant context; use original source indices [0,1,2] with <code>chart_transform</code> and <code>{"/positionX":"-positionX"}</code>. Only those fields change, with one undo entry. This mirrors local x; world-space symmetry under transformed parents requires additional math.</p>
<h3>Example: move existing notes to another line</h3><p>Use <code>chart_script</code> to remove chosen items from one array and append them to another within the same candidate chart. No intermediate live deletion is exposed. Review a dry run, then execute with fresh guards. The example below preserves JSON fields, not screen-space trajectory or a guaranteed stable note identity.</p>
<h2 id="catalog">What tools would exist?</h2><p>A literal conversion maps 50 commands to MCP tools and leaves 3 commands with the external Agent host. The 30 tools below directly describe chart reading, writing and review. The remaining 20 are documented in a collapsed appendix so their existence is explicit without turning this into a broader product comparison.</p>
<table><thead><tr><th>Purpose</th><th>Native tools mapped one-to-one</th></tr></thead><tbody>''')
for label,names in [('Read / write / history',CORE),('Navigate / inspect result',REVIEW),('Native authoring helpers',NATIVE)]:
 parts.append('<tr><td>'+label+'</td><td>'+', '.join(f'<a href="#tool-{n}"><code>{n}</code></a>' for n in names)+'</td></tr>')
parts.append('</tbody></table><p>Names are retained for comparison. They are not aliases for PhiChain tools. Exact native schemas do not prove semantic completeness; descriptions and runtime checks still matter.</p>')
for anchor,title,names in [('core','Read and write the live chart',CORE),('review','Review actual results',REVIEW),('native','Native authoring helpers',NATIVE)]:
 parts.append(f'<h2 id="{anchor}">{title}</h2>')
 for name in names:
  t=BY[name]
  parts.append(f'<article class="tool" id="tool-{name}"><div class="toolhead"><span class="badge">native access: {H(t["access"])}</span><h3>{name}</h3></div><p>{H(t["description"])}</p>')
  if name in NOTES: parts.append('<div class="behavior">'+H(NOTES[name])+'</div>')
  parts.append('<h4>Illustrative MCP call</h4>'+code({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments(name)}}))
  parts.append('<details><summary>Proposed MCP input schema</summary><p>Native schema plus proposed session envelope. No native revision parameter is invented.</p>'+code(schema(name))+'</details></article>')
parts.append('''<h2 id="comparison">The writing interface compared with PhiChain</h2><table><thead><tr><th>Task</th><th>Current PhiChain MCP</th><th>rpe-next native command mapping</th></tr></thead><tbody>
<tr><td>Change one property</td><td>update_note/update_event replaces the full object</td><td>chart_patch sets a JSON Pointer field and preserves other fields</td></tr>
<tr><td>Apply repeated changes</td><td>Explicit per-object operations</td><td>chart_transform evaluates one expression across a selected collection</td></tr>
<tr><td>Generate a sequence</td><td>Explicit create operations or native curve-track editing</td><td>chart_generate repeats a complete template with expressions; native generators also exist</td></tr>
<tr><td>Multi-array algorithm</td><td>Explicit supported operations; no arbitrary script path</td><td>chart_script edits a complete validated candidate chart in a Worker</td></tr>
<tr><td>Target identity</td><td>Opaque session-scoped editable IDs</td><td>Raw JSON paths and source array indices; reread after mutation/reordering</td></tr>
<tr><td>Motion review</td><td>inspect_motion and preview_passage supply bounded actual render evidence</td><td>Preview/editor images and shared navigation; no equivalent continuous passage inspection in this command inventory</td></tr>
<tr><td>Undo ownership</td><td>Explicit author match required</td><td>Native shared undo/redo without required author matching</td></tr>
</tbody></table><p>The material difference is the vocabulary of writes: field patches, host-evaluated expressions and validated scripts reduce repetitive model-generated data. MCP is the transport in both designs. This page does not claim that the wider write vocabulary guarantees better chart quality.</p>
<h2 id="limits">Units, targeting and recovery</h2><ul>
<li>Native indices are zero-based. A user's “notes 1–41” means exactly 41 playable objects under an explicitly chosen ordering. Notes on one line in source array order can be read with offset=0, limit=41; chart-wide ordinal order requires explicitly gathering and ordering playable notes across lines. Do not substitute beats 1–41.</li>
<li>Raw RPE JSON stores beats as [whole,numerator,denominator]. Several command parameters also accept numeric/string beats; inspect the native parameter description. Native schemas leave some beat values untyped. This proposal preserves that weakness rather than silently tightening accepted syntax.</li>
<li>Line-local beats include the line bpmfactor; noise-area timing uses global beats. Music seconds and chart seconds differ by META.offset / 1000. Navigation and context distinguish these bases.</li>
<li>chart_query time overlap is not full visual lifetime. Early visibility, preceding speed events, parent motion and hold tails require further reads and render inspection.</li>
<li>Native revision identity changes with immutable chart objects; it is not a persistent chart ID. JSON paths/indices must be re-resolved after structural edits. Do not reuse indices merely because a tool succeeded.</li>
<li>General chart writes validate before a single native commit. editor_api and file/material operations do not promise equivalent transaction rollback or ordinary undo.</li>
<li>Native permissions can escalate based on the prepared plan: line deletion/reordering, large deletions and asset changes may be dangerous. The exported access label is the registration default, not a complete per-call classification. history, global_events and other mixed-action commands must not be blindly marked readOnlyHint=true.</li>
<li>chart_patch supports up to 2,000 operations; chart_transform up to 10,000 explicit indices; chart_generate count up to 10,000. Read/query pages cap at 200. Transport byte limits would still need to be chosen for the new bridge.</li>
<li>dryRun is supported by chart_script; analyzeOnly by fitting tools. There is no uniform native dry-run switch across every chart write. Approval prepares a candidate internally, but is not itself a public dry-run MCP call.</li>
<li>On stale state, reread and recompute. After transport loss, inspect current chart/history before retrying: execution may have completed. Stop/cancel does not roll back earlier successful operations. A new MCP adapter must implement these transport semantics explicitly.</li>
<li>diagnose checks native chart structure and known issues; it is not an aesthetic, human-playability, or full render-correctness proof.</li></ul>
<h2 id="support">Supporting command appendix</h2><p>These 20 existing commands are outside the central chart-write comparison. A full fidelity conversion could expose them; a chart-only deployment can omit them. No extra authoring presets are invented here.</p><details><summary>Show supporting commands and exact native schemas</summary>''')
for name in SUPPORT:
 t=BY[name]
 parts.append(f'<article class="tool" id="support-{name}"><h3>{name}</h3><p>{H(t["description"])}</p><p>Native registration access: <code>{H(t["access"])}</code>. Proposed session envelope applies if exposed.</p><details><summary>Exact native input schema</summary>'+code(t['inputSchema'])+'</details></article>')
parts.append('''</details><h3>Commands left with the external Agent host</h3><table><thead><tr><th>Native command</th><th>Disposition</th></tr></thead><tbody><tr><td>web_search / web_fetch</td><td>Use the external Agent's browsing capabilities; the editor does not need to relay model-provider web search.</td></tr><tr><td>ask_user</td><td>Use the external Agent's conversation/user-input UI. Do not create a second chat loop inside the editor bridge.</td></tr></tbody></table><p><code>agent_tools</code> is retained in the supporting inventory for traceability. Its native “activate definitions in the next model request” behavior belongs to the built-in model loop and would not carry over automatically. MCP discovery uses tools/list; merely returning a command name does not make it callable by an MCP client.</p>
<h2 id="sources">Sources and verification</h2><p>The snapshot contains command names, descriptions, registration access and native JSON schemas collected from the pinned public source. Runtime chart handlers were not called. The proposed session envelope is authored for this document, not extracted from an existing rpe-next MCP implementation.</p><ul>''')
for path,label in [('src/application/agent-editor.mjs','Core read/write and review registrations'),('src/application/agent-chart-tools.mjs','Native authoring helper registrations'),('src/application/agent-scripting-tools.mjs','Script and discovery registrations'),('src/core/agent-commands.mjs','Prepare / approval / validity / apply'),('protocols/AI-AGENT-PROTOCOL.zh-CN.md','Native Agent protocol'),('LICENSE','Source license: PolyForm Noncommercial 1.0.0')]:
 parts.append(f'<li><a href="{BASE+path}">{label}</a></li>')
parts.append('''</ul><p>Rebuild with <code>python3 local/rpe-next-mcp-reference/build.py</code>. The saved snapshot makes rebuilding independent of /tmp or network access. To refresh it, re-extract native registrations from a new pinned source revision and review all behavior notes.</p><p><a href="verification.json">Verification report</a> · <a href="../mcp-reference/index.html">Current PhiChain MCP reference</a></p><footer>Documentation proposal. Schema-shaped examples and internal navigation checked; examples have not been executed against a live editor. No implementation, chart edits, or model-quality benchmark is included.</footer></main></div></body></html>''')
page='\n'.join(parts)
class Nav(HTMLParser):
 def __init__(self): super().__init__(); self.ids=[]; self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='a' and a.get('href','').startswith('#'): self.links.append(a['href'][1:])
nav=Nav(); nav.feed(page)
assert len(nav.ids)==len(set(nav.ids))
assert set(nav.links)<=set(nav.ids)
(OUT/'index.html').write_text(page)
report={'source_commit':COMMIT,'native_commands':len(TOOLS),'chart_workflow_tools':len(FOCUS),'supporting_tools':len(SUPPORT),'host_responsibilities':HOST,'mapped_mcp_tools':len(FOCUS)+len(SUPPORT),'example_count':len(EXAMPLES),'examples_schema_checked':True,'semantic_execution_tested':False,'internal_links_valid':True,'charts_modified':False,'implementation_created':False,'snapshot_sha256':hashlib.sha256((OUT/'native-tools.json').read_bytes()).hexdigest()}
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
