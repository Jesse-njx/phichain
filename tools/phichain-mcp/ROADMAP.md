# PhiChain MCP development

## Repository and architecture

This repository extends [upstream PhiChain](https://github.com/Ivan-1F/phichain),
based on `1409c19` (`v1.0.0-beta.7`), on branch `mcp-charting`. Upstream history
is preserved. Our fork is https://github.com/Jesse-njx/phichain; `origin` points
to the fork and `upstream` points to Ivan-1F/phichain. The editor and its MCP
server are developed together in this repository.

The running editor is the source of truth for chart authoring. New planning,
evidence and review capabilities belong in this live bridge, using the shared
project session, revision guards and undo history. Do not introduce a parallel
offline chart store. The separate phigros-chart-mcp project is historical work;
its useful capabilities still need to be ported to this bridge.

The authenticated loopback bridge in `phichain-editor/src/mcp.rs` executes
commands on Bevy's main thread. Its `structure.rs`, `quality.rs`, and
`analysis.rs` modules handle chart structure, review/validation, and native audio
analysis. Mutations share the editor's undo history and session/revision guards.

`tools/phichain-mcp/server.py` exposes MCP stdio with argument validation.
`local_tools.py` prepares local audio and projects and launches binaries;
`worker.py` runs persisted render/export jobs. Rendering and export reuse the
existing PhiChain renderer and converter. See [README.md](README.md) for usage.

## Implemented groups

| Commit | Capabilities |
| --- | --- |
| `no more computer use` | Editor status/launch/open/close, project creation and snapshots, local audio search/inspection/import including NCM, asynchronous preview rendering, still capture, job status, and chart export. |
| `charting QoL` | Atomic line hierarchy/reordering/deletion and curve-track edits, shared undo, chart validation including generated notes and transforms, selection and editor view controls. |
| `song analysis` | Metadata-aware song search, native-decoder onset/energy analysis, BPM/offset candidates, decoder-delay measurement, supplied LRC cues, feature pagination, and atomic BPM-list editing. |

The original context, section read, note/event editing, preview, history, and save
tools remain available. A local song can now become an open project, receive
reviewed timing and chart edits, and produce a rendered opening through MCP,
without desktop automation or hand-written project JSON.

## Limits and review

The agent still makes musical and visual charting decisions. Tempo confidence
is heuristic, downbeat placement requires review, and energy boundaries do not
classify musical semantics. Supplied lyrics retain their original timestamps.
Validation reports design warnings and conservative contact demand rather than
proving playability. Export uses converter diagnostics; call `validate_chart`
separately for native chart findings. Local imports and outputs never overwrite
existing files, and the source song remains untouched.

## Verification

```sh
cargo test -p phichain
python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py' -v
cargo fmt --all -- --check
git diff --check
```

The implementation has 21 Rust MCP tests and 15 Python adapter tests. Live stdio
smoke tests additionally exercised the actual rebuilt editor: NCM import,
project lifecycle, unsaved snapshots/render/export, line/curve editing and undo,
selection/view, validation, and analysis of the downloaded Override recording.
That opening produced a 204 BPM candidate and approximately 25.06 ms measured
native MP3 decoder delay. Analysis did not change the live chart; setting BPM
was separately tested with undo. The study audio/chart remain outside this repo.

Build artifacts, local bundles, endpoint credentials, and Python bytecode remain
untracked. New native tools require launching the rebuilt editor; clients also
need to reload the adapter's updated tool inventory.
