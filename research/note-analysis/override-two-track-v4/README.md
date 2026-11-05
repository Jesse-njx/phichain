> User feedback: significantly better than v3, but still not usable; drum density varies despite a steady primary pattern, and melody notes are missing. The next experiment is [v5](../override-two-track-v5/README.md). V4 is preserved as a comparison.

# Override — conservative drums and main melody

Current state (2026-11-02): a full-length two-track revision responding to the
user's rejection of v3 across the entire song. **This is an unvalidated experiment,
not a verified transcription or a demonstrated solution to false positives.**
No user-supplied bad timestamp is required; feedback applies globally.

## Output

- `override-two-track-full.mp4`: full native PhiChain preview, original music,
  drums on the left and one main-melody estimate on the right.
- `project/`: saved native project, authored through the native headless runtime.
- `analysis.json`: accepted events with independent timestamps, estimated ends,
  source, pitch, emphasis intensity (0–100), evidence and reasons.
- `candidate-audit.json`: 1,846 candidates from the revised decoder/detector,
  including accepted flags and explicit rejection reasons. Earlier raw model
  outputs remain in `../override-voices-v3/`; this audit does not include every
  possible subthreshold raw model peak.

There are 791 drum attacks and 402 melody events (322 from the vocal source,
80 from the other source); 88 events have Hold-shaped sustain displays. Neither
count nor the reduction from v3 is an accuracy metric. Removing separate bass
and harmony tracks also reduces the count without improving transcription.
Holds show evidence duration, not gameplay recommendations. No automatic second
melody track is created. Bass/harmony sources are not separate displayed roles.

## What changed

V3 selected one note from every onset group and additionally filled residual
pitch activity via Basic Pitch's melodia step. Its five stems/estimated parts
were incorrectly presented as five useful musical tracks. The user explicitly
wants approximately two functional tracks and reports false notes globally.

The revised melody path decodes the existing pretrained arrays with **direct
learned onsets only**: onset threshold 0.65, frame threshold 0.4, minimum length
7 model frames and gap tolerance 3 frames. Inferred onsets and residual-pitch
filling are disabled. An event additionally needs sustained activation, pitch
dominance, source activity, and a non-silent mixture. It is valid to output no
note; the path no longer must select a pitch from every group.

Vocal phrases own the single melody role across syllable gaps. An instrumental
candidate can take over outside those phrases only with a clear pitch margin
against competing pitches. Ambiguous chord tones and isolated short detections
are rejected. This can omit real instrumental melody: vocal priority and the
instrumental dominance rules are explicit heuristics, not a trained foreground
melody classifier. Sources can leak, and model onsets can still be false.

Drum attacks now use positive **linear-amplitude** spectral change, local
contrast, prominence, and source/mix activity checks. Weak frequency bins are
no longer logarithmically amplified before attack detection. Spectra are internal
signal features; they do not define the two displayed musical roles. No beat-grid
filling, cross-track snapping, chart-density target, or intentional arrangement
rests are applied. Abstention means insufficient evidence, not gameplay omission.

The source alignment is unchanged: the existing stem sum was 1,105 samples later
than canonical PCM at 44.1 kHz; the cached aligned stems already correct this.
Pitched timestamps now stay at learned onset times rather than being moved to
nearby generic source-flux peaks. Drums retain subframe peak interpolation.
The two streams keep independent timestamps; 77 melody events are more than
30 ms from the nearest displayed drum event. This is not a syncopation accuracy
score. A default 120 BPM editor clock encodes seconds without musical quantizing.

Intensity combines source-relative energy and attack strength; it is a musical
emphasis proxy, not difficulty, event confidence, or a calibrated cross-source
measure. Confidence remains null. Climax intervals (38.75–58.50 and 85.25–128.25 s)
are explicitly labeled old acoustic candidates carried forward, not revalidated
musical-section labels.

## Validation and limits

`analysis-verification.json` records synthetic controls: digital silence yields
zero attacks, a stationary tone yields no interior attacks, three decaying noise
hits retain their timing after a 40 dB gain reduction, and a silent mixture
rejects nonzero residual source events. These controls test specific failure
modes, not precision or recall on Override. Full accepted data has valid times,
unique IDs and exactly two tracks. Each accepted pitched event has a direct
learned onset at or above the configured threshold.

`verification.json` checks every saved native note's track, type, coordinates,
head and sustain end against JSON. The maximum conversion error is 0.044 ms;
this is serialization error, not acoustic accuracy. All twelve native render
passages share the saved revision. Video labels are the only visual overlay;
the original music replaces game hit sounds. Representative native frames were
inspected for geometry and labeling. No human listening/transcription review or
labeled false-positive benchmark has established that this revision is accurate.

A next accuracy claim requires matched audible-onset and role labels, including
negative examples. Original game charts offer positive timing references but
uncharted times cannot automatically be treated as non-musical negatives.

## Reproduction

Run `analyze.py` and `verify_analysis.py` with
the repository-relative interpreter
`research/music-flow-study/.venv/bin/python`. They use the preserved
v3 aligned stems and cached Basic Pitch ONNX outputs. `provenance.json` hashes
those inputs. Parameter values are recorded in `analysis.json`.

`create_native.py` creates a NEW dedicated native headless editor and project.
`import_full.py` requires that empty native project, performs a guarded dry-run
and atomic commit, verifies all objects and saves. `render_full.py` renders the
full saved revision via native preview tools and labels/joins the passages.
Never rerun creation/import over this populated project; read fresh state and
preserve user edits. Previous projects and raw training charts are unchanged.
