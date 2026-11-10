# Song analysis framework: design and evidence

Designed 2026-11-07 at the user's request, because the current analysis
algorithm does not capture the song. This is research under roadmap step 2
(music understanding): why the framework exists, what the runs showed, and how
to calibrate it. The framework itself is
[prompts/analysis/song-analysis.md](../../prompts/analysis/song-analysis.md);
its code is `agent-tools/song-analysis/`. First pilot:
`charts/override/override-analysis-pilot-2026-11-07/`.

## 1. Why the current algorithm misses the song

`research-tools/music-analysis/analyze.py` and its v2–v5 successors are **bottom-up
detectors**: transient → attack → priority score → "note"; texture novelty →
"section"; sustained loudness → "climax". The user rejected every output as
musically wrong, and the official-chart review
(`research/note-analysis/official-reference-review/`) shows why:

| Failure | What the detector does | What the music actually has |
| --- | --- | --- |
| Detectable ≠ chartable | Every sufficiently strong transient is a candidate attack | A chart follows one *lead layer* per passage; most audible sounds are not played |
| No musical function | Sections are 2-second texture contrasts with labels "Section 1..14" | Intro, verse, pre-chorus, chorus, hook, interlude, climax, each with a different charting role |
| No recurrence | Each section is independent | The hook returns three times, the chorus twice; a chart must relate them |
| Climax = loud | Sustained RMS, activity and spectral fullness | Climax is where the arrangement, vocal and harmonic drive peak; a build-up can be louder than the arrival |
| Sustain as attacks | Continuous gestures become streams of taps | Held vocal notes and arcs are one gesture, not many strikes |
| Numbers without meaning | Intensity, priority, confidence are uncalibrated heuristics | The user judges phrases, not scores |

A second failure was in how the local audio model was used. The music MCP
wrapped every question in meta-instructions ("Prior turns (JSON): []", "do not
invent timestamps", "do not claim to hear outside the clip") and asked for
everything at once. The 8B model then produced meta-hallucinations ("no actual
audio data is available", "sourced from 42.23s–94.73s") and invented BPMs. Its
native tasks are captioning, lyrics transcription, structure and QA on one clip
with one plain question; the pilot below uses it that way.

## 2. Provenance of the trust rules

Model rules 1–6 were set before the pilot. Rules 7–11 come from the Override
pilot (`charts/override/override-analysis-pilot-2026-11-07/README.md`).
Measurement rules 12–16 come from the blind runs of 2026-11-07/08 below. The
measurement side is the part of the framework that held up on every song.

## 3. Blind runs

Records so far (none user-reviewed):

| Song | Folder | What it showed |
| --- | --- | --- |
| Xterfusion | `charts/xterfusion/xterfusion-analysis-blind-2026-11-07/` | 128 BPM with a 74–108 s drift; 11 of 16 boundaries within ±2 s of the chart-derived map |
| モニタリング | `charts/other/monitoring/` | 132 BPM; section-opening lines within 0.2 s of the official LRC (checked afterwards, `POST-HOC-CHECK.md`) |
| NightTheater | `charts/other/nighttheater/` | 151 BPM, instrumental; model pair answers DIFFERENT 32/36, recurrence carried by MFCC |
| ハテ | `charts/other/hate/` | 7/8 → 4/4 metric modulation with constant bar length; piecewise grid; model unusable |

The viewer `artifacts/song-analysis-viewer/index.html` shows these records and
nothing else (no reference maps, no old-analyzer lanes).

## 4. Calibration before trusting it on new songs

Run the same protocol on songs with known structure and official charts
(`research/music-flow-study/audio/` has five with allin1 results and official
IN charts in `research/arrangement-training/raw/`). Measure, per song:

- Section-boundary recall and precision at ±2 s against a human-reviewed map.
- Function-label accuracy (intro/verse/pre/chorus/hook/interlude/bridge/outro).
- Pair-comparison accuracy including controls.
- Vocal-presence agreement with Demucs vocal-stem energy per 4 s.
- Lead-layer agreement with the layer the official chart audibly follows, on a
  sample of passages judged by the user.

Until this is done, model claims stay `model-only` or `corroborated`, never
`user-confirmed`, and the user's review remains the gate.
