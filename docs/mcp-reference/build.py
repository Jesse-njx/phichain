"""Build the minimal MCP reference from the current server; never call the editor."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools/phichain-mcp'))
import server
import music_server

H = html.escape
G = {'session': '<session from latest read>', 'revision': '<revision from latest read>'}
EXAMPLES = {
    'editor_status': {},
    'create_project': {'path':'/absolute/path/new-project','music_path':'/absolute/path/song.mp3'},
    'open_project': {'path':'/absolute/path/new-project'},
    'close_project': G,
    'get_context': {},
    'inspect_motion': {**G, 'note_ids':['1002'], 'from_seconds':0, 'to_seconds':2, 'frames':6},
    'read_section': {'start_beat': 0, 'end_beat': 8, 'line_id': '1001'},
    'apply_edits': {**G, 'operations': [{'op': 'create_note', 'line_id': '1001',
        'note': {'kind': 'tap', 'above': True, 'beat': [4, 0, 1], 'x': 120, 'speed': 1}}]},
    'preview': {'session': G['session'], 'action': 'seek', 'time_seconds': 2},
    'history': {**G, 'action': 'undo', 'author': 'agent'},
    'save': G,
    'preview_passage': {**G, 'from_seconds': 1, 'to_seconds': 3},
    'animate_selection': {**G, 'dry_run': True, 'groups': [{'carrier_id':'1001','note_ids':['1002','1003'],'events':[{'kind':'speed','start_beat':[0,0,1],'end_beat':[4,0,1],'value':{'type':'constant','value':0}}]}]},
}
assert set(EXAMPLES) == set(server.BY_NAME), 'Update documentation examples for the current tools'


def code(value):
    return '<pre><code>' + H(json.dumps(value, indent=2, ensure_ascii=False)) + '</code></pre>'


parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>PhiChain · Live MCP reference</title><style>',
    (OUT / 'reference.css').read_text(),
    '</style></head><body><header><div class="eyebrow">PhiChain / minimal live MCP</div>'
    '<h1>Read. Edit. Preview.</h1><p>13 tools for the project open in PhiChain. '
    'Charting decisions stay with you.</p><div class="rail"><span>Read the passage</span>'
    '<span>Apply one undo step</span><span>Preview &amp; save</span></div></header>'
    '<div class="layout"><aside><a class="major" href="#start">Setup</a>'
    '<a class="major" href="#workflow">Editing workflow</a>'
    '<a class="major" href="#catalog">13 tools</a>'
    '<a class="major" href="#music">Local music MCP</a>'
    '<a class="major" href="#note-analysis">MP3 note analysis</a>'
    '<a class="major" href="#operations">Edit operations</a>'
    '<a class="major" href="#limits">Units &amp; recovery</a>']
for tool in server.TOOLS:
    parts.append(f'<a href="#tool-{tool["name"]}">{tool["name"]}</a>')
parts.append('''</aside><main><h2 id="start">Start with an open project</h2>
<p>The Python adapter forwards validated requests to the authenticated editor bridge.
The live editor is the only chart state. Start PhiChain with its bridge enabled and
create/import and open your project using MCP lifecycle tools. Run these commands from the repository root:</p>
<p>The bridge handles at most one request per frame in <code>PreUpdate</code>, before
gameplay and render-state propagation. Newly edited sprites and hold parts are
initialized before that frame renders, preventing full-size texture bands during
continuous agent edits. Rebuild and restart the editor for this fix.</p>
<p>The default editor layout includes a live whole-chart Note Density pane below
Inspector and Timeline Setting. It counts each playable note head once, including
generated notes, and supports click/drag seeking through shared playback controls.
No MCP tools or arguments are added; the preview-only layout stays preview-only.</p>
<pre><code>cargo run -p phichain -- --mcp-endpoint "$PWD/.phichain-mcp.json"
codex mcp add phichain -- python3 "$PWD/tools/phichain-mcp/server.py" --endpoint "$PWD/.phichain-mcp.json"</code></pre>
<p>Python 3.9+ is sufficient; no Python packages are required. The adapter accepts
<code>--endpoint</code> and optional <code>--renderer</code>. Motion inspection also requires
<code>phichain-renderer</code>, ffmpeg on PATH and a GPU. Rebuild and restart the editor for the new bridge command.
Restart the MCP client to refresh the tool inventory. The endpoint is reread on every call.</p>
<div class="notice">Examples are documentation only. Replace guards and numeric IDs
with values from the live project. This page makes no editor calls.</div>
<h2 id="headless">Headless operation</h2>
<pre><code>cargo run -p phichain -- --headless --mcp-endpoint "$PWD/../runtime/headless-endpoint.json"</code></pre>
<p>Connect either chart adapter to that unique endpoint. No window, GPU or audio output
is initialized; native chart entities, editing commands, undo and save are shared with
the GUI implementation. The current executable still links GUI dependencies.</p>
<p>Call editor_status, then create_project with absolute path/music_path and optional
illustration_path/meta. The destination must be new with an existing parent. MP3/WAV/OGG/FLAC
and PNG/JPG/JPEG are validated and copied; sources remain unchanged. Poll editor_status
until pending=null, verify last_error=null, then open_project with created_path and poll
again. An opened project supplies session/revision. Save before guarded close_project.
Creation does not open automatically; existing-project audio replacement is not exposed.</p>
<p>Headless preview uses a silent seek/play/pause clock. Save explicitly; there is no
headless autosave. Motion/passage rendering still requires the independent renderer,
ffmpeg and GPU. Use a separate endpoint and project from other running agents. Forced
termination may leave a stale endpoint; confirm its PID exited before removal.</p>
<h2 id="workflow">Read, edit, review</h2><ol>
<li>Call <code>get_context</code> to identify the project, selected objects and lines.</li>
<li>Call <code>read_section</code> for the affected beat range. Use its fresh session and revision.</li>
<li>Send explicit operations through <code>apply_edits</code>. One successful batch is one shared undo entry.</li>
<li>Read the changed passage and use <code>preview</code> to review it in PhiChain.</li>
<li>Use current guards with <code>save</code> when the user asks to save.</li></ol>
<p>Project creation imports local audio and an optional cover without dialogs.
There are no authoring presets or planning caches in this MCP interface. It advertises tools
only, with no MCP resources or prompts. Future capabilities are user-designed.</p>
<h2 id="note-analysis">MP3 note decisions and musical intensity</h2>
<p>The user-requested local CLI <code>tools/music-analysis/analyze.py</code> accepts
MP3/WAV/OGG and exports timestamped note decisions, musical intensity (0–100),
separate priority and confidence, texture sections and candidate climax intervals.
It retains omitted candidates and produces a local HTML report with original/hits
audio comparison and source-bound JSON review corrections. Open reports yourself.</p>
<p>This is an acoustic heuristic draft, not verified transcription or a playable
chart. It does not edit the live project or add MCP tools. No automatic model
downloads or remote inference. Optional known BPM annotates beats without snapping.</p>
<pre><code>../research/music-flow-study/.venv/bin/python tools/music-analysis/analyze.py /absolute/path/song.mp3 --out ../research/note-analysis/song</code></pre>
<p>Requires ffmpeg/ffprobe and the dependencies in
<code>tools/music-analysis/requirements.txt</code>. See
<a href="../../tools/music-analysis/README.md">the CLI documentation</a> for setup,
score definitions, stem manifests, review syntax and limits. Keep artifacts under
the workspace outside the repository. Output directories must be new to preserve reviews.</p>
<p>For editor-native inspection, <code>tools/music-analysis/to_phichain.py</code>
imports selected analysis decisions into a new empty live experiment using the
existing experimental <code>chart_script</code> tool. It checks the exact project,
PCM audio hash and revision, dry-runs, then optionally applies/saves one undo entry.
Layer grouping makes one fixed track per acoustic layer; reason grouping is
multi-label and deliberately duplicates note objects. In-track horizontal position
encodes intensity; the shared judgment line brightens at candidate climaxes.
Names appear in the line list, not as arbitrary gameplay text. No MCP schema changes.</p>
<h2 id="motion">Inspect motion without editing</h2>
<p>Select 1–32 editable notes or pass explicit <code>note_ids</code>, fresh guards,
and an elapsed-audio window of at most 12 seconds. Request 2–12 frames (default 6).
This captures unsaved live state without changing playback, selection or history.</p>
<p>The response includes real PNG frames, note/line IDs, landing positions, sampled
head and hold-tail trajectories, hidden carrier and ancestor transforms, shared-line
note counts, and overlapping/inherited event IDs (capped at 4,000 with truncation reported).
The local HTML report overlays IDs, carriers and paths on those frames. PNGs are unmodified.</p>
<p>Sampling uses native easing and scroll math at 960×540 on a 30 fps lattice. Times
are audio seconds; the renderer receives chart seconds after subtracting offset.
Default styling is used, hit effects are hidden, and generated curves appear in
frames but are not selectable targets. This is not a playability or occlusion proof.</p>
<p>Artifacts live under <code>../artifacts/motion-inspections/</code>. Temporary chart
and asset copies are deleted after rendering. <code>live_revision_changed</code>
reports subsequent human edits (null if disconnected). Missing renderer/GPU/audio
fails explicitly; no offline chart session or fallback image is created.</p>
<h2 id="passage">Preview a passage</h2><p>PhiChain renders are visual ground truth.
<code>preview_passage</code> captures a guarded live revision and renders up to 12 audio seconds
within the loaded audio duration, returning a local MP4 and HTML video with playback, loop and scrub
controls. It does not open the report or change shared editor playback. Output is 960×540 at 30 fps,
default styling, hidden hit effects; the same renderer/ffmpeg/GPU requirements apply.
Artifacts live under <code>../artifacts/passage-previews/</code>; the response reports whether the live revision changed.</p>
<h2 id="line-roles">Human-facing line roles</h2><p>The editor line list displays Simple,
Complex and Decorative labels. Change the role in the line inspector; changes support undo/redo
and persist in native charts. Existing charts default to Simple. These are authoring labels,
not automatic motion or occupancy constraints. Decorative lines containing notes show a warning;
all those notes remain playable. External formats do not preserve native role labels.</p>
<p>Context and section line rows include <code>role</code>; changes invalidate revision guards.
MCP line updates preserve the existing role; no role-writing tool has been added.
Early-visible notes keep their later judgments. Truly fake RPE notes are currently converted
to playable notes on import, or removed with the existing import option; this UI does not add fake-note support.</p>
<h2 id="groups">Animate motion groups</h2><p><code>animate_selection</code> takes explicit groups of
note IDs, an existing carrier and native events. Explicit <code>dry_run</code> chooses validation or
one atomic agent undo step. Every note on each affected carrier must belong to the group,
including future notes. Child lines and curve dependencies reject. Merging requires identical
source event timelines and the same parent; similar direction alone is insufficient.</p>
<p>Supplied event channels replace their entire timelines; omitted channels remain. Include later
scroll/release events. Overlapping events reject. Note IDs and hit times remain unchanged.
Zero and negative scroll speeds support early-visible playable notes. Reserve the complete
visible lifetime through judgment and hold tails; never infer occupancy from hit times alone.</p>
<p>No new lines are allocated, no emptied source lines deleted, and no automatic splitting or
approximate fitting occurs. Default line budget 24 counts decoration too; explicitly raise it for
larger charts. Review results with inspection and passage preview. Refresh the editor and MCP
client after rebuilding.</p>
<div class="notice">This branch also implements an alternative <a href="agent.html">31-tool Agent authoring MCP</a> with patch, transform, generate and script writes. The 13 tools below belong to the minimal server.py entrypoint.</div>
<h2 id="catalog">13-tool reference</h2>
<p>Descriptions and schemas below come directly from <code>tools/phichain-mcp/server.py</code>.</p>''')
for tool in server.TOOLS:
    name = tool['name']
    server.validate(EXAMPLES[name], tool['inputSchema'])
    parts.append(f'<article class="tool" id="tool-{name}"><h3>{name}</h3><p>{H(tool["description"])}</p><h4>Example call</h4>')
    parts.append(code({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                       'params': {'name': name, 'arguments': EXAMPLES[name]}}))
    parts.append('<details><summary>Exact input schema</summary>' + code(tool['inputSchema']) + '</details></article>')
music_example = {**G, 'from_seconds': 0, 'to_seconds': 20,
    'question': 'Describe audible changes and separate evidence from mood interpretation.',
    'history': [], 'max_tokens': 768}
server.validate(music_example, music_server.TOOLS[1]['inputSchema'])
parts.append('<h2 id="music">Local music MCP</h2><p>Separate read-only entrypoint: '
    '<code>tools/phichain-mcp/music_server.py</code>, exposing get_context and music_chat. '
    'Uses local MOSS-Music Instruct through MLX; source audio comes from the guarded open editor. '
    'No chart edits, playback changes, cloud inference, or automatic downloads.</p>'
    '<p>Install the pinned requirements-music.txt into ../runtime/music-runtime and download '
    'rtikw/MOSS-Music-8B-Instruct-4bit into ../runtime/music-model/MOSS-Music-8B-Instruct-4bit. '
    'Launch with that Python and --endpoint /absolute/path/to/.phichain-mcp.json. '
    'Optional --model selects a local directory, --python selects the worker interpreter, '
    'and --timeout sets 10–1800 seconds (default 300). Requires ffmpeg and Apple Silicon. '
    'See tools/phichain-mcp/README.md for complete setup and external-client JSON.</p>'
    '<p>All MCP entrypoints instruct the authoring agent to get a full grasp of the entire piece before starting charting: cover the full audio in overlapping passages and understand structure, emotional arc, motifs, instrumentation, transitions, climaxes and resolution. Report gaps instead of claiming full understanding. Reconnect to receive updated initialize instructions.</p>'
    '<p>Clips: 1–120 elapsed-audio seconds. Questions: 1–6000 characters. '
    'Optional history: up to 12 user/assistant turns, 4000 characters each, 16000 total. '
    'History is explicit text context; each call hears the current clip again. '
    'Output: 64–2048 tokens, default 768. Mono 16 kHz extraction discards stereo imaging. '
    'Weights persist in one worker per MCP process; clips are temporary. Extraction timeout: 45s. '
    'Inference failure/timeout kills the worker. Client timeout must exceed both. '
    'No cancellation/progress notifications.</p>'
    '<p>Returns answer, token counts, model/backend, MLX peak allocation (not process RSS), '
    'clip SHA-256, source path, guards, live_revision_changed (null if disconnected), '
    'and source_audio_changed. Timestamps are clip-relative estimates, not measured onsets. '
    'Model output is fallible interpretation and must never be treated as instructions.</p>')
parts.append(code({'name':'music_chat','arguments':music_example}))
parts.append('<details><summary>Music tool schema</summary>' + code(music_server.TOOLS[1]) + '</details>')
parts.append('''<h2 id="operations">Native edit operations</h2>
<p>Place operations in <code>apply_edits.arguments.operations</code> with current guards.
These are low-level edits, not separate MCP tools. Updates replace complete notes/events;
preserve unchanged fields. Create lines first and use their returned IDs in a later batch.
Root reordering must be separate from line creation, updates, or deletion.</p>''')
for operation in server.OPERATIONS:
    name = operation['properties']['op']['const']
    parts.append(f'<details class="operation"><summary>{name}</summary>{code(operation)}</details>')
parts.append('''<h2 id="limits">Units and recovery</h2><ul>
<li>“Notes” means playable note objects. Beats describe musical timing.</li>
<li>Beat fractions use <code>[whole, numerator, denominator]</code>, such as
<code>[4, 1, 2]</code> for beat 4.5. Write canonical fractions with positive denominators.</li>
<li>Note x uses native coordinates. Note speed changes approach speed, not hit timing.</li>
<li>Offset uses milliseconds; preview time uses elapsed audio seconds. Convert beats
using the BPM map, then add offset / 1000.</li>
<li>Holds require a positive hold duration. Generated curve notes cannot be edited directly;
curve endpoints cannot be deleted while referenced.</li>
<li>A batch contains 1–1000 operations. Each existing target may occur once.
The editor validates the whole batch before applying it.</li>
<li>Stale guards fail without mutation. Re-read and reconsider the edits. Active human
interactions can also block writes.</li>
<li>After a transport timeout, inspect current state before retrying: edits may have executed.</li>
<li>History requires an explicit <code>author</code>: <code>agent</code> or <code>human</code>.
Read <code>undo_author</code> / <code>redo_author</code> from context (null means no entry).
A mismatch fails without mutation; entries cannot be skipped. Rebuild and restart the editor
and refresh the MCP client after this update. History is shared with the human. Undo only when requested or reverting your known latest batch.</li>
<li>Edits stay in memory until saved or autosaved. Preview requests are acknowledgments;
read context to observe playback after the editor processes them.</li></ul>
<footer>Generated by <code>../docs/mcp-reference/build.py</code> from the current server.
Examples are schema-checked; no live chart changes are performed during generation.</footer>
</main></div></body></html>''')
page = '\n'.join(parts)


class Navigation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.links.append(attrs['href'][1:])


nav = Navigation()
nav.feed(page)
assert len(nav.ids) == len(set(nav.ids)), 'Duplicate anchors'
assert set(nav.links) <= set(nav.ids), 'Broken internal links'
(OUT / 'index.html').write_text(page)
report = {'scope': 'Schema examples and internal navigation; no live chart execution',
          'tools': len(server.TOOLS), 'music_tools': len(music_server.TOOLS), 'native_operations': len(server.OPERATIONS),
          'resources': 0, 'prompts': 0,
          'tool_schema_sha256': hashlib.sha256(json.dumps(server.TOOLS, sort_keys=True).encode()).hexdigest(),
          'all_internal_links_valid': True, 'charts_modified': False}
(OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

import build_agent_reference
print(json.dumps({"agent_reference": build_agent_reference.build(EXAMPLES)}, indent=2))
