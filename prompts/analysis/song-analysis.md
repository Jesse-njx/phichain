# Song analysis (macro)

Produce a song description that is musically structured, time-aligned to the
grid, and honest about what is measured, what is heard by a model, and what the
user has confirmed. Code lives in `agent-tools/song-analysis/`. Song-specific results
live in the song's own workspace folder. Nothing here edits a chart.

## 1. The Song Analysis Record

The framework's output is a **Song Analysis Record (SAR, XR0)**: one JSON
document per song, hierarchical, where every claim carries its evidence source
and status. A chart agent reads the SAR; it never reads raw detector output
directly. Item codes such as `MG1` are defined in
[terminology.md](../shared/terminology.md); the SAR holds the
song- and section-scale items of its music-understanding tables, the Phrase
Rhythm Record ([phrase-rhythm.md](phrase-rhythm.md)) the rest. Existing
records keep the legacy keys `L0_identity_grid` … `L5_energy`; the registry's
section 8 maps them.

| Aspect and items | Content | Primary evidence | Secondary |
| --- | --- | --- | --- |
| MG Grid: MG0 audio identity, MG1 tempo, MG2 beat zero, MG3 meter, MG4 tempo segments, MG5 key | Audio hash, duration, BPM, beat-zero offset, meter, piecewise grid where tempo or meter changes, key (optional) | Measurement (pulse fit, onset alignment) or user | Model for key only; model BPM is never used |
| MF Form: MF0 sections, MF1 recurrence groups, MF2 pickups | Ordered sections `[start,end)` in beats, **function label**, phrase length, pickup/anacrusis flag, recurrence group (A, A', B...) | Model listening + chroma self-similarity + stem energy | allin1 labels as a third vote |
| ML Layers: ML0 inventory, ML1 entrances and exits, ML2 vocal ranges | Per section: layers present (lead vocal, lead synth, guitar, bass, drums, pads, FX), role (foreground/background), entrances and exits with times | Model listening (entrances) + stem energy (presence) | |
| ML3 lead layer, ML4 lyric lines | Per section: which layer a player should follow, its rhythmic character (sustained, steady eighths, sixteenth runs, syncopated, call-and-response), vocal phrase boundaries, hook motif occurrences, lyric lines | Model listening (lead, lyrics) + pitch tracking on the named stem | |
| MR Rhythm: MR0 drum pattern class, MR3 fills and breaks | Drum pattern class (four-on-the-floor, half-time, breakbeat, absent), subdivision, fills and breaks with times, pattern changes | Model listening + drum-stem pulse analysis | |
| ME Energy: ME0 energy per bin, ME1 tension, ME2 pairwise intensity, ME3 climax candidates, ME4 drops, breaks and build-ups | Per 4-beat bin: energy 1–5, tension (building/steady/releasing), drops, breaks, build-ups; climax spans **with a musical reason** | Model ratings reconciled with measured energy | |
| MH Hits (derived): MH4 density envelope, MH6 background driver, plus sustain candidates (MR6) and section relations (MF1) | Derived only: which layer each section follows, density envelope, sustain candidates, section relations to preserve, background-line driver layer | Computed from MF, ML, MR and ME plus reference charts; never asked of the model | |

Every claim is an object:

```json
{"value": "chorus", "source": "model", "status": "corroborated",
 "evidence": ["calls/A1_W1.json", "calls/B3_chorus1.json", "ssm:136-200~304-368:0.88"],
 "confidence": 0.8, "note": "two overview windows and the section clip agree"}
```

`source` ∈ {measurement, model, reference, user}. `status` ∈ {corroborated,
model-only, measurement-only, contradicted, user-confirmed}. A `contradicted`
claim is kept visible with both sides, never silently resolved. `user` beats
everything; a user correction is recorded as `user-confirmed` and reused.

## 2. Evidence sources and trust rules

| Source | Trust for | Do not trust for |
| --- | --- | --- |
| Measurement (beat grid, RMS, chroma self-similarity, Demucs stem energy, pulse fit) | Timing, tempo, where energy and texture change, which passages repeat | Musical function, which layer leads, whether a passage is a pickup |
| Local audio-language model (MOSS-Music-8B-Instruct, 4-bit MLX) | Function labels, instrumentation and entrances, vocal presence, lyrics, same/variation/different between two clips, lead-layer identity, drum-pattern class, relative energy | BPM, meter, key, exact timestamps (its native resolution is the 2-second time marker), anything about audio it was not given |
| Reference charts (327 official IN charts, Arcaea same-song AFF) | How a given function is typically charted, density ranges per function | The specific song's structure |
| User | Everything; the only acceptance gate | — |

Model rules.

1. **Native prompt, one question per call.** Plain chat template, no
   meta-wrapper, no injected history, no negative instructions about
   hallucination. Temperature 0. Each question targets one SAR aspect.
2. **Clips aligned to the measured grid.** Section questions use clips cut at
   the candidate section boundaries in beats. Clip-relative times are converted
   to absolute seconds and then to beats with the grid (MG1, MG2); the model never
   sees beats.
3. **Resolution cap.** A model timestamp is accepted to ±2 s and is only
   promoted to a beat when a measured boundary (energy step, stem entrance,
   self-similarity edge) lies within that window.
4. **Stability.** Any boundary claim must be reproduced by a second call on a
   different clip (shifted window, or a different question) within ±2 s
   absolute. Unstable claims stay `model-only`.
5. **Pair comparison with a control.** Recurrence is asked as a two-clip
   SAME/VARIATION/DIFFERENT question. Every batch includes at least one pair
   known to be different; if the control fails, the batch's SAME answers are
   discarded.
6. **Numbers from the model are diagnostics only.** Ask for BPM once per song
   to document the error; never use the answer.
7. **No list questions on long clips.** Asked to enumerate entrances, energy
   per window or several sections over a 40–50 s clip, the model collapses to
   one label or loops ("bass enters / drops out" every second, "2 - no change"
   for 40 s). Keep clips at or under one section (about 20 s) and ask for one
   value per call. Only lyrics transcription tolerates long clips.
8. **Lyrics are the vocal-phrase detector.** Timestamped lyric lines are the
   model's most reliable time-resolved output: every line in the pilot fell on
   an active vocal stem, line starts mark sung phrases, and the first and last
   lines of a clip locate vocal entries and exits to about ±1 s. Parallel line
   templates across choruses identify returning sections even when the words
   differ. Gate the lyrics question on measured vocal presence: on an
   instrumental clip it emits digit loops.
9. **Pairs beat absolute ratings.** "Which clip is more intense, A or B" gave
   musically sensible orderings where absolute 1–5 ratings had collapsed, but
   the equal-material control was answered "A", so every pair must be asked in
   both orders and only consistent answers count. For recurrence, ask a second,
   lyric-agnostic variant ("same melody ignoring the words") so that different
   chorus lyrics are not mistaken for a different section.
10. **Do not ask the model for change points.** "Does the section change inside
    this clip" returned NO CHANGE across known vocal exits and entries. Boundaries
    come from lyrics timing, section-clip function labels and measurement, not
    from change-point questions.
11. **Drum and lead descriptions are boilerplate.** B2 returned the same
    four-on-the-floor paragraph for all ten sections, including the quiet
    turnaround; B1 returned "lead vocal, changes at 12.233 s" for three different
    choruses. Use B1 only for vocal-versus-instrumental lead, and take drum
    pattern, fills and breaks from the drum stem, not from the model.

Measurement rules. Doubt your own grid before anything is built on it.

12. **Doubt the grid.** Never assume the tempo or the meter is constant. Fit the
    tempo in windows (about 20 s), check beat-phase drift, and check the
    kick/snare pattern per window. Xterfusion drifted 74–108 s; ハテ changed
    from 7/8 at 220.5 pulses per minute to 4/4 at 126 BPM with the bar length
    unchanged, with three passages that have no pulse at all. When the grid is
    not single, record a piecewise grid (`L0_identity_grid.tempo_segments`: each
    segment with seconds, BPM, meter, anchor, confidence) and keep every
    section's `seconds` authoritative; `beats` then use the config grid and are
    approximate. Where no stable pulse exists, say so instead of inventing one.
13. **Check half, double and the bar.** Report the half and double tempo
    candidates and why they were rejected (kick on every beat, snare on 2 and 4,
    bar/n subdivision test). Take beat zero from the drum stem's kick phase, not
    from the full mix, which was ambiguous by half a beat on NightTheater. Check
    where phrases start: a 4-beat pickup bar before the first 16-beat phrase is
    common and must not shift the section grid.
14. **Stems need a high-pass.** Demucs htdemucs stems can carry a DC offset
    that makes a silent vocal stem read −37 dBFS. High-pass at about 20 Hz
    before measuring RMS; `vocal_ranges_seconds` are 2 s bins above −40 dBFS
    after that.
15. **Recurrence by MFCC and lagged chroma, not block chroma.** Block chroma
    similarity was 0.95–1.00 for nearly every pair on three songs built on one
    harmonic loop, so the old ≥ 0.9 rule separates nothing. Use MFCC similarity
    at the best lag plus sequence chroma with a lag search; block chroma is kept
    only as a side figure.
16. **On songs without a clear sung lead, the model's pair, function, energy
    and lyric questions contribute almost nothing.** Across NightTheater and
    ハテ it answered DIFFERENT in 63 of 68 pair calls, including pairs with the
    highest measured similarity in the song, gave one boilerplate function
    label to most clips, rated energy 2–3 everywhere, said VOCALS on every clip
    and looped a single lyric line. Only the vocal-versus-instrumental lead
    answer was useful (agreed with the vocal stem on about 80% of clips). Run
    the protocol anyway so the record documents it, but reconcile from
    measurement and song position, and mark the function labels `contradicted`
    or `measurement-only` honestly.

## 3. Listening protocol

Implemented in `agent-tools/song-analysis/pilot_moss.py` (`--protocol v1` is the first pilot as run,
`--protocol v2` the follow-up probes). Each pass is a set of (clip, question)
calls; raw answers are stored one file per call with clip range, SHA-256,
model path, prompt and absolute offset. The table is the v1 design; the
"Keep?" column records the pilot verdict and is what the next version runs.

| Pass | Clips | Questions | Feeds | Keep? |
| --- | --- | --- | --- | --- |
| A Overview | 4 overlapping 40–50 s windows | A1 structure list; A2 entrances/exits; A3 energy per 4 s; A4 lyrics with timestamps | MF0, ML1, ML4, ME0 | A4 yes, on vocal passages only. A1 only on the first window; A2, A3 dropped (rule 7) |
| B Sections | One clip per candidate section (≤ 20 s) | B1 lead layer; B2 drum pattern; B3 function, energy, tension, pickup, ending | MF0, ML3, MR0, ME0–ME1 | B3 yes; B1 reduced to vocal/instrumental; B2 dropped (rule 11) |
| C Recurrence | Pairs plus a control | SAME / VARIATION / DIFFERENT; lyric-agnostic variant | MF1 recurrence groups | Yes, both orders, both variants (rule 9) |
| D Stability | Shifted windows | A1 again | Status of MF0 boundaries | Replaced by cross-question agreement (rule 4) |
| E Grid check | One 30 s clip | BPM and meter | Documents numeric error | Yes, one call |
| New: pairwise intensity | Section pairs in both orders | Which is more intense, A/B/EQUAL | ME2 ordering | Added (rule 9) |

Measured cost on the M5 32 GB machine: model load 2–4 s, 1–4 s per call on
section clips, 8–35 s on 50 s windows, 6.6 GB peak memory; the 55-call v1 pass
took 379 s of model time and the 15-call v2 pass about 100 s. Running the model directly
through `mlx_audio` (as the script does) rather than through the live-editor
MCP is appropriate for analysis of a song file; the MCP remains the path when
the question is about the open project's audio.

### Running v3 on a new song

`pilot_moss.py --protocol v3 --config song.json` takes the song's measured grid
and candidate sections; nothing song-specific is in the script. Config fields:

```json
{"bpm": 150.0, "offset_seconds": 0.123,
 "sections": {"intro": [0, 32], "a1": [32, 96], "end": [288, null]},
 "clips": {"hookA": [8, 40], "hookB": [200, 232]},
 "pairs": [["C_hook", "hookA", "hookB"]], "control_pairs": [["C_ctrl", "hookA", "S_a1"]],
 "intensity_pairs": [["PI_1", "S_intro", "S_a1"]],
 "vocal_ranges_seconds": [[12.0, 60.0], [68.0, 128.0]]}
```

Beats are in the config grid, `null` means audio end; sections longer than 20 s
are split into equal clips `S_<name>_1..n`. Pair members may be `clips` names or
`S_` section clip names. Every pair is asked in both orders, as SAME/VARIATION/
DIFFERENT and as the lyric-agnostic variant. `vocal_ranges_seconds` (from a
vocal stem) gates the lyrics question; without it the gate is the model's own
VOCALS/NO VOCALS answer, which said VOCALS on an instrumental clip in testing.
Most rhythm-game songs have no vocals at all; for them the lyric layer is
simply empty and the record relies on section clips, pairs and measurement.

## 4. Reconciliation

1. Convert every model time to absolute seconds (`clip.from_seconds + t`).
2. Cluster boundary and entrance claims across windows and passes within ±2 s.
   A cluster with claims from two independent windows is `stable`.
3. Snap each stable cluster to the nearest measured candidate within 2 s
   (energy step, stem entrance, chroma novelty peak, previous reviewed
   boundary) and express it in beats. No candidate within 2 s: keep the model
   time with status `model-only`, unsnapped.
4. Function labels: majority across A1, B3 and D1/D2 for the beats the section
   covers. Disagreement is recorded as `contradicted` with all labels.
5. Recurrence: C answers define groups; chroma self-similarity between the two
   clips is attached as the measurement side. SAME with similarity ≥ 0.9 is
   `corroborated`; SAME with low similarity or DIFFERENT with high similarity
   is `contradicted`.
6. Energy: per 4-second bin, keep the model's 1–5 rating and the measured
   relative RMS side by side. Climax spans are proposed where model energy is
   ≥ 4 for at least 32 beats **and** B3 calls the function chorus/final
   chorus; loudness alone never creates a climax. When that rule selects
   nothing (it selected nothing on any instrumental song), propose candidates
   from measured section level, layer count and song position, and mark them
   `contradicted` or `measurement-only`.
7. **Climax position prior (user rule, 2026-11-08).** In a regular song the
   climax is near the end: usually the second- or third-to-last section, rarely
   the last one (that is the outro) and almost never in the first half. When
   there are several candidates they are normally all near the end. So: list
   candidates in order of position-weighted strength, the latest strong one
   first; a candidate that starts in the first half of the song is demoted to
   `early peak` and kept only as a secondary entry with its evidence; a
   candidate in the final sections needs less model support than one in the
   middle. Only a measured collapse after the candidate (drums out, level
   down for a whole section) justifies naming a mid-song climax as primary,
   and then the record must say why the song is irregular.
8. Lyrics: used for phrase boundaries and for identifying returning text
   (chorus identity), not for exact onset times.

### Blind runs

A new song is analyzed by a context-free subagent that gets only the
tag-stripped audio and the files named in [blind-run.md](blind-run.md). The
per-run prompt only supplies the audio path and the scratch directory.

## 5. Scope

It does not decide hit times, note types or positions (roadmap step 1), does not
rate difficulty, does not claim emotional truth, and does not replace listening
by the user. Its job is to give the charting agent a song description that is
musically structured, time-aligned to the grid, and honest about what is
measured, what is heard by a model, and what the user has confirmed.
The micro level (which grid slots get notes, per phrase and layer) is
covered separately in [phrase-rhythm.md](phrase-rhythm.md).

Model claims stay `model-only` or `corroborated`, never `user-confirmed`, until
the user confirms them. The user's review remains the gate.
