# Override — timing v2 visualization

Latest feedback: the user closed the window and identified frequency-band
grouping as inadequate for separating foreground melody/vocals and accompaniment.
Do not treat these three frequency tracks as accepted musical layers. The next
source-aware diagnostic is documented in `../override-voices-v3/README.md`.

Current state: imported, verified and saved on 2026-11-02. This is the current
timing-analysis demonstration requested after the two chart-supervised timing
experiments. It is not an accepted playable chart or a complete music analysis.
The previous rejected four-line visualization remains untouched.

Open `project/` in PhiChain. The dedicated live editor is left paused at 48 audio
seconds. Its endpoint is `endpoint.json`; do not print or share its credentials.
Read fresh context before any further edit, and preserve subsequent user changes.

## Display

The complete 138.533-second audio contains **1,108 candidate events**, represented
as Taps for inspection. Left-to-right tracks are:

| Track | Frequency evidence | Candidates |
| --- | --- | ---: |
| Left | Low-band positive spectral change, <250 Hz | 215 |
| Center | Mid-band positive spectral change, 250–2500 Hz | 193 |
| Right | High-band positive spectral change, >2500 Hz | 700 |

Track assignment uses the largest mean positive log-mel change across the bands
at the original detected peak. Bands are approximate mel-center groups, not
brick-wall filters. They are not instrument identification or source separation.
Every event appears on exactly one track; simultaneous sources can be merged by
the full-mix detector.

Within each track, a note farther right has greater relative attack strength.
This scalar is the event's flux divided by the song's 95th-percentile candidate
flux, clipped to 0–100. It is an acoustic proxy, not validated musical emphasis,
selection importance, confidence or gameplay difficulty. JSON musical_intensity
and confidence fields are explicitly null. Tap is a display object, not a
classification that the sound must be charted as Tap.

## What is being shown

This uses the validation-winning **spectral-flux baseline with quadratic peak
interpolation**, not either rejected neural model. It inherits the timing
experiment's 8-candidates/second whole-song cap and 40 ms peak spacing. The cap
is an experiment setting, not an agent's musical selection decision or a final
discovery policy. All retained candidates are shown; no phrase-level omission or
intentional blank-section logic is applied.

The largest interpolation correction is 4.974 ms. No global song-specific timing
correction or beat snapping is applied. The live project's default 120 BPM is
only an editing clock for exact audio-time placement, not a musical tempo claim.
Three fixed vertical tracks use normal approach and one visible judgment line.
No Hold, sustain interpretation, new climax estimate or decorative motion is
included in this timing experiment.

## Source and safety

The empty native project was created through PhiChain's UI using the same canonical
PCM audio as the previous experiment. Audio SHA-256 and duration are checked
against `analysis.json`. No offline chart file was synthesized. All notes and
line events were added through one dry-run-validated live `chart_script` commit
with current project/session/revision guards, then saved through the live bridge.

The initial verification stopped after commit because it compared native float32
x positions to decimal source positions with exact equality. A fresh read
confirmed the complete import. Verification resumed without any second import,
using a 0.00001 native-coordinate tolerance; all checks passed. No duplicates
were added.

Full verification confirms 1,108 Taps, three lines, correct event-to-track mapping
and positions, unchanged BPM/offset, and maximum audio-time serialization error
of 0.025 ms. This is conversion accuracy, not acoustic timing accuracy. Native
structural diagnosis passed. A 12-second native render at 960×540 includes audio;
four sampled frames were visually checked for separated tracks, ordinary vertical
approach and readable note size. The render reports no live revision change.
User listening review remains outstanding.

## Files

- `project/`: native saved project, including its audio.
- `analysis.json`: event IDs, original and corrected seconds, correction amount,
  frequency evidence, attack strength and explicit limitations.
- `analyze_override.py`: reproducible audio analysis for this demonstration.
- `author.js`, `import_live.py`: empty-project-only live visualization importer.
- `dry-run.json`, `commit.json`, `save.json`, `verification.json`: live receipts.
- `native-preview.json`: guarded native render receipt.
- `override-timing-v2-48-60.mp4`: native 48–60 second demonstration with audio.

To reproduce analysis without touching the live chart:

```sh
research/music-flow-study/.venv/bin/python research/note-analysis/override-timing-v2/analyze_override.py
```

Do not rerun the importer into this populated project. Its default empty-project
guard will reject that operation. The `--verify-only` recovery option checks the
recorded commit revision and does not create chart objects.
