# MP3 to note-decision evidence

A local, reviewable first-pass analyzer requested on 2026-11-02. Give it an MP3
(or WAV/OGG); it produces selected note decisions with audio timestamps,
**musical intensity**, reasons and uncertainty, plus section boundaries and
**candidate climax regions**. It also keeps omitted candidates for review.

For an editor-native visualization, use [the live PhiChain importer](#visualize-in-phichain).

This is an acoustic heuristic baseline, not a trained chart-selection model or
verified transcription. It cannot yet infer a perceptual lead voice reliably,
recover every polyphonic note, rate difficulty, or prove that a choice feels good.
The report makes those limits explicit. No editor state, notes, offsets, or
project files are changed. This is an audio-analysis CLI, not an authoring server
or a new MCP tool. There are no model downloads, uploads, network assets, or
browser auto-opening.

## Visualize in PhiChain

`to_phichain.py` converts selected analysis decisions into a diagnostic chart in
an **empty live editor project**, using existing guarded `chart_script` tools.
No native chart JSON is constructed or written offline. This user-requested
visualization is separate from the audio analyzer and requires no new MCP tools.

First create a new project through PhiChain using the analysis output's
`audio.wav`, then open that project in an MCP-enabled editor. Use a dedicated
endpoint if another editor/project is already open. Inspect the track counts:

```sh
python3 research-tools/music-analysis/to_phichain.py research/note-analysis/song/analysis.json --summary
```

Validate without editing (default):

```sh
python3 research-tools/music-analysis/to_phichain.py research/note-analysis/song/analysis.json \
  --endpoint /absolute/path/to/experiment-endpoint.json \
  --project /absolute/path/to/empty-experiment --title "Song - Analysis Layers"
```

Add `--apply --save --receipt research/note-analysis/song-import.json` to validate
again, commit one shared undo entry and save. Omitting `--save` leaves the change
in live memory, subject to ordinary editor autosave. The script checks the exact
project path, canonical PCM SHA-256, duration and revision. It rejects populated
projects, multiple existing lines, stale revisions, and an existing receipt path.
Reimports are rejected to avoid duplicating notes; start with another empty
experiment or deliberately undo the earlier import through the editor.

Default `--group-by layer` assigns one track to each selected note's primary
acoustic layer. Each selected decision appears **exactly once**. Tap/hold types
and audio timestamps are preserved, using the live project's BPM map/offset.
The native 1/10000-beat precision is serialization, not rhythmic quantization.
All notes land at y = −180 on fixed tracks, with line speed 10.35. Within each
track, x moves from left (intensity 0) to right (100), normally ±45 native units.
No motion or finger-travel interpretation is implied by these positions.

`--group-by reason` creates a separate track for each applicable normalized
reason category. Reasons are **multi-label**: a decision is duplicated into each
applicable track, with its original type/time. This inflates combo/object count
and may require simultaneous contacts; it is an inspection view, not a playable
arrangement. The current Override example has four layer tracks / 1,424 objects,
or five reason tracks / 3,990 objects representing the same 1,424 decisions.
Unknown reason text falls into an explicit Other category. More than six tracks
is rejected because native note widths would overlap.

Track names appear in the editor's line list. The existing engine/interface does
not support arbitrary text overlays or per-note reason labels in gameplay.
The receipt maps every created native note ID to its source decision, intensity,
layer and full reasons. The shared judgment line brightens during candidate
climax regions; no additional playable notes mark sections. These fixed tracks
are intentionally diagnostic, not two-finger choreography. Reason-view duplicates
are real chart objects, not fake notes.

## Run

Use Python 3.11+ and ffmpeg/ffprobe. From the repository root, a clean setup is:

```sh
python3.11 -m venv runtime/note-analysis-runtime
runtime/note-analysis-runtime/bin/python -m pip install -r research-tools/music-analysis/requirements.txt
runtime/note-analysis-runtime/bin/python research-tools/music-analysis/analyze.py "/absolute/path/song.mp3" --out research/note-analysis/song
```

In this workspace, the existing `research/music-flow-study/.venv/bin/python` has
the needed dependencies and can be used instead. Generated audio and artifacts
belong under the workspace outside this repository; do not publish source audio.

For a **known** timing grid:

```sh
research/music-flow-study/.venv/bin/python research-tools/music-analysis/analyze.py "/absolute/path/song.mp3" \
  --out research/note-analysis/song-with-grid --bpm 204 --offset 0.348
```

All timestamps use **elapsed FFmpeg-decoded audio seconds**. The offset is the
audio time of beat zero, in seconds; annotations use `(time - offset) * bpm / 60`.
Supplied BPM does not change detection, snap timestamps, or change an editor.
The report plays the exact PCM used for analysis. Other MP3 decoders may differ.
There is no tempo inference or constant-tempo assumption without `--bpm`.

| Argument | Default / contract |
| --- | --- |
| `audio` | Required existing local audio path; first audio stream is used |
| `--out` | Required **new** directory; existing directories are rejected |
| `--threshold` | 50; selection priority cutoff, 0–100; not a difficulty rating |
| `--min-gap` | 0.045 seconds; allowed 0.025–0.5; selected attack separation |
| `--bpm` | Omitted; optional known BPM, 20–400, for beat annotations only |
| `--offset` | 0 seconds; beat-zero audio offset, −1200 to 1200 |
| `--stems` | Optional source/hash-bound stem manifest, described below |
| `--review` | Optional source/analysis-bound correction file |

Inputs require a probeable duration up to 20 minutes and at least 0.1 seconds of
decoded audio. A run uses a temporary output directory; only successful runs
publish the complete report folder. Reruns use new directories to preserve reviews.

## Outputs and review

- `index.html`: offline report with original/hits comparison, speed control,
  seekable song intensity and note timelines, climax intervals, per-note
  intensity/priority/confidence/reasons, omitted-candidate filters, and section
  review. No remote scripts or fonts. Open it yourself in a browser.
- `analysis.json`: versioned source hashes, parameters, score definitions,
  limitations, sections, climax regions, 250 ms timeline, **all** `decisions`,
  and `selected_notes`. Times are seconds; intensity and priority are 0–100;
  confidence is 0–1. Confidence is uncalibrated, not a correctness probability.
- `decisions.csv` and `selected-notes.csv`: one row per candidate/selected attack.
- `audio.wav` and `with-hits.wav`: matching PCM clocks. Hits mark selected heads
  only; their volume follows intensity. Hold tails do not generate hits. This
  audition does not simulate held contact or finger movement.
- `review-template.json`: source/analysis-bound correction template.

The browser can change selection and intensity, and section labels/bounds/climax
flags. Export **Review JSON**, then regenerate with **identical analysis options**:

```sh
research/music-flow-study/.venv/bin/python research-tools/music-analysis/analyze.py "/absolute/path/song.mp3" \
  --out research/note-analysis/song-reviewed --review "/absolute/path/review.json"
```

If the original run used `--bpm`, `--offset`, `--threshold`, `--min-gap` or
`--stems`, repeat those settings. A review is bound to the exact source, settings,
version and detected evidence; mismatches reject rather than attaching edits to
unrelated sequential IDs. Prior corrections survive subsequent report exports.
Unexported browser edits disappear on reload. Saved audio/CSV/JSON do not update
in place; rerun to rebuild them. No report data is sent to an editor.

For time or type corrections, edit the review JSON directly. Each decision patch
has a required `id` and optional `selected`, `intensity`, `time_seconds`,
`end_seconds`, `suggested_type` (`tap`/`hold`) and `comment` fields. Unknown IDs,
unknown fields, duplicate IDs, invalid times, NaN values and reversed holds reject.
Tap ends follow their start. Original detected times remain available, and
overridden values are recorded in `automatic_before_review`.

Optional `sections` replaces the map with contiguous, ordered intervals covering
the complete decoded duration, each containing `start_seconds`, `end_seconds`,
`label` and boolean `climax`. Automatic sections and climax candidates are retained
separately when a reviewed map replaces them. Sections do not imply 4/4, bar
boundaries, fixed phrase lengths or verse/chorus functions.

## What the algorithm actually decides

1. FFmpeg decodes once to 44.1 kHz stereo PCM for review. Features use 22.05 kHz
   mono, a 2048-sample centered FFT and a 128-sample hop (5.8 ms). The approximately
   93 ms FFT window is not a guarantee of 5.8 ms timing accuracy.
2. Median HPSS separates **harmonic/percussive textures**, not instruments.
   Three percussion frequency bands plus harmonic texture provide attack
   evidence. Positive spectral change uses a frequency-local maximum reference
   to suppress small pitch fluctuations. Peaks are located independently of
   chart timing. A conservative dominant pitch ridge also supplies masked tonal
   changes and possible sustained spans; it is not polyphonic transcription.
3. Evidence within a fixed 25 ms window merges into one attack decision. It does
   not turn multiple supporting sources into mandatory doubles. Raw peak and
   estimated leading-edge times are retained. Nominal 50 ms uncertainty is a
   review flag, not a measured error bound; soft attacks can be worse.
4. Priority = 40% attack strength + 25% two-second acoustic-layer energy share +
   20% evidence confidence + 15% coincident-layer support. Repeated activity in a
   layer adds 6 points. A threshold selects candidates; priority-ordered minimum
   gap suppression resolves nearby decisions and records why others were omitted.
   These are explicit heuristics, not learned aesthetic judgments or a density quota.
5. **Intensity** = 40% song-relative energy + 25% local accent + 20% attack
   strength + 15% section intensity. Silence is excluded from energy reference
   estimation. Intensity is musical/acoustic emphasis, **not** difficulty,
   importance, MIDI velocity, or a score comparable across songs.
6. A sufficiently stable tonal ridge can suggest a hold of at least 300 ms;
   a later selected attack in the same layer cuts its tail. These tails and
   their separate sustain confidence require review. No automatic drag/flick,
   finger, lane, chord multiplicity, or occupancy decisions are made.
7. Adjacent two-second timbre/chroma contexts propose texture boundaries.
   Section intensity combines 50% sustained relative loudness, 30% attack activity,
   and 20% spectral fullness. An approximately eight-second smoother, adaptive
   thresholds and hysteresis find sustained acoustic peaks of at least four
   seconds. A region occupying over 70% of the song is not labeled a distinct
   climax. Silence, constant texture or one brief loud hit can yield **no climax**.

Climax is a musical interpretation: loudness/activity can miss a quiet emotional
peak and include a buildup. Automatic region edges and texture boundaries are
approximate and need not coincide. The report deliberately says *candidate*.
This baseline does not implement reliable melodic phrase transcription,
cross-phrase motif matching, or the full listening-led method discussed earlier.

## Optional separated stems

Existing full-length, time-aligned Demucs or manually supplied stems can replace
the default acoustic layers. Use a JSON manifest:

```json
{
  "source_sha256": "SHA-256 of the exact input MP3",
  "time_origin": "decoded_audio_start",
  "stems": {
    "drums": {"path": "drums.wav", "sha256": "SHA-256 of drums.wav"},
    "bass": {"path": "bass.wav", "sha256": "SHA-256 of bass.wav"},
    "vocals": {"path": "vocals.wav", "sha256": "SHA-256 of vocals.wav"},
    "other": {"path": "other.wav", "sha256": "SHA-256 of other.wav"}
  }
}
```

Paths are relative to the manifest or absolute. A nonempty subset is allowed.
Each file hash and source hash must match; durations must agree within 50 ms.
The manifest is a caller assertion of alignment, not proof: check that stems
were made from the same decoded audio without trimming or padding. This tool
does not run separation or download models. Leakage remains possible and
`other` is not synonymous with melody. Tails still use the mix's tonal ridge.

## Verification

```sh
NUMBA_CACHE_DIR=/private/tmp/phichain-music-numba research/music-flow-study/.venv/bin/python \
  -m unittest discover -s research-tools/music-analysis -p 'test_*.py' -v
```

Tests exercise silence, known attack alignment, 74 ms rapid notes, relative
intensity, sustained tones, isolated-hit versus sustained-section climax,
MP3-to-PCM exports, review validation, source binding and HTML escaping.
These establish software behavior on known signals, not human-approved chart quality.

The optional headless UI test needs Playwright and an installed Chromium:

```sh
node research-tools/music-analysis/test_report.cjs /absolute/path/to/result/index.html
```

`PLAYWRIGHT_CHROMIUM_EXECUTABLE` can point to an existing Chromium executable;
the test never installs browsers or opens a visible window.

Primary technical references:
[Librosa onset implementation](https://librosa.org/doc/0.11.0/_modules/librosa/onset.html),
[Librosa HPSS](https://librosa.org/doc/0.11.0/generated/librosa.decompose.hpss.html),
[All-In-One's MP3 decoder alignment note](https://github.com/mir-aidj/all-in-one#concerning-mp3-files).
These support feature extraction and clock discipline; the selection/intensity
weights and climax policy above are this project's provisional design choices.
