# PhiChain MCP

This is an extension of the upstream PhiChain editor, not a separate charting
application. The Rust bridge runs inside the editor; `server.py` adapts MCP stdio
requests to that bridge. See [ROADMAP.md](ROADMAP.md) for repository provenance,
the implemented tool groups and verification from the Override opening study.

A local stdio MCP server for coordinating Codex with the **running** PhiChain editor. No embedded chat, model API key, or Python packages are needed. Python 3.9+ is sufficient for the adapter. Audio tools use `ffmpeg`/`ffprobe`;
NCM extraction also uses `openssl`. Rendering and export use the existing
PhiChain renderer and converter executables.

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

Restart the Codex chat/client as needed to load the newly configured server. The server can initialize before the editor starts; live chart tools require an open project; search, import, launch, and explicit-path analysis do not. The adapter re-reads the endpoint on each call, so it can reconnect after an editor restart. Do not run the adapter directly in a terminal expecting an interactive prompt: stdin/stdout carry MCP JSON-RPC messages.

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
| `apply_edits` | Create/update/delete notes and events; set metadata or audio offset. Validate the entire batch, then apply as one undo step. Returns created IDs and before/after changes. |
| `preview` | Play, pause, or seek the shared preview using seconds. |
| `history` | Undo or redo one entry in the shared editor history. |
| `save` | Write the live chart and metadata to the open project. |

Try: **“Look at my selected notes, simplify their rhythm while keeping the first and last notes, then preview that section.”**

### Editing contract

1. Read context and the relevant section first. Object IDs are opaque strings scoped to the project session.
2. Send `session` and `revision` from the latest read with edits, history actions, or save. The revision is a content fingerprint, not a sequence number; it includes project data, editable object IDs, curve track configuration, and the history cursor, but excludes playback and selection.
3. If the human changes chart data, a stale batch fails before any changes are applied. Read again and regenerate the intended edits. Active mouse/text interactions, edits marked `Pending`, and queued human commands also block writes. Inspector undo baselines are refreshed after agent edits and history operations.
4. Updates replace the entire note/event. Preserve fields you were not asked to change. Existing targets may appear only once per batch. Create operations reference existing lines; line and curve operations are described below; BPM changes use `set_bpm_list`.
5. Each successful batch is one history entry. History is shared with the human; do not blindly undo after a human edit.
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

## Verification

```sh
cargo test -p phichain mcp::
python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py' -v
```

Rust tests cover actual editor commands, grouped undo/redo, stale sessions and human edits, invalid-batch atomicity, malformed beats, curve protections, serialization/save, bridge authentication, endpoint cleanup, and a full stdio MCP subprocess editing a live Bevy World through the bridge. Python tests cover MCP lifecycle, schema validation, JSON-RPC errors, and loopback transport.

## Project, audio, and artifact tools

The adapter now provides `editor_status`, `launch_editor`, `create_project`,
`open_project`, `close_project`, `project_snapshot`, `find_local_audio`,
`inspect_audio`, `import_audio`, `render_preview`, `capture_preview`,
`render_status`, and `export_chart`.

Use `editor_status` even on the home screen. `launch_editor` launches the configured
build and supplies asset paths; poll status until the bridge is connected. An
existing unreachable endpoint is never overwritten. Opening requires an empty
editor; closing requires a saved project and current session/revision. Poll
status after either request; loading errors appear as `last_error`.

All paths must be absolute. Source songs remain untouched. Import and project
creation refuse existing destinations, and imports report whether they reencoded
the original audio. Search uses normalized filename terms and explicit roots, and checks embedded
title/artist aliases by default (`search_metadata=true`). `metadata_limit` bounds
these inspections to 200 by default, at most 500; the result reports that bound.
Use `inspect_audio` for full codec and metadata details. NCM artwork can be
embedded or stored in NetEase's adjacent `meta` directory.

Render, capture, and export accept current `session`/`revision` guards and take a
native chart snapshot without saving. They return a `job_id`; poll `render_status`
for `completed` or `failed`, an absolute output path, and diagnostics. Jobs persist
under the local temporary directory across adapter restarts. Render ranges use
elapsed audio seconds and are limited to ten minutes per job. Outputs never
replace existing files. Temporary chart/audio snapshots are removed when jobs end.

The adapter finds source builds in `target/debug` or `target/release`, then the
local macOS bundle. Override executable paths with `--editor`, `--renderer`,
`--converter`, `--ffmpeg`, or `--ffprobe`; each override takes an absolute path.

## Charting QoL

`apply_edits` also supports `create_line` (name, optional parent_id),
`update_line` (id, name, optional parent_id; null moves to root),
`delete_line` (id, explicit cascade=true for lines with dependent objects),
`reorder_lines` (every root line_id exactly once), and
`create_curve_track` / `update_curve_track` / `delete_curve_track`.
Create a line first, then use its returned ID in a subsequent batch for notes.
Root reordering must be separate from line create/update/delete operations.
Hierarchy cycles, conflicting subtree edits, and deleting the final existing
root line are rejected. Subtree undo/redo preserves editable IDs.

Curve creation takes line_id, from_id, to_id, and options:
`{"kind":"drag","density":16,"curve":{"type":"linear"}}`.
Updating takes the track id and the same endpoints/options; deletion takes id.
Endpoints must be editable notes on the track's line, ordered in time. Density
is bounded to 1–256 and generated count to 10,000. Hold curve options also need
hold_beat. Generated curve notes remain read-only.

`validate_chart` accepts a beat range, aspect_ratio (default 16:9), and
max_contacts (default 2). Findings include native curve notes, transformed hit
positions, audio and hold boundaries, duplicate notes, event overlaps, scroll
speed, and judge-line visibility. Contact demand is a conservative onset/hold
count: it is a warning, not proof of playability. Findings are capped at 2,000.

`select_objects` accepts session, ids, and optional line_id; an empty ids array
clears selection. `set_editor_view` accepts session and optional focus_beat,
zoom (0.1–5), density (1–256), show_spectrogram, or layout (default/preview).
These change the shared review UI, not chart history. Focus queues a seek and
pauses playback; observe context afterward.

## Song analysis

`analyze_audio` starts a background job and returns `analysis_id`. Supply an absolute
`path`, or omit it to use the open project's audio. Import NCM first. Optional
`from_seconds` / `to_seconds` bound a 2–600 second range (default first 60 seconds);
`bpm_min` / `bpm_max` default to 80–240 and allow 30–400. Optional `lyrics_path` supplies local LRC timestamps and text. `read_audio_features` polls the job and
returns timing candidates, onsets, energy, possible section boundaries, and cues.

Analysis uses PhiChain's own decoder and estimates BPM/offset from spectral flux
and onset timing. Confidence is heuristic; the first strong onset is a proposed
beat-zero anchor, and the musical downbeat is unverified. Energy changes do not
identify vocals or instruments. Silence returns no tempo candidate. Nothing is
applied to the chart automatically.

The adapter compares the first audible sample in a short ffmpeg reference decode
with the native decoder and reports a measured decoder delay with uncertainty.
Native onset times remain in the editor's audio clock. A `lyrics_path` can supply
standard LRC or NetEase colon-separated fractional timestamps; lyric timestamps
are preserved, without automatic delay correction.

Jobs are cached in the editor process (up to 16 retained, two running). Adapter
restarts preserve access; editor restarts clear this cache. Feature reads accept
`from_seconds` / `to_seconds` and `onset_offset` / `limit` for pagination.

`set_bpm_list` takes current `session`, `revision`, and a `bpm_list` of
`{"beat":[0,0,1],"bpm":204.0}` entries. The first entry must start at beat zero;
subsequent beats must increase strictly. The entire list is validated and applied
as one shared undo step, using PhiChain's native beat/time conversion. Set audio
offset separately with `apply_edits` after reviewing the proposed timing.

A complete workflow is: search → inspect/import → create project → launch/open
and poll status → analyze and poll features → set BPM/offset → edit and validate
→ render and poll output → save. These steps use MCP tools without file dialogs.
