# Current state (2026-11-05)

What already exists, grouped by the step it serves. Paths are relative to the
repository root.

## Shared infrastructure

- **Live editor + MCP bridge** (`agent-tools/Phichain/editor/src/mcp/`, `agent-tools/Phichain/mcp/server.py`):
  guarded reads, dry-run edits, shared undo, previews. The single source of truth
  for any chart an agent writes. See `agent-tools/Phichain/mcp/README.md`.
- **Agent evaluation** (`research-tools/agent-evals/`): L0 validity, L1 detectors against
  official charts, L2 blind user review. The agent runner that would drive
  unattended authoring runs is not built yet.
- **Design guidance** (`prompts/charting/rules.md`, `prompts/charting/design.md`): accumulated user
  corrections and baseline principles. Today they are written for an agent that
  receives per-passage direction; much of it is the raw material for autonomous
  decision rules.

## Step 1: note arrangement

- **Official reference corpus** (`research/arrangement-training/`): 327 Phigros IN
  charts, 300,631 notes, with integrity verification.
- **Single-line representation** (`preprocess.py`): projects near-vertical
  approaches onto one horizontal line; 4,080 windows split by song
  (261 / 33 / 33 train / validation / test).
- **Masked arrangement model** (`masked_model.py`, `train.py`, `arrange.py`): an
  initial small Transformer run. Not yet evaluated as an arranger against user
  review.
- **Hand and action rules** in `prompts/charting/rules.md` (alternation, wide-movement trills,
  double-tap justification, contact occupancy, Tap/Drag/Hold/Flick semantics).
- **Pure configuration converter** (`agent-tools/pure-configuration/`): reduces a chart
  to one static receiver, useful for producing arrangement-only comparisons.
- Song studies in `charts/` (Silent, Happy ending, Override, Xterfusion) with
  user-approved and user-rejected examples.

## Step 2: music understanding

- **MP3 note-decision analyzer** (`research-tools/music-analysis/`): acoustic heuristic
  onset selection, intensity, climax candidates, review corrections, stems.
  Explicitly a baseline, not learned musical judgment.
- **Local music Q&A MCP** (`agent-tools/Phichain/mcp/music_server.py`): MOSS-Music answers
  questions about clips of the open project's audio.
- Research notes in `research/music-flow-study/` and `research/note-analysis/`.

## Step 3: performance

- **Motion tools** (`inspect_motion`, `preview_passage`, `animate_selection`).
- **Judgment-line study and bank** (`research/judgment-line-study/`): observed
  mechanisms from official charts; not an emotion-to-effect mapping.
- Cadence guidance in `prompts/charting/design.md`, plus the run02/run03 rejections
  recording what does not work (constant noisy motion, sparse punctuation).

## Scope note

`prompts/development/editor-and-mcp.md` and `agent-tools/Phichain/mcp/ROADMAP.md` link to this roadmap. Individual
tools and MCP capabilities are still added only when the user explicitly requests
them. The roadmap sets direction; it does not authorize specific tools.
