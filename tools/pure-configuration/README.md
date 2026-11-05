# Pure configuration CLI

Convert an official-v3 Phigros chart into **exactly one static judgment line containing every note**. This automates the user-approved Poseidon AT conversion. Python 3.9+ standard library only: no LLM, agent, editor, MCP host, GPU, network, installation or build step.

```sh
# Preserve the audio, illustration, metadata and other members of an existing PEZ.
python3 tools/pure-configuration/convert.py song.pez song-pure.pez

# Chart JSON only; default output is AT-pure.json beside the source.
python3 tools/pure-configuration/convert.py AT.json

# JSON → playable PEZ. Auto-finds sibling music/song .ogg/.mp3/.wav/.flac.
# Auto-finds illustration/cover .png/.jpg/.jpeg, or supplies a plain PNG.
python3 tools/pure-configuration/convert.py AT.json song-pure.pez --name "Song AT — Pure Configuration"

# Explicit assets when they are elsewhere or discovery is ambiguous.
python3 tools/pure-configuration/convert.py AT.json song-pure.pez --music song.ogg --illustration cover.jpg
```

Run from the repository root, or use the script's absolute path from anywhere. Output directories must already exist. Existing outputs require `--force`; even with that flag the source and supplied/discovered audio/cover assets cannot be overwritten. Input files remain unchanged. Output publication is atomic and failed conversions leave no partial output.

## What it does

1. Evaluate each source note's horizontal judgment position at its head time, including line translation and rotation: `18 × (line_x − 0.5) + note_x × cos(angle)` in official coordinates.
2. Put every note above one horizontal line at screen position `(0.5, 0.25)`, with full line opacity and constant scroll speed **2.2** (override with `--speed`). This equals native PhiChain speed 9.9 used for Poseidon.
3. Preserve all note types, head timestamps, Hold durations, simultaneous stacks, rests and the chart's audio offset. Normalize differing per-line BPM clocks to the first line's BPM without changing time in seconds. No quantization or decimal rounding is applied.
4. Recalculate floor positions. Use speed 1 for Tap/Drag/Flick and the absolute scroll speed for Holds, as required by official-v3 semantics.
5. Remove line performance, decorative carriers, variable scroll and below-side approach. Vertical separation and continuous Hold-contact travel are flattened; Holds remain at their head x. Tap+Flick overlaps and repeated Drag checkpoints are intentionally retained.

This is a stateless file conversion, not a second authoring session or chart server. The output is deterministic for the same inputs/options. Rerunning on an already flattened chart is idempotent with the same scroll speed.

## Inputs and limits

- Supports **official `formatVersion: 3` JSON**, including a PEZ containing exactly one chart JSON. RPE, PhiChain-native JSON, official v1, fake-note extensions and ambiguous multi-chart packages are rejected, not silently approximated.
- PEZ files are read in memory, never extracted. The chart member retains its original name/path; every other member's **uncompressed bytes**, including metadata/credits and audio, are retained. ZIP timestamps/compression are normalized. The existing package must already have valid asset/metadata references; this tool does not repair them.
- New JSON → PEZ packages use a supplied `--name` or the input filename stem. Bare chart JSON does not contain song credits, so generated metadata uses a generic adaptation credit and an unrated difficulty of 0. For existing credits/metadata, prefer PEZ → PEZ. `--name`, `--music` and `--illustration` apply only to JSON → PEZ.
- Source move/rotation events are linear official events. The latest-start event wins, including at shared boundaries; its end value persists through gaps. Before the first event, the default is centered x and zero rotation. Missing channels use those defaults. Source opacity and scroll performance are intentionally discarded.
- A few official charts contain constant events with reversed timestamps. Because their value does not depend on interpolation, these become a step at the stated start. Reversed nonconstant transitions are rejected.
- The tool preserves horizontal placement even if a source head is offscreen. It does not clamp, deduplicate, simplify difficulty or reinterpret musical/fingering intent. Flattening distinct vertical contacts may affect execution. Automatic correctness checks do not certify human playability.
- Audio and illustration bytes are copied without transcoding or decoding. Their file extensions must match the documented formats; supplied files must already be valid media.
- Preview rendering is optional and separate; conversion does not launch or open anything.

## Verification

```sh
python3 -m unittest discover -s tools/pure-configuration -p 'test_*.py'
```

Synthetic tests cover moving/rotating judgments, mixed BPM clocks, below-side notes, exact timing and stacks, Hold speed/floor semantics, event boundaries, unsupported inputs, deterministic packaging, metadata/asset preservation, asset ambiguity and overwrite protection. User charts and audio are kept under ignored `local/` paths and are not test fixtures.
