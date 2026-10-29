# PhiChain MCP

A minimal, dependency-free Python 3.9+ stdio adapter for the running PhiChain
editor. It exposes nine tools and forwards validated requests to the live Rust
bridge. Open the editor and a project yourself before using chart tools.

## Start the editor

From the repository root:

```sh
cargo run -p phichain -- --mcp-endpoint "$PWD/.phichain-mcp.json"
```

Open a project normally, or add `--project /absolute/path/to/project`.

When running `target/debug/phichain` directly, set
`CARGO_MANIFEST_DIR="$PWD/phichain-editor"` so the editor can find its language
files. Launch the same build you connect to: an older packaged app can open a
separate editor instance without the MCP bridge.
The MCP bridge is opt-in. It binds an ephemeral port on `127.0.0.1`, writes a random authentication token to the endpoint file, and handles commands on Bevy's main thread. On Unix the file has mode `0600`. On other platforms, keep it in a directory private to your user.

The endpoint file is removed on a clean shutdown. After a crash, check that the editor identified by the file's `pid` has exited before deleting the stale file and restarting. Existing endpoint files are never silently replaced. Use separate endpoint paths for separate editor instances.

## Connect Codex

From the repository root, register the stdio server:

```sh
codex mcp add phichain -- python3 "$PWD/tools/phichain-mcp/server.py" --endpoint "$PWD/.phichain-mcp.json"
```

Restart the Codex chat/client as needed to load the newly configured server. The server can initialize before the editor starts; all nine tools require an open project. The adapter re-reads the endpoint on each call, so it can reconnect after an editor restart. Do not run the adapter directly in a terminal expecting an interactive prompt: stdin/stdout carry MCP JSON-RPC messages.

Alternatively, add this entry to a trusted project's `.codex/config.toml` (replace the absolute paths):

```toml
[mcp_servers.phichain]
command = "python3"
args = ["/absolute/path/to/PhiChain/tools/phichain-mcp/server.py", "--endpoint", "/absolute/path/to/PhiChain/.phichain-mcp.json"]
```

## Tools

| Tool | Behavior |
| --- | --- |
| `get_context` | Project/audio file paths, metadata, BPM, offset, line hierarchy, selected objects, current beat, audio and chart time, playback and history state. |
| `read_section` | Notes, overlapping holds and line events in a beat range, optionally on one line; curve track references. |
| `preview_passage` | Render a guarded live passage as a local looping, scrubbable video without touching editor playback. |
| `animate_selection` | Apply explicit shared motion groups on existing carriers, with exact compatible merging, dry-run and one undo step. |
| `inspect_motion` | Render a guarded live snapshot and inspect selected notes, carrier lines, trajectories and source events without changing playback or chart state. |
| `apply_edits` | Create/update/delete notes, events, lines and curve tracks; reorder lines; set BPM, metadata or audio offset. Validate the entire batch, then apply as one undo step. Returns created IDs and before/after changes. |
| `preview` | Play, pause, or seek the shared preview using seconds. |
| `history` | Undo or redo one entry; required `author` (`agent` or `human`) must match the next entry. |
| `save` | Write the live chart and metadata to the open project. |

Try: **“Look at my selected notes, simplify their rhythm while keeping the first and last notes, then preview that section.”**

### Editing contract

1. Read context and the relevant section first. Object IDs are opaque strings scoped to the project session.
2. Send `session` and `revision` from the latest read with edits, history actions, or save. The revision is a content fingerprint, not a sequence number; it includes project data, editable object IDs, curve track configuration, and the history cursor, but excludes playback and selection.
3. If the human changes chart data, a stale batch fails before any changes are applied. Read again and regenerate the intended edits. Active mouse/text interactions, edits marked `Pending`, and queued human commands also block writes. Inspector undo baselines are refreshed after agent edits and history operations.
4. Updates replace the entire note/event. Preserve fields you were not asked to change. Existing targets may appear only once per batch. Create operations reference existing lines; line and curve operations reference existing IDs; BPM changes use the `set_bpm_list` operation.
5. Each successful batch is one history entry. Context reports `undo_author` and `redo_author` (`agent`, `human`, or null). `history` requires an explicit matching `author` for both undo and redo; a mismatch fails without mutation. It cannot skip entries. History is shared with the human; do not blindly undo after a human edit.
6. Edits remain in memory until `save`, normal editor save, or existing autosave behavior. `preview` returns a request acknowledgment; read context afterward to observe actual playback state. Seek positions are clamped by the editor to the audio duration.
7. After a transport timeout, read state before retrying an edit: it may already have executed. Queued requests expire before execution after ten seconds. No automatic mutation retries occur.

Beats use `[whole, numerator, denominator]`, for example `[4,1,2]` is beat 4.5. For MCP writes, fractions must be canonical: `0 <= numerator < denominator <= 10000`, with whole parts between -1000000 and 1000000. Notes must start at nonnegative beats, holds have positive durations, and note speed must be positive. Events must have nonnegative, ordered beat ranges. Generated curve notes cannot be edited directly, and curve track endpoints cannot be deleted.

Example `apply_edits` arguments:

```json
{
  "session": "session-from-read",
  "revision": "revision-from-read",
  "operations": [
    {
      "op": "create_note",
      "line_id": "line-id-from-context",
      "note": {
        "kind": "tap",
        "above": true,
        "beat": [4, 1, 2],
        "x": 120.0,
        "speed": 1.0
      }
    }
  ]
}
```

For hold notes use `"kind": "hold"` plus `"hold_beat": [1,0,1]`.
Event values are `{"type":"constant","value":10}` or a transition such as `{"type":"transition","start":0,"end":100,"easing":{"type":"linear"}}`.
Audio offset uses PhiChain's native serialized units (milliseconds). Preview `time_seconds` and context `time_seconds` are elapsed audio seconds; context `chart_time_seconds` subtracts the offset. To preview a chart beat, convert it using the BPM list and add `offset / 1000`.

## Inspect motion

Use `get_context` and `read_section` to choose the actual note IDs, then call:

```json
{
  "session": "session-from-read",
  "revision": "revision-from-read",
  "note_ids": ["1002", "1003"],
  "from_seconds": 10.8,
  "to_seconds": 20.4,
  "frames": 6
}
```

Omit `note_ids` to inspect the editor's current selected editable notes. An empty
selection fails; it never substitutes all notes. IDs are returned explicitly,
not interpreted as ordinal note numbers. Limits: 1–32 targets, 2–12 frames,
a positive range of at most 12 seconds, and times within the audio duration
(maximum 24 hours). Targets cannot be generated curve notes; generated notes
still appear in the rendered scene.

The bridge checks session/revision and idle state, samples the native easing,
scroll integration and parent transforms, then serializes that same live revision.
No seek, playback, selection, history, save, or chart mutation occurs. The adapter
renders a temporary immutable snapshot, including unsaved changes, and removes
the temporary project afterward. This is not an offline authoring session.

The response contains actual PNG images as MCP image content and structured data:

- `notes`: IDs, carrier IDs, original note fields, judgment times and landing positions.
- `frames`: audio and chart timestamps, selected note heads/hold tails, timing/cover
  visibility, and carrier/ancestor positions, rotations, opacity and scroll speed.
- `lines`: carrier/ancestor IDs and total editable note counts, showing shared use.
- `events`: overlapping and latest inherited events on those lines, with editable
  IDs; `event_count` and `events_truncated` explicitly report the 4,000-event cap.
- `report_path`: local HTML with toggleable IDs, hidden carrier lines and sampled
  trajectories over the real images; `inspection.json` retains the exact evidence.
- `live_revision_changed`: whether a final context read differs from the captured
  revision; null if the editor can no longer be checked. Re-read before editing.

Frames use 960×540, default renderer styling, hidden hit effects and a 30 fps time
lattice. Pixel coordinates have a top-left origin. The renderer receives chart
seconds (audio seconds minus offset), so nonzero offsets are preserved. Source
events cover the requested window and inherited values; numerical scroll samples
integrate all preceding speed events. Sampled paths are not continuous collision
or human-playability proofs. PNG images themselves are unmodified; the optional
HTML overlay is diagnostic. Custom editor skins/settings are not reproduced.

Build `phichain-renderer` and install `ffmpeg` on PATH; a working GPU is required.
The adapter searches `target/debug`, `target/release`, the local macOS bundle,
then PATH. Use `--renderer /absolute/path/to/phichain-renderer` to select a build.
Rendering has a 90-second timeout; each frame extraction has a 20-second timeout.
Failures report the missing prerequisite or diagnostic and never change the live
project. There is no background job/polling API or silent schematic fallback.
Artifacts remain under ignored `local/motion-inspections/`; source chart/audio
snapshots are temporary. Provide links without opening reports in Codex.

Rebuild/restart the editor and refresh the MCP client to load `inspect_motion`.
An older editor reports an unknown command rather than using another chart source.

## Verification

```sh
cargo test -p phichain mcp::
python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py' -v
```

Rust tests cover actual editor commands, grouped undo/redo, stale sessions and human edits, invalid-batch atomicity, malformed beats, curve protections, serialization/save, bridge authentication, endpoint cleanup, and a full stdio MCP subprocess editing a live Bevy World through the bridge. Python tests cover MCP lifecycle, schema validation, JSON-RPC errors, and loopback transport.

Rebuild and restart PhiChain and refresh the MCP client for the required history author argument. Example: `{"session":"session-from-read","revision":"revision-from-read","action":"undo","author":"agent"}`. Authorship stays attached to each history entry through undo/redo and branching.

## Scope

The MCP interface contains only the nine tools above. `apply_edits` provides
literal editor operations; charting decisions belong to the user and agent.
There are no presets, authoring plans, evidence caches, analysis tools, project
management, audio import, background render jobs, MCP resources, or prompts.
New tools will be added when the user designs and requests them.

The adapter accepts `--endpoint` and optional `--renderer` (an absolute executable
path used by `inspect_motion` and `preview_passage`). Other legacy executable overrides are unsupported. Restart the MCP client to refresh the tool list.
The six core tools and `animate_selection` are direct bridge calls.
`inspect_motion` and `preview_passage` render immutable snapshots captured from the live editor.


## Passage preview and motion groups

PhiChain renders are visual ground truth for review. `preview_passage` takes
`session`, `revision`, `from_seconds`, and `to_seconds` (elapsed audio, maximum
12 seconds, within loaded audio). It returns `video_path`, `report_path`, the
captured guard and `live_revision_changed` (null if disconnected). The HTML video
has native play/pause, scrub and loop controls; it does not open automatically.
This first version renders a bounded passage, rather than controlling a live
editor playback loop. It uses 960×540 at 30 fps with default styling and hidden
hit effects. It requires the same renderer, ffmpeg and GPU as inspection.
Artifacts stay under ignored `local/passage-previews/`; temporary source snapshots
are removed, and failed renders remove partial output. No offline authoring fallback.

`animate_selection` requires fresh guards, explicit `dry_run`, and 1–24 `groups`.
Each group supplies `carrier_id`, 1–1000 explicit `note_ids`, and 1–512 native
`events` (same event schema as `apply_edits`). Each supplied channel replaces
its **whole timeline** on the destination carrier. Include the approach, animation,
release and later scrolling in that timeline; omitted channels remain unchanged.
Events must have positive duration and cannot overlap within a channel.

All notes on every affected carrier must be included, even ones hit much later.
Child lines, curve tracks/generated notes, overlapping groups, stale guards and
incompatible source timelines reject the entire call without mutation. Merging
requires exactly matching event timelines and the same parent; similar direction
alone is insufficient. Note IDs, kinds, positions, speeds, judgment times and hold
lengths are retained; only carrier membership and explicit events change.
The tool does not allocate new lines, delete emptied source lines, fit approximate
trajectories, or automatically split a partly selected carrier. Isolate such
selections before using it. Source lines remain available for later deliberate reuse.

The default `line_budget` is 24 and counts all lines, including decorative lines.
Charts already above it need an explicit higher budget (maximum 1024). This is a
workflow budget, not an RPE format constraint. The response reports groups,
replaced channels, removed event IDs, total/new line counts and undo steps.
`dry_run:true` validates and reports without editing; `false` commits all groups
as one agent undo entry, without saving. Limit: 4000 internal commands per call.

Early-visible notes are ordinary playable notes with a later judgment time.
Keep their hit times fixed and animate carrier position/rotation plus line scroll:
zero speed can suspend approach, and negative then positive speed can release it.
Changing speed changes the integrated approach distance, so review the entire
appearance-to-judgment interval and hold tail, not only the animation interval.
This implementation requires whole-carrier ownership instead of guessing a safe
reuse window from hit times. Use `inspect_motion` for frame-level evidence and
`preview_passage` for continuous perception before and after editing.

```json
{"session":"session-from-read","revision":"revision-from-read","dry_run":true,
 "groups":[{"carrier_id":"1001","note_ids":["1002","1003"],"events":[
   {"kind":"x","start_beat":[0,0,1],"end_beat":[4,0,1],
    "value":{"type":"constant","value":120}}
 ]}]}
```

Rebuild/restart the editor and refresh the MCP client for the new tools. No live
chart is changed by installing or testing them.


## Editor line roles

The human-facing editor now displays Simple, Complex and Decorative role labels
in its line list, with an undoable Role selector in the line inspector. Roles are
saved in native PhiChain charts; legacy charts default to Simple. These describe
intent, without changing playback or implementing automatic carrier allocation:
Simple shares movement across notes, Complex is intended for one independently
animated active note at a time, and Decorative is intended for visual lines with
no playable notes. The inspector warns when a Decorative line contains notes;
changing its label never removes notes or exempts them from judgment.

`get_context` and section line rows include `role`; role changes invalidate revision
guards. Existing MCP line renames/reparenting preserve the role. No new MCP tool
or role-writing argument is added. External RPE/official export does not retain
these native authoring labels.

Early-visible notes remain playable at their later judgment times. PhiChain does
not currently represent truly non-playable fake notes: RPE import converts them
to playable notes by default, or removes them when `remove_fake_notes` is enabled.
The role UI does not change this existing conversion policy. Decorative note-shaped
objects and complex-carrier occupancy validation are not implemented by these labels.

## Experimental rpe-next-style authoring server (this branch)

The `rpe-agent-mcp` branch adds `agent_server.py`. It still connects to the same
running PhiChain editor and uses the same endpoint, session/revision guards,
native renderer, save path and shared human/agent undo history. There is no
standalone chart store or dependency on a running rpe-next editor.

Build/restart the editor with this branch, then register the **experimental** entry:

```sh
cargo build -p phichain
codex mcp add phichain-agent -- python3 "$PWD/tools/phichain-mcp/agent_server.py" --endpoint "$PWD/.phichain-mcp.json"
```

Restart/refresh the MCP client afterward. Prefer enabling one PhiChain entry in a
chat to avoid duplicate tool names. Do not restart an editor containing unsaved
work without saving through the normal UI first. The existing `server.py` still
advertises its original nine tools; `agent_server.py` advertises those nine plus
18 authoring tools (27 total). Python 3.9+ supports patch/read operations; **Node.js
22.13+ with permission-mode support** is additionally required for transform,
generate and JavaScript scripts. No npm packages are required. `node` must be on
the MCP process's PATH. Render tools retain their renderer/ffmpeg/GPU prerequisites.

| Tool | Purpose |
| --- | --- |
| `editor_context` | Live context, selection, session/revision and actual capabilities. |
| `chart_read` | Read any native field or page through editable ID-keyed collections. |
| `chart_query` | Filter/project/sort one collection, optionally by beat overlap. |
| `chart_templates` | Complete native templates, explicit easing schema and script API. |
| `chart_patch` | Partial field writes, removal and insertion, without resending objects. |
| `chart_transform` | Batch safe numeric expressions or removal across selected IDs. |
| `chart_generate` | Template sequence generation using `i`, `N`, `u` and expressions. |
| `chart_script` | Synchronous JavaScript modifying a complete fresh candidate document. |
| `line_manage` | Create, duplicate a subtree, delete, reorder, reparent or rename lines. |
| `bpm_set` | Replace the complete native BPM map. |
| `curve_notes` | Create a native generated curve track between existing endpoints. |
| `editor_entities` | Find native names/IDs without confusing numeric names with beats. |
| `editor_navigate` | Seek/play/pause with explicit audio seconds, chart seconds or beats. |
| `editor_view` | Select editable objects and optionally their line. |
| `diagnose` | Guarded native structural/motion checks. |
| `chart_tools`, `agent_tools` | Discover actual tool descriptions/schemas, no hidden activation. |
| `project_save` | Alias of guarded native save. |

### Candidate document and atomic commits

`editor_context` returns fresh guards. `chart_read` with `path=""` returns the
available document fields/counts; `/notes` and the other editable collections
return ID-keyed rows with pagination. Read a particular object with a path such as
`/notes/123/note`. All reads other than context/templates/discovery require the
current session and revision. Existing `read_section` remains useful for passage
reads; `chart_query` can sort all notes by `/note/beat` and return exactly the
requested number. Ties sort by ID; notes stored on separate lines are still in one
flat native collection. Beat overlap is not visibility: inspect earlier speed
and parent events and full hold tails when designing motion.

A writable document has exactly these fields:

```json
{
  "lines": {"123": {"name": "Carrier", "role": "complex", "parent_id": null, "order": 0}},
  "notes": {"456": {"line_id": "123", "note": {"kind": "tap", "above": true, "beat": [4,0,1], "x": 100, "speed": 1}}},
  "events": {},
  "curve_tracks": {},
  "meta": {"name": "Example", "composer": "", "charter": "", "illustrator": "", "level": ""},
  "bpm_list": [{"beat": [0,0,1], "bpm": 120}],
  "offset": 0
}
```

This is PhiChain's **native authoring view**, not RPE JSON. Existing object keys
are opaque IDs. New keys use unique `new:name` aliases (5–80 ASCII bytes containing
letters, numbers, underscore, hyphen or colon). Aliases can reference each other:
create a line and insert/move its notes/events in the same candidate. Numeric
unknown IDs and cross-type ID reuse reject. Successful writes return `created_ids`
mapping aliases to stable native IDs; reread before the next operation.
New lines receive missing native baseline channels (x/y/rotation=0, opacity=255,
speed=10), making them visible and scrolling by default. Any explicitly supplied
channel, including zero/negative speed or opacity, is preserved. Baseline inserts
appear in dry-run diffs and the same undo entry. Existing lines are never seeded.

Every chart-write tool requires explicit `dry_run`. Start with `true`: the
candidate goes through native validation but neither the world nor history
changes. Reinvoke with fresh guards and `false` to commit. A dry run is not a
retained plan/token; scripts are recomputed and should be deterministic if the
user expects an identical result. Native validation checks note/event fields,
canonical beats, BPM, line cycles, root orders, all references, curve ownership,
durations and generation limits before any entity allocation. Unknown or missing
fields reject instead of silently losing data. Native floating-point fields are
normalized to f32. The document permits at most 20,000 editable objects; the
candidate bridge's 16 MiB limit may bind first (public MCP requests remain 1 MiB). Each successful changed candidate
is one agent history entry. No-op candidates create no entry. Undo/redo restores
existing/new object IDs, parent/event relationships and metadata/BPM/offset.
Generated curve notes are rebuilt derived state and have no stable editable IDs.

The adapter only holds a temporary computation copy, captures no independent
persistent authoring state, and commits through the live bridge. Any intervening
human edit causes final guard validation to fail. Direct note moves preserve
local fields, including judgment timing and hold durations, but do not compensate
for different parent/event transforms. Scripts must explicitly perform any such
compensation; inspect actual renders afterward.

### Expressions and scripts

`chart_transform` uses `path="/notes"` (or another collection), optional `ids` and
`where`, and relative expression paths such as `{"/note/x":"-x"}`. Numeric fields
of the nested note/event (or line row), `beat`, `i`, `N` and `u` are available.
Selection uses original collection order; evaluation uses selected sequence order.
All fields in a row are evaluated from its original values. Beat-field expression
results are converted to canonical fractions with 1/10000 resolution. Conditions
and expressions use the vendored rpe-next numeric parser, not JavaScript eval.
`ease(t,id)` uses the original RPE numbered easing mapping; native event easing
uses the explicit named PhiChain easing schema from `chart_templates`.

`chart_generate` takes a complete row template, count (1–10,000), expression map
and optional alias prefix. Both existing IDs and new aliases are checked again
inside the editor. Use row templates from `chart_templates`, retaining wrappers
like `{line_id,note}` and `{line_id,event}`.

`chart_script` executes synchronous JavaScript with `chart`, `api`, and optional
`input`. Mutate the document or return `{chart, result}`. The API includes
`createNote`, `createLine`, `createEvent`, `id`, `fromNumber`, `beatValue`, `clone`
and `report`; exact signatures come from `chart_templates`. There is no async,
DOM, editor instance, `process`, `require`, filesystem or network API supplied to
the script. It runs in a fresh VM context in a separate memory-limited Node
process, under Node permission mode with only the adapter source directory
readable. Credentials and the editor endpoint are not passed to that process.
This is computation isolation, not a claim that Node VM is an OS security boundary.
Default timeout is 10 seconds; permitted range is 100–30,000 ms. Timeout/errors
never submit a candidate. Computation input is capped at 16 MiB and output at
8 MiB; the final candidate bridge request must fit in 16 MiB. Public MCP request
size remains 1 MiB. Do not automatically retry writes after transport loss.

Example: isolate existing notes on a new line, preserving native note IDs and
judgment times, in one candidate:

```javascript
const carrier = api.id("carrier");
const order = Math.max(...Object.values(chart.lines).map(line => line.order)) + 1;
chart.lines[carrier] = api.createLine("Independent", order);
for (const id of input.note_ids) chart.notes[id].line_id = carrier;
api.report({ moved: input.note_ids.length });
```

### Port scope and source provenance

This branch ports the **chart-writing workflow** into PhiChain. It copies the
rpe-next expression engine and adapts its patch/transform/generate/script
contracts to native PhiChain data. It does not copy the foreign editor/runtime
or pretend PhiChain supports RPE noise areas, shaders, fake notes, text/noise
fitting, aggregate trajectory objects, Demucs, a separate chat loop, asset
workspaces, VCS or collaboration. Those native rpe-next commands are not advertised
as working PhiChain tools. General supported note/event algorithms can be written
through `chart_script`; this does not make unsupported chart fields valid.
The existing renderer-backed inspection/passage tools provide visual review.

Vendored files are pinned to rpe-next commit
`274bc55866dc5893e68c95bb4107f79711f1aa1d`. Their **PolyForm Noncommercial 1.0.0**
license and required notices are preserved in `vendor/rpe-next/`; they are not
covered by this repository's root license. The only source change to the copied
expression parser is replacing its editor translation import with standalone
error messages. No foreign assets or charts are included.

The HTML reference is generated as `local/mcp-reference/agent.html`, linked from
the existing reference. Rebuild with `python3 local/mcp-reference/build.py`.
Verification adds candidate atomicity/identity/undo tests, script timeout/isolation,
expression/generation tests, and real stdio-to-Bevy authoring integration.
