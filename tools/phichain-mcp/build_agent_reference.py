"""Generate the branch's real agent-server reference; never connect to an editor."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

import agent_server
import server

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'local/mcp-reference'
G = {'session':'<session from latest read>','revision':'<revision from latest read>'}
W = {**G,'dry_run':True}
EXAMPLES = {
 'editor_context':{}, 'chart_templates':{},
 'chart_read':{**G,'path':'/notes','limit':41},
 'chart_query':{**G,'collection':'notes','sort':'/note/beat','limit':41},
 'chart_patch':{**W,'operations':[{'op':'set','path':'/notes/1002/note/x','value':120}]},
 'chart_transform':{**W,'path':'/notes','ids':['1002','1003'],'expressions':{'/note/x':'-x'}},
 'chart_generate':{**W,'path':'/notes','count':8,'template':{'line_id':'1001','note':{'kind':'tap','above':True,'beat':[0,0,1],'x':0,'speed':1}},'expressions':{'/note/beat':'8+i/2','/note/x':'-210+60*i'}},
 'chart_script':{**W,'source':'const line = api.id("carrier");\nconst order = Math.max(...Object.values(chart.lines).map(row => row.order)) + 1;\nchart.lines[line] = api.createLine("Independent", order);\nfor (const id of input.note_ids) chart.notes[id].line_id = line;\napi.report({moved: input.note_ids.length});','input':{'note_ids':['1002','1003']}},
 'line_manage':{**W,'action':'duplicate','line_id':'1001','alias':'new:copy'},
 'bpm_set':{**W,'bpm_list':[{'beat':[0,0,1],'bpm':120}]},
 'curve_notes':{**W,'line_id':'1001','from_id':'1002','to_id':'1003','options':{'kind':'drag','density':16,'curve':{'type':'ease_in_out_sine'}}},
 'editor_entities':{**G,'collection':'lines','query':'Chorus'},
 'editor_navigate':{**G,'unit':'global_beat','value':8},
 'editor_view':{**G,'ids':['1002'],'line_id':'1001'},
 'diagnose':G,'chart_tools':{},'agent_tools':{'names':['chart_patch','chart_script']},'project_save':G,
}
NOTES = {
 'chart_read':'Document collections are keyed by editable native IDs, not RPE array indices. Existing read_section still reads a passage. Root returns counts and metadata; specific paths return exact data. Read parent lines and preceding events explicitly.',
 'chart_query':'limit=41 with sort=/note/beat returns exactly the first 41 playable editable notes in beat order; equal-beat ties use ID. Generated curve notes are derived and absent from this editable collection. Clarify numbering when users intend a different ordering. Beat range filters include overlapping holds, not full visible lifetime.',
 'chart_patch':'A field write preserves unrelated native fields. Insert a new:name line and notes/events referencing that alias in one batch. The bridge validates all references before any allocation. No delete/recreate is needed to move an existing note: set /notes/ID/line_id.',
 'chart_transform':'Paths are relative to each row: /note/x for notes; /event/value/start for events. Numeric fields, beat, i, N and u are evaluated from each original object. Beat results become canonical fractions. ids and where intersect. Shared-line motion still requires reading all affected notes.',
 'chart_generate':'Use complete rows from chart_templates. New aliases are new:prefix:i and returned as created_ids after committing. Numeric expressions use the copied rpe-next parser and numbered ease(t,id) mapping. Native event easing uses named PhiChain easing objects.',
 'chart_script':'Complete synchronous JavaScript computation on a fresh live candidate; no independent session/store. Use chart.lines/notes/events/curve_tracks ID maps and native meta/bpm_list/offset. New aliases resolve atomically. Moving a note preserves ID and fields; different parent transforms still require explicit geometric compensation. Dry runs recompute on apply; they are not saved plans.',
 'line_manage':'Duplicates include descendant lines, editable notes/events and remapped curve endpoints. Delete populated subtrees requires cascade=true. Reparenting preserves local coordinates. Native validation rejects cycles, invalid endpoints and deletion of every root.',
 'diagnose':'Reports native structural and motion issues. This is not a proof of aesthetic quality or human playability. It checks the exact supplied live revision.',
 'curve_notes':'Uses the native endpoint-based curve representation. Generated notes remain derived and cannot be edited as ordinary notes. Use chart_generate for independent editable notes.',
}
H=html.escape

def code(value): return '<pre><code>'+H(json.dumps(value,indent=2,ensure_ascii=False))+'</code></pre>'

def build(legacy_examples):
 examples={**legacy_examples,**EXAMPLES}
 assert set(examples)==set(agent_server.BY_NAME)
 for tool in agent_server.TOOLS:server.validate(examples[tool['name']],tool['inputSchema'])
 css=(OUT/'reference.css').read_text()
 parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PhiChain · Agent authoring MCP</title><style>'+css+'</style></head><body>',
 '<header><div class="eyebrow">PhiChain / rpe-agent-mcp branch / implemented</div><h1>Patch. Transform. Script.</h1><p>27 live tools: the original nine plus 18 rpe-next-style authoring operations adapted to native PhiChain. Charting decisions stay with the user and external Agent.</p><div class="rail"><span>Read exact native objects</span><span>Validate one candidate</span><span>Commit one undo entry</span></div></header><div class="layout"><aside>']
 for key,label in [('start','Setup'),('workflow','Writing workflow'),('document','Native document'),('scripts','Scripts & limits'),('catalog','27 tools'),('scope','Port scope & provenance')]:parts.append(f'<a class="major" href="#{key}">{label}</a>')
 for tool in agent_server.TOOLS:parts.append(f'<a href="#tool-{tool["name"]}">{tool["name"]}</a>')
 parts.append('''</aside><main><h2 id="start">Connect to the running editor</h2><p>This is an implemented alternative MCP entrypoint on the experimental branch. It uses the same live PhiChain editor, endpoint and shared history as the minimal server. It does not run rpe-next or keep an offline chart store.</p>
<pre><code>cargo build -p phichain
# Save your current work before restarting the editor with this build.
cargo run -p phichain -- --mcp-endpoint "$PWD/.phichain-mcp.json"
# Open a project normally, then register the experimental MCP entry:
codex mcp add phichain-agent -- python3 "$PWD/tools/phichain-mcp/agent_server.py" --endpoint "$PWD/.phichain-mcp.json"</code></pre>
<p>Refresh the MCP client after registration. Prefer one PhiChain entry per chat to avoid duplicate tool names. Python 3.9+ is required. Transform/generate/script additionally require Node.js 22.13+ supporting permission mode on the MCP PATH; there are no npm dependencies. Rendering retains the native renderer/ffmpeg/GPU prerequisites. Old editor builds report unknown authoring bridge commands and must be rebuilt/restarted.</p>
<div class="notice">Examples are documentation only: replace IDs, guards and paths with current live values. Builds and tests verify mechanical correctness; model-generated chart quality is not established by this page.</div>
<h2 id="workflow">Read → compute → validate → commit → inspect</h2><ol>
<li>editor_context identifies the current session, revision, lines and selected editable IDs.</li>
<li>chart_read/chart_query reads exact native data and dependencies. chart_templates provides complete legal object shapes and easing forms.</li>
<li>Choose chart_patch for individual fields, chart_transform for repeated numeric changes, chart_generate for template sequences, or chart_script for algorithms spanning several objects/collections.</li>
<li>Set dry_run=true: the live editor validates the complete candidate without chart/history changes. Reinvoke deterministically with fresh guards and dry_run=false to commit one shared agent undo entry.</li>
<li>Read changes, run diagnose and inspect actual renders via inspect_motion/preview_passage. Save through project_save only when requested.</li></ol>
<p>Both dry and real writes validate session/revision and idle state on the editor thread. An intervening human edit invalidates the candidate. After timeouts reread current data/history before retrying. Successful earlier edits are not automatically rolled back. Existing history retains its explicit human/agent author match.</p>
<h2 id="document">The native writable document</h2><p>Seven fields: lines, notes, events, curve_tracks, meta, bpm_list and offset. Collections use ID keys. Existing IDs retain identity through moves and undo/redo. New objects use unique new:name aliases; a new carrier and its notes/events can be created in one candidate. created_ids returns the native IDs after commit. New lines receive missing native baseline channels (x/y/rotation=0, opacity=255, speed=10) so they actually render and scroll. Explicit channels are preserved, existing lines are untouched, and added baselines appear in dry-run diffs.</p>''')
 parts.append(code({'lines':{'1001':agent_server.templates()['line']},'notes':{'1002':{'line_id':'1001','note':{'kind':'tap','above':True,'beat':[4,0,1],'x':100,'speed':1}}},'events':{},'curve_tracks':{},'meta':{'name':'Example','composer':'','charter':'','illustrator':'','level':''},'bpm_list':[{'beat':[0,0,1],'bpm':120}],'offset':0}))
 parts.append('''<p>Unknown or missing native fields, arbitrary numeric IDs, cross-type IDs, missing references, cycles, duplicate root orders and invalid curve endpoints reject before mutation. Beat arrays must be canonical; BPM begins at beat zero. Native numeric fields round to f32. Candidate operations affect actual native entities, not an RPE export/import round trip.</p>
<p>Changing line_id preserves local note fields and judgment times. It does not preserve screen-space motion automatically when parent/event transforms differ. Motion review must include early appearances and hold tails. Generated curve notes are rebuilt derived state, never stable editable objects.</p>
<h2 id="scripts">Computation and limits</h2><p>The copied rpe-next numeric expression parser supports safe arithmetic, comparisons, functions and conditional expressions. Numeric object fields plus beat/i/N/u are available; time-field expression results convert to canonical beats at 1/10000 resolution. Script code instead uses synchronous JavaScript and the native constructors shown by chart_templates.</p>
<p>A fresh VM context in a separate memory-limited Node process receives only JSON data, script source and computational helpers. No process/require/editor/DOM/file/network API is supplied. Node permission mode restricts reads to adapter code and denies writes/process spawning; credentials and the endpoint are not passed. This is computation isolation, not a claim that Node VM is an OS security boundary. No async scripts. Default 10-second timeout; allowed 100–30,000 ms. Errors and timeout do not submit a candidate.</p>
<ul><li>At most 20,000 editable objects; candidate bridge limit of 16 MiB may bind earlier (public MCP requests remain 1 MiB).</li><li>Patch: 1–2,000 operations. Generate: 1–10,000 objects. Read/query pages: at most 200.</li><li>Script input: 16 MiB; result: 8 MiB; final candidate bridge request must fit 16 MiB. Public MCP request: 1 MiB.</li><li>No-op candidates create no history entry. Dry runs are recomputed, not durable prepared-plan tokens.</li><li>Aliases: unique new:name, 5–80 ASCII bytes using letters, digits, underscore, hyphen or colon.</li></ul>
<h2 id="catalog">Actual server tool reference</h2><p>These descriptions and schemas come directly from agent_server.TOOLS. The first nine retain compatibility with the minimal entrypoint. Each example is schema-checked during generation.</p>''')
 for tool in agent_server.TOOLS:
  name=tool['name'];parts.append(f'<article class="tool" id="tool-{name}"><h3>{name}</h3><p>{H(tool["description"])}</p>')
  if name in NOTES:parts.append('<div class="behavior">'+H(NOTES[name])+'</div>')
  parts.append('<h4>Example call</h4>'+code({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':examples[name]}})+'<details><summary>Exact input schema</summary>'+code(tool['inputSchema'])+'</details></article>')
 parts.append('''<h2 id="scope">What was ported</h2><p>This branch ports the agent-to-chart writing vocabulary into PhiChain: field patches, batched expressions, templates and whole-candidate scripts. The expression parser and numbered easing functions were copied from rpe-next commit 274bc55866dc5893e68c95bb4107f79711f1aa1d; editor translation calls were replaced with standalone error messages. Those files retain PolyForm Noncommercial 1.0.0 and their required notices under tools/phichain-mcp/vendor/rpe-next/.</p>
<p>No foreign editor assets/runtime, noise areas, shader model, fake notes, text/noise fitting, aggregate trajectories, audio models, built-in model/chat loop, file workspace, VCS or collaboration were ported. Unsupported capabilities are not advertised as working tools. Native note/event algorithms can use chart_script, with PhiChain's existing rendering for review.</p>
<p><a href="index.html">Minimal nine-tool reference</a> · <a href="../rpe-next-mcp-reference/index.html">Earlier hypothetical rpe-next mapping</a> · <a href="agent-verification.json">Schema/navigation verification</a></p>
<footer>Generated from the implemented agent_server.py by build_agent_reference.py via local/mcp-reference/build.py. No editor calls or chart writes occur during documentation generation.</footer></main></div></body></html>''')
 page='\n'.join(parts)
 class Nav(HTMLParser):
  def __init__(self):super().__init__();self.ids=[];self.links=[]
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if 'id'in a:self.ids.append(a['id'])
   if tag=='a'and a.get('href','').startswith('#'):self.links.append(a['href'][1:])
 nav=Nav();nav.feed(page)
 assert len(nav.ids)==len(set(nav.ids)) and set(nav.links)<=set(nav.ids)
 (OUT/'agent.html').write_text(page)
 report={'tools':len(agent_server.TOOLS),'examples':len(examples),'examples_schema_checked':True,'all_internal_links_valid':True,'charts_modified':False,'schema_sha256':hashlib.sha256(json.dumps(agent_server.TOOLS,sort_keys=True).encode()).hexdigest()}
 (OUT/'agent-verification.json').write_text(json.dumps(report,indent=2)+'\n')
 return report
