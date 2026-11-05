> Superseded and rejected by the user: the five-track result was too sensitive across the entire song. The current two-track experiment is [v4](../override-two-track-v4/README.md). The material below is historical, not an accepted result.

# Override — full independent-voice result

Current state: full-song analysis, native project, and labeled native preview
completed on 2026-11-02. This supersedes the earlier 12-second probe as the
current deliverable. The user requested the best concrete output available now;
this is an experimental music-evidence visualization, not an accepted playable
arrangement or verified transcription.

## Open the result

- `override-voices-full.mp4`: entire 2:18.53 song, five labeled tracks, original
  music audio. The final video lasts approximately 2:18.57 due to the 30 fps frame
  boundary. Original music replaces the game hit sounds so the sources remain
  audible. Text annotations are the only visual addition to native rendering.
- `project/`: saved native PhiChain project, left open and paused at 48 seconds.
- `analysis.json`: complete event times, source IDs, pitches, estimated durations,
  musical-role hypotheses, intensity components and reasons.
- `aligned-stems/`: four full-length aligned source estimates for independent
  listening. These are model estimates, not original multitrack recordings.
- `vocals-transcription.mid`, `bass-transcription.mid`, `other-transcription.mid`:
  unpruned pretrained-model MIDI outputs, before voice-selection heuristics.

## Five tracks, left to right

| Track | Interpretation | Events |
| --- | --- | ---: |
| Vocal | Dominant vocal pitch-line estimate | 544 |
| Instrumental voice | Salient smooth upper pitched line within the other stem | 906 |
| Harmony | Remaining simultaneous pitch groups within the other stem | 518 |
| Bass | Dominant bass pitch-line estimate | 469 |
| Drums | Independent percussive attacks within the drum stem | 919 |

Total: **3,356 events**, including **506 Hold-shaped duration displays**. These
counts describe analysis evidence, not a recommended gameplay density. No global
events-per-second cap or cross-source onset suppression is applied.

Notes move left/right slightly within each track according to pitch (the harmony
track uses the group's mean pitch); drums stay centered. This is a pitch cue,
not finger arrangement or an intensity mapping. Holds show estimated sustained
audio evidence, not a recommendation to require held screen contact.

Different sources retain their own onset times. Of 544 vocal events, 169 lie more
than 30 ms from the nearest drum event. This describes detector outputs, not
verified syncopation counts. Their identities are not merged or snapped together.

## Analysis method and uncertainty

1. Reuse the existing HTDemucs vocals, drums, bass and other source estimates.
   Their sum matches the canonical original mix after removing 1,105 samples
   (25.0567 ms at 44.1 kHz) of decoder offset, consistently across five windows.
   Original source files are preserved. Aligned WAVs match the canonical length.
2. Run the official Spotify Basic Pitch 0.4.0 pretrained ICASSP 2022 ONNX model
   independently on vocals, bass and other. Parameters are onset threshold 0.5,
   frame threshold 0.3, minimum-note-length parameter 75 ms, with the model's
   melodia postprocessing enabled. Frequency limits are recorded in
   `transcription-manifest.json`. Raw outputs contain 614 vocal, 487 bass and
   1,958 other pitch notes and are retained alongside model arrays and MIDI.
3. Group within-source near-simultaneous pitched starts within 25 ms. A dynamic
   path chooses one salient, smoothly connected note per group, using model
   activation and pitch continuity. Instrumental voice has an explicit mild
   upper-pitch preference; bass has a mild lower-pitch preference. The path resets
   across gaps of at least 650 ms. This is a transparent heuristic, **not a model
   trained to distinguish main melody and accompaniment**.
4. Remaining other-stem notes become chord/pitch-group evidence in the harmony
   track. The instrumental upper voice is described as a lead candidate when no
   vocal estimate is nearby and as a countervoice candidate otherwise. These
   role hypotheses can be wrong: a top chord tone can be mistaken for melody,
   and the other stem can contain multiple foreground and accompaniment sources.
5. Refine each pitched onset toward a nearby attack in its own source only when
   within 25 ms. Otherwise preserve its transcribed start. Original temporal
   midpoint bounds prevent distinct same-track attacks from collapsing onto one
   peak; 31 events needed this guard. Source-local drum attacks are separate.

Secondary vocal/bass simultaneous hypotheses are omitted from the dominant-line
display, but preserved in raw transcriptions. Source leakage, octave mistakes,
missed short notes, erroneous note boundaries and wrong role assignments remain
possible. Confidence fields are null; raw model activation is retained and is
not advertised as calibrated event correctness. No listening review has been
performed by a human for this result.

## Intensity and climax

Every event has a 0–100 intensity estimate. Pitched events combine within-source
relative energy (50%), attack strength (30%) and local accent (20%). Drum events
combine relative energy (60%) and attack strength (40%). Components are recorded
in JSON. These are heuristic musical-emphasis proxies within each source, not
trained intensity labels, cross-source calibrated loudness, confidence or
gameplay difficulty. Spatial position in the native display does not encode it.

Climax candidates remain **38.75–58.50 s** and **85.25–128.25 s**, carried forward
from the earlier source-hash-matched whole-mix energy/texture heuristic. They
were not newly validated by this transcription. The shared line brightens and
the video explicitly labels them as acoustic climax candidates. Do not treat
these intervals as confirmed musical-section boundaries.

## Native authoring and verification

The new project was created and opened with the native editor's existing
`create_project` and `open_project` lifecycle tools. All chart content was added
through a guarded `chart_script` dry run and one atomic commit, then saved using
the live bridge. No offline chart was authored or substituted. Previous Override
projects remain unchanged. The editor uses the unchanged default 120 BPM as an
audio-time editing clock; this is not a musical tempo estimate or grid snap.

Verification covers all 3,356 native objects, five carrier lines, note types,
source-to-line mappings, positions, head times and displayed sustain ends. Maximum
time conversion error is 0.050 ms; this is serialization accuracy, not acoustic
onset accuracy. Structural diagnosis reports no errors. JSON checks confirm
unique IDs, strictly increasing times within each track, valid durations and
intensities. Native renders preserve the same captured revision.

The whole song is rendered in twelve guarded passages, joined without changing
chart timing. Static track labels and heuristic climax labels are added for
readability. Native images at representative passages were inspected for
separated tracks, sustained-note shapes and readable labels. User review of the
musical choices remains outstanding.

## Reproduction and records

- `transcribe_full.py`: source alignment and cached pretrained inference.
- `build_full_analysis.py`: full voice organization, local timing and intensity.
- `author.js`, `import_full.py`: new-empty-project-only native authoring.
- `render_full.py`, `make_labels.py`: full native video and text overlays.
- `transcription-manifest.json`: pretrained model/source hashes and parameters.
- `analysis-verification.json`, `verification.json`, `diagnosis.json`: data and
  native correspondence checks.
- `dry-run.json`, `commit.json`, `save.json`: native authoring receipts.
- `native-parts/`, `render-verification.json`: revision-bound rendering evidence.

Analysis uses `research/music-flow-study/.venv/bin/python`. Newly installed local
packages: basic-pitch 0.4.0, onnxruntime 1.31.1, pretty_midi 0.2.11.post0,
mir_eval 0.8.2, importlib_resources 7.1.0 and resampy 0.4.3; mido already existed.
No editor/MCP source code or arrangement-training corpus was changed by this
task. Do not rerun the importer into the populated project. Read fresh native
state and preserve any subsequent user edits.

References: [Basic Pitch](https://github.com/spotify/basic-pitch),
[Demucs](https://github.com/facebookresearch/demucs).
