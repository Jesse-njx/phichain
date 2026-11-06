# PhiChain MCP scope

This fork keeps the editor and its live MCP bridge together. The running editor
is the single source of truth, with session/revision guards and shared undo.

The MCP server exposes 13 user-approved tools: `editor_status`, `create_project`,
`open_project`, `close_project`, `get_context`, `read_section`,
`apply_edits`, `preview`, `history`, `save`, `inspect_motion`, `preview_passage`,
and `animate_selection`. Inspection and passage preview render guarded live
snapshots. Animation operates on explicit motion groups with complete carrier
ownership, exact compatible merging, dry-run and shared undo. It never allocates
one line per note. Early-visible notes retain their later judgment times.
See [README.md](README.md) for contracts and current limits.

The product direction toward autonomous charting is set in the
[project roadmap](../../docs/roadmap/README.md) (2026-11-05). Note arrangement is
the current focus. That roadmap does not pre-authorize MCP tools. Add capabilities
only when the user explicitly designs or requests them, rather than anticipating
charting needs.

## MP3 note-decision analysis (2026-11-02)

The user explicitly requested a toolchain accepting MP3 audio and returning note
selection decisions, timestamps, per-decision musical intensity, and climax
sections. `tools/music-analysis/analyze.py` now provides a local CLI with JSON/CSV
and an offline audition/review report. It retains omitted candidates, separates
intensity from priority/confidence, and accepts source-bound review corrections
and optionally aligned stems. It does not edit charts or maintain authoring state;
MCP catalogs and the Rust bridge are unchanged.

The implemented selection and climax methods are acoustic heuristic baselines,
not learned musical judgment or verified transcription. Polyphonic voice choice,
hold boundaries and emotional/functional climax interpretation remain subject to
review. No difficulty, finger, lane or decorative decisions are inferred.
See [the analyzer documentation](../music-analysis/README.md) for executable
commands, exact scoring policy, outputs and validation limits.

The same-day user-requested `to_phichain.py` visualization now imports analysis
JSON into a new empty live experiment through the existing `chart_script` API.
Primary-layer tracks preserve one object per selected decision; reason tracks
are explicitly multi-label and duplicate objects for inspection. In-track x
encodes intensity and judgment-line brightness marks climax candidates.
Names use the editor line list; arbitrary gameplay text is unsupported. The
importer is guarded, dry-run first and undoable, and retains an ID/evidence receipt.
It does not create offline chart state or alter MCP/bridge capabilities.

## Local music question answering (2026-10-29)

User-requested `music_server.py` adds a separate read-only music MCP with
`get_context` and `music_chat`. A local MLX MOSS-Music Instruct worker answers
questions about guarded clips of the open project's audio. Explicit caller
history supports follow-ups; no model edits charts, no parallel authoring state,
and no automatic model downloads or remote inference. Setup and limits are in
README.md. The chart-editing tool catalogs remain unchanged. This supersedes
the historical audio-model-setup exclusion below for this specific capability.


Current focus is human-facing editor authoring: persisted Simple, Complex and
Decorative line labels and an undoable inspector selector. These labels do not
yet enforce complex-note occupancy or implement decorative note-shaped objects.
No additional MCP capabilities or animation presets are introduced by this work.

The editor also includes a whole-chart Note Density pane in the lower-right
default layout, with live note-head counts, a playback cursor and shared seeking.
Existing saved layouts receive this pane once. MCP tool catalogs are unchanged.

## Experimental rpe-next-style authoring branch

Explicitly requested by the user on 2026-10-27: retain PhiChain as the live editor
and port the rpe-next Agent chart-write vocabulary into an MCP server. The new
`agent_server.py` is a separate experimental entrypoint with 31 tools; the minimal
13-tool `server.py` entrypoint remains available. This request expands the
previous user-approved scope for this branch.

Implemented: ID-keyed native chart reads and queries, partial patch, vendored safe
numeric transform/generation, timed synchronous JavaScript candidate edits,
atomic new-object aliases, ID-preserving note moves, line subtree duplication,
native BPM/curve commands and guarded selection/diagnostics. Complete candidates
are validated in Bevy before one shared agent undo entry. Existing renderer-backed
inspection and passage preview are retained. No standalone authoring state.

Not ported: foreign data-model features (noise areas/shaders/fake notes), foreign
editor UI/generators without a native counterpart, model/chat orchestration,
asset workspaces, audio-model setup, VCS and collaboration. These are not advertised
as supported tools. Scope is the requested agent-to-chart writing workflow.

Validation covers mechanical correctness and integration, not whether a model now
produces good charts. A real creative-task comparison with the same model is still
needed before drawing that conclusion. Vendored expression code remains under
its source PolyForm Noncommercial license with required notices.

## GUI-free project lifecycle and headless host (2026-11-02)

User-requested scope: create native projects/import songs through MCP and run
the editing application without laptop GUI interaction. Both chart MCP catalogs
now expose status, create (including validated audio/optional cover copy), open
and guarded close. Creation/open report asynchronous completion through status.

`phichain --headless --mcp-endpoint PATH` hosts the existing Bevy chart and shared
command/history/serialization code without window, GPU or audio output device
initialization. Preview timing is silent; renderer-backed artifacts retain their
GPU/ffmpeg requirements. This is runtime headless support, not a build stripped
of GUI dependencies. No UI panel automation, audio replacement, model loop or
parallel authoring state is introduced. Save explicitly; no headless autosave.
