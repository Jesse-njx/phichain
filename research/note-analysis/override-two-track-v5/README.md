# Override — recurring primary drum pulse and continuous melody

Current state: v5, 2026-11-02. This responds to the user's v4 feedback:
"significantly better" but still not usable, the drum pattern should be constant,
and many audible melody notes are missing. This remains an experimental output;
the user has not accepted v5 and no accuracy claim is established.

## Review

- `project/`: new saved native PhiChain project. It was opened in its own GUI
  window during authoring; the endpoint was no longer present at the final check,
  so the window is not claimed to remain open.
- `override-two-track-full.mp4`: complete native preview with original audio.
- `analysis.json`: timestamps, durations, musical-emphasis intensity, sources,
  onset/pitch-boundary evidence and uncertainty.
- `candidate-audit.json`: accepted and rejected events; no raw source files altered.
- `analysis-verification.json`: behavioral controls and diagnostic comparisons.

There are exactly two lines: **primary drum pulse** (459 events) and **main
melody estimate** (846 events: 525 vocal-source, 321 other-source). There are 117
Hold-shaped displays of estimated sustain, not authored gameplay Holds. The
prior v4 project is preserved. The counts describe hypotheses, not accuracy.

## Drum correction

V4 treated every sufficiently strong source-flux peak as part of the same drum
role. Its primary on-beat attacks were mixed with off-beat percussion and other
transients, causing the changing density the user rejected.

The corrected role is the **recurring primary drum pulse**, explicitly not all
percussion. Global weighted phase coherence finds approximately 204.000033 BPM,
with a primary period of 294.117599 ms and phase 25.186715 ms relative to canonical
PCM. This is a source-attack timing estimate, not a recommendation to change the
audio offset. The half-beat recurrence score is 0.95857. A coarse search followed
by local refinement avoids unrelated local optima in tempo fitting. The stronger
of the two half-beat phases identifies the primary pulse. `probe_pulse.py` also
checks primary versus intervening-phase support across 16-second windows: the
primary attack remains strong, while the intervening phase changes by section.

Every displayed drum head uses the same period and phase, and additionally has
a local source attack within approximately 10 ms. Twelve proposed grid locations
have insufficient local evidence and are withheld, not automatically called true
rests: 0.025, 21.202, 38.260, 38.849, 40.025, 87.672, 87.966, 137.084, 137.378,
137.672, 137.966 and 138.260 seconds. They are listed in JSON for review. Intro/outro
and internal gaps therefore remain; v5 does not claim literally uninterrupted
drums. It does not invent hits just to complete a grid. Auxiliary percussion
is intentionally outside this displayed role and remains available in v4's
raw evidence. Drum intensity can still vary even though its primary timing is
periodic. The user identified constancy of rhythm, not necessarily equal volume.

## Melody correction

V4's high onset threshold and whole-event dominance tests discarded weak attacks
and legato changes. The new decoder follows a **monophonic pitch path across
frames**, with an explicit silence state. Temporal transition costs favor
continuity but permit stable pitch changes without a strong onset. Learned onset
evidence can reduce transition cost. Separate same-pitch onset peaks represent
rearticulation; unrelated pitch/mixture attacks do not split a sustained lead.

The pretrained model remains the cached Basic Pitch output, not a newly trained
model. Source activity and mix gates remain. Vocal and other pitch-activation
floors are 0.34 and 0.36; notes require at least four model frames and mean
activation at least 0.015 above the corresponding floor. The song-specific pitch
range is MIDI 43–84. This range is an internal search constraint, not a semantic
frequency-band lane. Short unstable states are not emitted. Exact implementation
is in `pitch_path.py` and `analyze.py`.

Vocal phrase occupancy is now derived from the continuous voiced path. One other
source path supplies instrumental foreground outside vocal phrases. Vocal
priority remains a heuristic; this is not a trained role classifier. True
instrumental countermelodies during vocals may be omitted. Pitch errors,
vibrato-related segmentation, source leakage and chord-tone role errors remain
possible. Raising melody count does not establish improved recall or precision.

396 of v4's 402 melody events have a v5 event of the same pitch with a start
within 60 ms. This is a retention diagnostic, not ground truth. There are 165
accepted melody boundaries whose local learned onset is below v4's 0.65 threshold.
484 melody heads lie more than 30 ms from the closest displayed primary drum
head: the melody is neither quantized nor forced to follow the primary drum.

## Validation

Behavioral controls verify:

- A sustained pitch change without a new onset survives.
- An unrelated weaker pitch's onset does not split a sustained lead.
- A real same-pitch rearticulation is retained.
- Zero pitch evidence and inactive-source frames produce no notes.
- A one-frame competing pitch glitch produces no extra note.

All drum intervals are integer multiples of the fitted primary period, and each
accepted pulse has local attack support. JSON invariants and all 1,305 native
objects' tracks, types, positions, head times and sustain ends are checked.
Maximum native conversion error is 0.042 ms; this is not acoustic timing accuracy.
The native import uses a fresh project, guarded dry-run, atomic commit and save.
Full-song rendering uses twelve snapshots of the same saved revision. Only
labels are overlaid; original canonical music replaces game hit sounds.

The default 120 BPM editing clock encodes audio seconds. It is separate from the
estimated 204 BPM musical pulse. Source alignment and audio hashes are inherited
from v3. Intensity is still a within-source acoustic emphasis proxy (0–100), not
difficulty or calibrated confidence. Climax candidates 38.75–58.50 and
85.25–128.25 seconds are carried forward unchanged and explicitly unvalidated.
No human-label benchmark or listening review establishes transcription accuracy.

## Reproduction

Use `research/music-flow-study/.venv/bin/python analyze.py`, then
`verify_analysis.py`. Cached aligned stems and model arrays are read from v3;
the v4 feature routine and drum evidence supply the acoustic input and initial
recurrence observations. `provenance.json` records these dependencies.
`create_native.py`, `import_full.py` and `render_full.py` create a new native GUI
project, import through guarded MCP authoring, and render the full song. Do not
rerun creation/import over a populated project. Preserve subsequent user edits.
