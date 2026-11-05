# Override analysis visualization

## Current state — rejected diagnostic experiment

User feedback on 2026-11-02: this analysis/selection is musically terrible. Do
not treat the saved chart or its software verification as an accepted selection
model. The user briefly added an unnamed candidate-time line, then reported it
may not have been saved and explicitly asked to skip it. The saved chart inspected
in this review contains only the original four analysis lines. No recovery,
reconstruction, or inference about the missing line is authorized or performed.

The experiment and root MCP endpoints were absent during the review; the editor
was not restarted. The latest task is a read-only study of already downloaded
official charts, documented in `../official-reference-review/README.md`. No saved
notes, timing, audio or editor state were changed in that task. The original
import details below describe the rejected baseline, not a new accepted version.

## Saved baseline details

Created through the native project UI on 2026-11-02, then populated via the live
MCP bridge using `tools/music-analysis/to_phichain.py`. This is a visualization of
automatic analysis decisions, not a two-finger arrangement or an approved chart.

- Title: `Override - Analysis Layers`.
- 1,424 notes: 1,418 taps and 6 holds; 4 independent lines, 24 events.
- Left to right: Low percussion (265), Mid percussion (188), High percussion
  (150), Harmonic texture (821). These are acoustic textures, not instrument identities.
- Native lane centers: −450, −150, +150, +450. Judgment row y = −180;
  rotation 0; native line speed 10.35. Stationary tracks are intentional for
  diagnostic inspection. There is no finger assignment.
- Each note's local x maps intensity 0–100 to −45…+45. The mapping is musical
  emphasis, not difficulty. Tap/hold types and their timings remain as analyzed.
- One shared visible horizontal line, with other carriers invisible. Brightness
  rises from 65 to 230 during automatic climax candidates 38.75–58.50 and
  85.25–128.25 audio seconds. No extra notes or combo mark these regions.
- Track labels live in the editor line list. Arbitrary gameplay text and note
  reason tooltips are not supported by the existing interface.
- Saved revision: `e5f230d4ae13fcfa`; session
  `dcba6881-d460-4465-bcd5-4a4b9324d31d` (historical identifiers; reread before editing).
- Editor left paused at 48.0 audio seconds with the first line selected.

## Source and timing

Input analysis: `../override/analysis.json`. Project music is a byte-identical
copy of its FFmpeg-decoded `audio.wav`, duration 138.533356009 seconds and SHA-256
`8f3cedc2e31a276fd2526382b9ce904e2321c2308b276c14f9ae0529a7894f36`.
Original MP3 hash:
`7284ea9019ef8ea3a90f7c92c3394aa4447ffc9cd29bc8b5df2b6c6c30407e29`.

The empty project's 120 BPM / zero offset were preserved as an editing clock,
not inferred musical tempo. Audio seconds map to twice that many editor beats.
No snapping to the song's rhythmic grid occurred. Native fraction serialization
has 1/10000-beat resolution; all 1,424 heads and six tails match the analysis
within 0.000020 seconds.

## Reason categories

The same selected decisions contain five overlapping reason categories:
attack evidence 1,424; coincident-layer evidence 1,078; repeated layer activity
1,227; local prominence 255; sustain/hold evidence 6. A separate `--group-by reason`
import would create 5 tracks and 3,990 objects, duplicating decisions across their
reasons. That mode is implemented/tested but has not replaced this four-track view.

## Verification and evidence

- `../override-phichain-dry-run.json`: native validation with zero undo changes.
- `../override-phichain-import.json`: one committed agent undo entry, save receipt,
  created IDs, per-native-note decision mapping and full source reason/intensity data.
- `../override-phichain-verification.json`: full live timestamp/type comparison,
  six native rendered samples over 48.0–49.8 seconds, unchanged revision and
  blue-note pixel component bounds (maximum width 113 px at 960×540). No rendered
  report was opened for the user. This is limited geometry verification, not
  human aesthetic or playability review.
- 18 analysis/importer tests passed, including source/project safeguards,
  multi-label reason mapping, offset/variable-BPM conversion and stale-revision rejection.
- Existing Xterfusion and other Override chart projects were not imported into or replaced.

The live endpoint for this experiment is `../override-phichain-endpoint.json`.
Do not expose endpoint credentials. Read fresh live state before any changes.
The converter refuses populated projects, so rerunning it cannot silently
duplicate this import or erase later manual edits.
