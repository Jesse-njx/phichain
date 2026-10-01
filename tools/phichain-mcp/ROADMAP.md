# PhiChain MCP development

## Repository and architecture

The repository is a clone of <https://github.com/Ivan-1F/phichain>, based on
commit `1409c19` (`v1.0.0-beta.7`). Local MCP development begins on branch
`mcp-charting`. Upstream history is preserved. The existing `origin` remote
still points to upstream; a personal hosted fork has not been created.

The current implementation has two parts:

- `phichain-editor/src/mcp.rs`: an opt-in authenticated loopback bridge that
  executes chart commands on the editor's main thread, using shared undo history.
- `tools/phichain-mcp/server.py`: a dependency-free Python stdio MCP adapter
  that validates arguments and forwards them to the running editor.

Chart rendering remains the existing `phichain-renderer` executable. Song
preparation, analysis, project bootstrapping, and rendering were orchestrated
outside MCP for the first Override study. That project is stored separately at
`/Users/jesse/Music/PhiChain/Override-opening`; its chart and audio are not part
of this source repository.

The available tools are `get_context`, `read_section`, `apply_edits`, `preview`,
`history`, and `save`. All tools below are proposals, not implemented features.

## Proposed tools, in implementation order

| Priority | Tools | What they remove from the workflow |
| --- | --- | --- |
| 1 | `editor_status`, `launch_editor`, `create_project`, `open_project`, `close_project` | Manual file dialogs, blank-project JSON creation, asset-path launch errors, and confusion between the MCP build and an older packaged app. Return the connected PID/build, endpoint state, project/session, and save state. Refuse to silently replace an unsaved project. |
| 2 | `find_local_audio`, `inspect_audio`, `import_audio` | Manual searches and one-off conversion scripts. Search specified local roots by title/artist; inspect actual codec, bitrate, duration, metadata, and artwork; extract supported local NCM files or convert only when necessary. Return an exact output path, source provenance, and whether audio was re-encoded. Preserve the source. |
| 3 | `analyze_audio`, `read_audio_features`, `set_bpm_list` | Ad hoc numerical analysis and the inability to set BPM through MCP. Return candidate BPM/offset with confidence, onset times, energy/section summaries, and optional supplied lyric cues. Measure decoder delay with the same decoder as PhiChain. Analysis suggests timing; an explicit edit applies it. |
| 4 | Extend `apply_edits` with line creation/update/reorder/delete and curve-track editing | Bootstrapping lines on disk before opening the project. This should remain one atomic edit API with session/revision guards and a shared undo step, rather than a second mutation path. Line deletion must account for dependent notes/events. |
| 5 | `render_preview`, `render_status`, `capture_preview` | Shell renderer invocation, polling, frame extraction, and opening the wrong app for visual checks. Accept an explicit time range, return a job ID immediately, then expose progress and absolute video/still paths. Render a snapshot of the current revision, including unsaved edits, and record that revision with the output. |
| 6 | `validate_chart` | Custom one-off chart checks. Report simultaneous contact demand, duplicate notes, overlapping events, holds crossing the requested boundary, offscreen hit positions, missing line speed/visibility, and timing outliers. Evaluate transforms at note times; distinguish hard errors from design choices. |
| 7 | `select_objects`, `set_editor_view`, `export_chart` | Manual navigation during joint review and command-line format conversion. Focus a beat range and objects, choose preview/timeline layout, and export a named format with a validation report. |

Audio preparation and render jobs belong in the adapter or small local worker
modules. Live chart mutations belong in the Rust bridge so validation, undo,
session protection, and the user's editor remain consistent. Reuse PhiChain's
decoder, renderer, and converter rather than building competing implementations.

## First milestone

Given a local song query and an opening duration, the tools should find and
inspect the audio, create and open a project, supply timing candidates, create
lines/BPM/notes/events through guarded edits, validate the chosen range, and
return a rendered clip. No file dialogs or hand-written project JSON should be
required. The agent still makes the musical and visual charting decisions.

## Verification

```sh
cargo test -p phichain mcp::tests
python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py' -v
git diff --check
```

The initial baseline passes 13 Rust MCP tests and 5 Python adapter tests,
including a stdio MCP subprocess editing a live Bevy world. Build artifacts,
local app bundles, endpoint credentials, and Python bytecode remain untracked.
