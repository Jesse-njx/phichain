# PhiChain MCP

This is an extension of the upstream PhiChain editor, not a separate charting
application. The Rust bridge runs inside the editor; `server.py` adapts MCP stdio
requests to that bridge. See [ROADMAP.md](ROADMAP.md) for repository provenance,
the current boundary, and proposed tools informed by the Override opening study.

A local stdio MCP server for coordinating Codex with the **running** PhiChain editor. No embedded chat, model API key, or Python packages are needed. Python 3.9+ is sufficient.

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

Restart the Codex chat/client as needed to load the newly configured server. The server can initialize before the editor starts; tool calls require an open project. The adapter re-reads the endpoint on each call, so it can reconnect after an editor restart. Do not run the adapter directly in a terminal expecting an interactive prompt: stdin/stdout carry MCP JSON-RPC messages.

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
4. Updates replace the entire note/event. Preserve fields you were not asked to change. Existing targets may appear only once per batch. Create operations reference existing lines; creating lines, changing BPM, and editing curve tracks are outside this initial tool set.
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
cargo test -p phichain mcp::tests
python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py' -v
```

Rust tests cover actual editor commands, grouped undo/redo, stale sessions and human edits, invalid-batch atomicity, malformed beats, curve protections, serialization/save, bridge authentication, endpoint cleanup, and a full stdio MCP subprocess editing a live Bevy World through the bridge. Python tests cover MCP lifecycle, schema validation, JSON-RPC errors, and loopback transport.
