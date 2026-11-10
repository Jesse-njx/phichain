# Phrase rhythm (micro analysis)

This framework answers the micro question: **which timestamps get notes**, by
asking what rhythm the player plays in each phrase, on which layer, at which
subdivision. The timestamp is derived: grid slot → beat → seconds through the
SAR grid (MG1–MG4). Code lives in `agent-tools/phrase-rhythm/`. No MCP tool, editor
feature or chart state is added, and nothing edits a chart.

The macro framework produces a Song Analysis Record (SAR, XR0). This
framework consumes the SAR and produces a **Phrase Rhythm Record (PRR, XR1)**:
for every phrase, the rhythm lines of each layer on the beat grid, the
recurring cells they form, and two to four candidate *readings* of what the
player plays, with their articulation and anchors. The chart agent (roadmap
step 1) takes one reading as its hit times. All codes such as `MR1` are
defined in [terminology.md](../shared/terminology.md); the record items
below are the PRR rows of its music-understanding tables.

## 1. Principles

1. **Grid first, audio second.** The grid proposes a fixed set of slots per bar;
   the audio answers, per layer and per slot, "is there an attack here". This
   turns detection into classification on a known slot set. Off-grid onsets are
   reported as evidence of a wrong grid, a triplet, a free-rhythm passage or a
   human performance, never promoted to notes on their own.
2. **The unit is the bar cell and the phrase, not the event.** Each layer's
   rhythm is written as one string per bar (`X.x.X.x.X.x.X.x.`), cells are
   deduplicated across the song, and a phrase is described by which cells it
   uses. Consistency ("constant drum pattern", "same as the first chorus") is
   then a property of the record, not a hope about a detector.
3. **Readings, not a selection.** For each phrase the record offers two to four
   complete readings (the lead line alone; lead plus kick; drums; the dense
   union), each with density statistics. A reading keeps its followed layers
   whole. Thinning for lower difficulty is done by rhythm-preserving operators
   (accents only, downbeats and anchors, gesture heads), never by an acoustic
   strength threshold.
4. **Articulation is part of the rhythm.** Every event in a reading is a fresh
   strike, the start of a sustain with a grid-quantized length, part of a
   gesture (run, roll, glissando), or a simultaneity. Rests are written down.
   Note *type* (Tap/Drag/Hold/Flick) is still the arrangement step's decision;
   the PRR gives it the musical duration and gesture span it needs.
5. **Anchors are never thinned away.** Section arrivals, pickups into them,
   phrase downbeats, fill bars, break edges and the last hit before a rest are
   listed per phrase. Every reading contains every anchor of its followed
   layers. This is the direct answer to "important notes are missing, the
   climax became empty".
6. **Everything carries evidence and status**, with the shared vocabulary
   (XS: `measurement-only`, `corroborated`, `contradicted`, `user-confirmed`)
   plus `propagated` (XS5): a user-confirmed cell copied to another bar where the same
   cell was measured.
7. **The user judges phrases by ear.** Every phrase gets a one-screen rhythm
   sheet and an audition file (clicks per layer over the original audio, one
   file per reading). Corrections are given as a tapped or written cell for one
   phrase and propagate through the cell inventory.
8. **The audio-language model is not used at this level.** Its only
   contribution is already in the SAR (sung versus instrumental lead). It is
   never asked for a timestamp, a subdivision or a pattern.

## 2. The Phrase Rhythm Record

One JSON document per song beside the SAR, plus one rhythm sheet per phrase.
Rows group the registry items by the step that produces them; the item codes
are the JSON keys (`MR1_layer_lines`, `MH0_readings`).

| Items | Content | Evidence | Depends on |
| --- | --- | --- | --- |
| MF3 phrases, MF4 bars, MG6 slot set, MG7 swing | Bars and phrases (4 or 8 bars, pickup bars marked) on the SAR phrase grid; per phrase: smallest subdivision that explains the layers (8th, 16th, triplet, 32nd), swing ratio, local tempo check, `free_rhythm` flag where MG4 has no stable pulse | MG1–MG4 grid and tempo segments, MF0 sections, onset autocorrelation on the drum stem | MG, MF0–MF2 |
| MR1 layer lines, MR4 off-grid onsets | Per layer and bar: one string over the phrase's slot set, each slot `X` (accent), `x` (attack), `~` (sustain continues), `.` (rest), with per-slot evidence strength 0–1; for pitched layers also pitch and quantized duration per attack; off-grid onsets listed separately in seconds | Stems: kick / snare / hat band envelopes of the drum stem; Basic Pitch note events on bass, vocals and other; the v5 monophonic lead path on the lead stem; full-mix flux as a sanity layer | ML0 layer inventory |
| MR2 cells, MR3 fills and breaks | Per layer: the distinct bar cells, their occurrences (bars), variants (fill, pickup, truncated), and the dominant cell per section; a phrase is described as a sequence of cell ids | Computed from MR1 by exact and near match (Hamming ≤ 1 slot) | MR1 |
| MH0 readings, MH1 thinning, MH4 density | Per phrase: two to four candidate hit-time sets, each defined as a union of layer lines plus thinning operators, with density statistics (hits per second mean and peak, smallest interval, chord fraction, sustain count) and the corpus range for the section's function | ML3 lead layer, ME0 energy, MR1, MR2, the calibrated corpus prior | ML3, ME, MH6 |
| MH2 articulation, MR5 gestures, MR6 sustains, MR7 simultaneities | Per event of each reading: fresh strike / sustain start with grid length and release reason (next attack, pitch change, phrase end) / gesture member with gesture id and span / simultaneity member; rests and breaks explicit | MR1 pitch and duration, gesture rules in section 3 | MR1, MH0 |
| MH3 anchors | Per phrase: section arrival, pickup into it, phrase downbeats, fill bars (cells that deviate from the section's dominant cell), break edges, last hit before a rest, climax entry; each with the layer it belongs to | MF0 boundaries, MR2 deviations, measured silence | MF0, MR2 |

A reading is an object:

```json
{"id": "R-lead+kick", "phrase": "P07", "follows": ["lead", "kick"],
 "thinning": [], "events": [{"slot": "b1.0", "beat": 100.0, "seconds": 39.872,
   "layers": ["lead", "kick"], "articulation": "strike", "anchor": "section_arrival"},
   {"slot": "b1.2", "beat": 100.5, "seconds": 40.071, "layers": ["lead"],
   "articulation": "sustain", "length_beats": 1.5, "release": "next_attack"}],
 "density": {"hits_per_s_mean": 4.1, "hits_per_s_peak": 8.0, "min_interval_ms": 125,
   "chord_fraction": 0.12, "sustains": 3},
 "corpus_range": {"function": "chorus", "level": "IN", "hits_per_s_p25_p75": [3.6, 6.2]},
 "status": "measurement-only", "evidence": ["MR1:lead:P07", "MR1:kick:P07"]}
```

Slots (XT5) are written `b<bar>.<index>` within the phrase; `beat` is in the
SAR grid and `seconds` through MG1–MG2. Where MG4 has a piecewise grid,
`seconds` is authoritative, as in the macro framework (rule 12).

## 3. Rules

Grid and slots.

1. **Slot set per phrase.** Start from 1/4 beat (sixteenths). Add 1/3 and 1/6
   (triplets and sextuplets) when a layer's onsets near the triplet-only
   positions (1/6, 1/3, 2/3, 5/6 beat, ±1/48) are ≥ 15% of its onsets, at least
   four, and at least twice the onsets near equally wide control positions on
   neither grid (1/12, 5/12, 7/12, 11/12). Add 1/8 (32nds) for a drum layer by
   the same test on the odd 32nds. The timing
   tolerance is ¼ of the finest subdivision with a 15 ms floor, capped below
   half the smallest slot gap. Record the chosen set and the share of onsets it
   explains; below 90% the phrase is flagged for the user before anything is
   built on it.
2. **Attack in a slot.** A layer attacks in a slot when its onset envelope has a
   local maximum within the tolerance and that maximum is at least 20% of the
   layer's maximum in the same bar, with a prominence of at least 15% of it.
   `X` (accent) when it is ≥ 60% of the bar maximum or lands on a downbeat with
   the layer present. Thresholds are per bar and per layer, never global across
   the song; this is what keeps a quiet verse's kick line complete. A bar
   is only read when the layer is present, i.e. its bar maximum is at least 15%
   of the layer's loud-bar level. Peaks are at least half a sixteenth apart.
2a. **Phase alignment.** Every detector has a constant latency (the
   drum stem's sub-bass builds up 20–30 ms after the beater click; Basic Pitch
   frames are 11.6 ms), and MP3 stems from Demucs lag the decoded mix by about
   25 ms. So: stems are aligned to the decoded mix by cross-correlation; the
   per-layer latencies are measured on the corpus against official heads
   (`calibrate.py`) and subtracted on every song; the remaining
   offset of the drum onsets from the grid is reported as `grid_check`, because
   it means the SAR's beat zero is off. With `--fit-phase auto` the offset is applied when the
   clearly periodic layers agree on it; the SAR should still be corrected
   upstream.
3. **Off-grid onsets.** An onset farther than ¼ slot from every slot is listed
   under `off_grid` with its seconds and layer. More than three drum onsets per
   bar means
   the grid, the slot set or the `free_rhythm` flag is wrong, and the bar is
   marked `contradicted` (XS3) until resolved. In a `free_rhythm` segment the layer
   lines are replaced by the raw event list in seconds, as the macro
   framework does for its sections.
4. **Swing.** Estimate the mean displacement of off-beat eighths and sixteenths
   in the hat and lead lines. If it exceeds 10% of a slot consistently, store
   `swing_ratio` and compute `seconds` with it; the slot strings stay straight.

Layers and cells.

5. **Layers come from stems, not from frequency bands of the mix.** Kick, snare
   and hat come from the drum stem only. Drum onsets are detected on the drum
   stem's broadband flux, which is well timed, and each onset is labelled by how
   much each component of an NMF decomposition of the drum stem rises there; a
   snare or hat label needs 1.5× the energy the song's kick leaks into that
   component. Lead, bass, chords and vocals come from Demucs stems through Basic
   Pitch and the v5 monophonic lead decoder. The lead stem per section is the SAR's lead
   layer (ML3); where ML3 is `contradicted`, both candidates get a line.
6. **Pitched-layer attacks need a pitch event, not only an onset.** A new note
   in the lead line is an attack if Basic Pitch or the lead path starts a note
   there, including a pitch change without a new onset (legato). A repeated
   pitch with a new onset is a rearticulation and is an attack. Vibrato and
   octave errors are smoothed by the path decoder, not by thresholds.
7. **Cells.** A bar string is a cell. Two bars share a cell when their strings
   match exactly, or differ in one slot, in which case the rarer one is a
   variant. Identity ignores the accent level, `X` versus `x`, which is detector
   strength noise; the accents stay in the line. A fill is a bar whose cell differs from the section's dominant cell
   in ≥ 3 slots and is followed by a section or phrase boundary within one bar.
   Cell ids are per layer (`K1`, `S2`, `H3`, `B4`, and `V5`/`O6` for the vocals
   and other stems, since the lead can move between them) and stable across the song, so the
   record can say "chorus 2 uses the same lead cells as chorus 1 except bar 8".
8. **Sustains.** In a pitched layer, an attack whose quantized note length is
   ≥ 2 slots and ≥ 120 ms, and that is either released into a rest (or the
   phrase end) or lasts at least a beat, is a sustain candidate with that
   length and a release reason. Short sustains are
   normal (official median hold lengths 126–183 ms); the arrangement step
   decides whether a sustain becomes a Hold, a Tap, or a Tap plus Drag.
9. **Gestures.** Three or more consecutive attacks of one layer at the phrase's
   smallest subdivision with monotonic or constant pitch form a gesture (run,
   roll, glissando). The gesture gets an id and a span; its head is an anchor
   candidate; its members are kept in every reading that follows the layer,
   so a run is never half-charted. Whether the arrangement plays it as taps or
   as a tap with drags is not decided here (Verrückt plays the same spacing
   both ways).
10. **Simultaneities.** Two layers attacking in one slot with at least one
    accent form a simultaneity candidate. The dense reading keeps both; the
    others keep the followed layer's event and note the other layer.

Readings and thinning.

11. **Default readings per phrase.** `R-lead` (the ML3 lead line alone),
    `R-lead+kick` (lead plus kick accents; snare accents instead in a phrase
    without kick),
    `R-drums` (kick plus snare; hats only in the dense reading), `R-dense` (the
    union of lead, bass attacks and drum accents). An instrumental section
    whose lead is `contradicted` adds one reading per candidate lead. Readings
    are complete per phrase; a phrase may have fewer when layers are absent.
12. **Thinning operators**, applied to a reading to reach a lower density,
    in this order and never below the anchors: drop hats; drop `x` keep `X`
    (accents only); keep gesture heads only; keep beats and anchors only
    (events on integer beats). Each event stores `keep_through`, the highest
    level at which it survives, so every level is a filter of one list.
    Each operator is recorded on the reading. There is no operator "drop the
    weakest N%".
13. **Phrase consistency.** Within a phrase, a layer is either followed in all
    its bars or not at all. A change of followed layer happens at a phrase
    boundary, or at a section arrival, and is recorded as the reason.
14. **Recurrence.** Phrases in the same recurrence group (MF1) get the same
    reading id by default; differences are listed per bar (MR2 variants). A
    reading that would differ between two phrases of one group needs a
    recorded reason (a different lead, a fill, a measured texture change).
15. **Rests and empty passages.** A reading may be empty for a phrase (the
    layers it follows rest). This is written as a rest, with the reason
    (`breakdown`, `drums_out`), not filled from another layer automatically.
    The user accepts regions without playable notes when the music supports it.
16. **Density is reported against the corpus, not targeted.** For each reading
    the record shows the 25th–75th percentile of hits per second for the same
    phrase energy tercile (low, mid, high within the song) of IN charts in the
    reference corpus (`corpus-prior.json`), and flags readings outside the 10th–90th. A
    reading far outside the range is flagged, not altered.

User input.

17. **A tapped or written rhythm is a reading.** Per [rules.md](../charting/rules.md) the user
    may record a rhythm; it is offset-fitted and quantized to the phrase's slot
    set, stored as `R-user` (MH5) with status `user-confirmed` (XS4), and its
   cells propagate to every other bar of the song with the same measured cell
   as `propagated` (XS5). One corrected phrase therefore corrects every return of it.
18. **The user corrects the sheet, not the JSON.** A phrase's rhythm sheet
    shows all layer lines, the cell ids, the readings and the anchors on one
    screen; the audition files let the user hear each reading. The review loop
    is: listen to `R-lead+kick` for phrase 7, say "the lead is right, drop the
    kick, the pickup in bar 4 is missing", and the record updates that phrase
    and its recurrence group.

## 4. Procedure for one song

Inputs: the audio, the SAR (reviewed or blind), the Demucs stems with the
20 Hz high-pass (macro rule 14).

1. **Phrase grid (MF3, MF4, MG6, MG7).** Lay bars and 4/8-bar phrases on the
   SAR grid with the pickup convention of MF2. Per phrase choose the slot set (rule 1), estimate
   swing (rule 4), confirm local tempo against the tempo segments (MG4), mark
   `free_rhythm` where MG4 says no pulse.
2. **Layer lines (MR1, MR4).** Drum stem → kick, snare, hat envelopes → slot
   strings. Bass, vocals, other → Basic Pitch note events; lead stem → v5
   path → attacks with pitch and length. Full-mix flux as a sanity line to
   catch a layer the stems missed (a loud event with no layer attack is
   listed, not charted).
3. **Cells (MR2, MR3).** Deduplicate bar strings per layer, name cells, find
   variants, fills and the dominant cell per section. Cross-check with MF0:
   the dominant cell should change at most section boundaries; a change
   inside a section is reported.
4. **Readings (MH0, MH1, MH4).** Build the default readings per phrase from ML3; compute
   density statistics; attach the corpus range; apply recurrence defaults
   (rule 14).
5. **Articulation and anchors (MH2, MR5–MR7, MH3).** Sustains, gestures,
   simultaneities, rests; anchors from MF0 and MR2.
6. **Sheets and auditions (XR3, XR4).** One text sheet per phrase; one click-track WAV
   per reading per section (distinct click per layer, original audio
   underneath). No editor, no chart.
7. **Review.** The user listens to two or three phrases per section function,
   corrects by cell, the corrections propagate, and the chosen reading per
   section becomes the hit-time input for the arrangement step.

Rhythm sheet, one bar of a chorus at 151 BPM, sixteenth slots:

```
P07 bar 1  (beats 100–104, 39.87–41.46 s)   cells: K1 S1 H2 L4   anchor: section_arrival
kick   X...X...X...X...   K1 (dominant, bars 1–8)
snare  ....X.......X...   S1
hat    x.x.x.x.x.x.x.x.   H2
lead   X.~~x.x.X~~~x.x.   L4   pitches  C5 ~~ D5 E5 G5 ~~~ E5 D5   sustain b1.0 ×3 slots, b1.8 ×4
bass   X.......X.......
R-lead        X...x.x.X...x.x.      3.5 hits/s   corpus chorus IN 3.6–6.2
R-lead+kick   X...X.x.X...X.x.      4.5 hits/s
R-dense       X.x.X.x.X.x.X.x.      7.6 hits/s   (hats dropped)
```

## 5. Interfaces

- **From the SAR:** grid and tempo segments (MG1–MG4), sections with pickups
  and recurrence groups (MF0–MF2), layer presence (ML0), lead per section
  (ML3), energy (ME0) for the density envelope. The PRR does not re-derive any of these; a wrong SAR
  produces a wrong PRR and is corrected upstream.
- **To the arrangement step (roadmap N0):** one reading (MH0) per section, as
  timed hits with articulation (MH2), gesture spans, sustain lengths,
  simultaneities, anchors (MH3) and phrase boundaries. This is the "hit times of a passage" input
  that step 1 assumes, now with the musical duration and grouping the
  arrangement rules in [rules.md](../charting/rules.md) ask for (fresh hit versus continued
  contact, gesture completion, rests preserved).
- **Difficulty (N7):** the readings and thinning operators are the natural
  ladder: `R-lead` thinned to anchors for low levels, `R-lead+kick` for the
  middle, `R-dense` for the top, with the corpus prior saying what each level
  normally follows. No separate detector per level.

## 6. Running it

Run everything with the [measurement Python](../shared/references.md#python-environments)
(librosa, Demucs, Basic Pitch ONNX).

| File | Role |
| --- | --- |
| `prr_audio.py` | Evidence per song, cached in a `work/` folder: Demucs stems aligned to the decoded mix, 20 Hz high-pass, drum-stem flux and NMF activations, Basic Pitch frames, v5 monophonic paths for vocals, other and bass |
| `prr_build.py` | The record: grid from the SAR (or a plain grid), bars and phrases, slot sets, swing, phase alignment, layer lines, cells, fills and breaks, sustains, gestures, simultaneities, anchors, readings with `keep_through` thinning, density, corpus range, recurrence defaults |
| `prr_render.py` | Rhythm sheets (one text file per phrase plus `sheets.md`) and auditions (one `.ogg` per reading per section: a click timbre per layer, a soft tone for a sustain's length, original audio at −6 dB) |
| `prr.py` | CLI: `build` (`--sar` or `--grid`, `--auditions`, `--reference-chart`, `--fit-phase auto|on|off`) and `apply-user` |
| `corpus.py` | Corpus list and evidence extraction |
| `test_prr.py` | 14 tests on synthetic evidence (`python -m unittest test_prr`) |

```
python agent-tools/phrase-rhythm/prr.py build --audio <song> --sar <song-analysis-record.json> --out <dir> --auditions
```

Phrases default to 4 bars, starting at each section's first bar
(`--phrase-bars` changes it). Longer structure is carried by recurrence groups,
not by longer phrases.

To record a user rhythm (rule 17), put `prr-user.json` in a PRR folder with
`{"rhythms": [{"phrase": "P07", "bars": {"1": "X...x.x.X...x.x."}}],
"choices": [{"phrase": "P07", "reading": "R-lead", "apply_to_group": true}]}`
(or `"taps_seconds": [...]` instead of `bars`) and run
`prr.py apply-user --out <folder>`.

## 7. Scope

It does not decide positions, note types or hand plans; it does not rate
difficulty; it does not use the audio-language model; it does not claim that
any reading is *the* chart. It makes the rhythm of each layer explicit on the
grid, keeps every candidate reading whole and auditable, and lets the user
correct one phrase and have the correction reach every return of it.

Readings stay `measurement-only` (XS0) or `corroborated` (XS2), and no reading
is handed to an arrangement run without the user choosing it.
