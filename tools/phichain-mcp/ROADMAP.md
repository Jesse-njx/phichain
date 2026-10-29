# PhiChain MCP scope

This fork keeps the editor and its live MCP bridge together. The running editor
is the single source of truth, with session/revision guards and shared undo.

The MCP server exposes nine user-approved tools: `get_context`, `read_section`,
`apply_edits`, `preview`, `history`, `save`, `inspect_motion`, `preview_passage`,
and `animate_selection`. Inspection and passage preview render guarded live
snapshots. Animation operates on explicit motion groups with complete carrier
ownership, exact compatible merging, dry-run and shared undo. It never allocates
one line per note. Early-visible notes retain their later judgment times.
See [README.md](README.md) for contracts and current limits.

There is no planned AI-charting framework. Add capabilities only when the user
explicitly designs or requests them, rather than anticipating charting needs.


Current focus is human-facing editor authoring: persisted Simple, Complex and
Decorative line labels and an undoable inspector selector. These labels do not
yet enforce complex-note occupancy or implement decorative note-shaped objects.
No additional MCP capabilities or animation presets are introduced by this work.

## Experimental rpe-next-style authoring branch

Explicitly requested by the user on 2026-10-27: retain PhiChain as the live editor
and port the rpe-next Agent chart-write vocabulary into an MCP server. The new
`agent_server.py` is a separate experimental entrypoint with 27 tools; the minimal
nine-tool `server.py` entrypoint remains available. This request expands the
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
