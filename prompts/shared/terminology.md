# Terminology and codes

The single registry of the terms and codes used across AutoPhiChain's
documents, records and prompts. Set up 2026-11-08 at the user's request. Every
other document uses the codes defined here and links back; no document defines
a competing code. When a new term is needed, it is added here first.

## 1. The code

A code is three characters: **component letter, aspect letter, item digit**.

```
M G 1
│ │ └─ item: tempo (BPM and the half/double check)
│ └─── aspect within the component: G = Grid
└───── component of chart making: M = Music understanding
```

Rules.

1. **The first letter is the component of chart making** (section 2). There
   are three, arguably four, and one letter for what cuts across them.
2. **The second letter is an aspect within that component**, a group of
   closely related items. Aspect letters are unique within a component only;
   `MG` and `PG` may both exist.
3. **The digit identifies the item.** It is an identifier, not a rank and not
   an order of work. Once assigned it is never reused: a retired item keeps
   its digit and is marked retired here. An aspect that outgrows ten items is
   split into two aspects rather than given a fourth character.
4. **Written form.** In prose, the name first and the code in parentheses on
   first mention: "tempo (MG1)". In headings and tables, code then name:
   "MG1 tempo". A whole aspect is the two letters: "the grid (MG)". A whole
   component is the one letter, spelled out in prose: "music understanding (M)".
5. **In records and JSON**, a key is the code, an underscore, and the name in
   lower snake case: `MG1_tempo`, `MH0_readings`. Records written before this
   registry keep their keys; section 8 maps them.
6. **Claim fields** (`value`, `source`, `status`, `evidence`, `confidence`,
   `note`) are the same on every item in every record. Their vocabularies are
   the cross-cutting items in section 7.
7. **Two-character codes are not terminology codes.** Roadmap milestones
   (N0–N7), autonomy levels (A0–A3), evaluation layers (L0–L2) and listening
   protocol call ids (A1, B3, C, CM, PI, VP, E1) keep their existing short
   names; section 8 lists them so that nothing new collides with them.

## 2. Components (first letter)

| Letter | Component | Roadmap | Decides |
| --- | --- | --- | --- |
| **N** | Note arrangement | step 1 | Given hit times: position, type, hand plan, phrase-level cells |
| **M** | Music understanding | step 2 | Grid, form, layers, rhythm, energy, and which hits the player plays |
| **P** | Performance | step 3 | Judgment-line motion, effects, visibility, choreography |
| **G** | Game design | above the roadmap, out of scope | Difficulty identity, pacing, how a chart sits among others |
| **X** | Cross-cutting | — | Statuses, evidence sources, time scales, records, autonomy, evaluation |

The letters are taken from the component names (Note, Music, Performance,
Game) so that they read without a table. `A` is not used for arrangement
because A0–A3 are the autonomy levels.

## 3. N — Note arrangement

Items here come from `prompts/charting/rules.md` and `prompts/charting/design.md`; the registry
names them, it does not restate the rules.

### NT Note types

| Code | Item | Definition |
| --- | --- | --- |
| NT1 | Tap | A fresh screen hit at the head time |
| NT2 | Drag | Contact present at the checkpoint; no fresh hit required |
| NT3 | Hold | A stricter initial hit followed by sustained contact to the tail |
| NT4 | Flick | A flick gesture; its fresh-hit or from-contact intent is stated per use (NA4) |

NT0 is unused so that the digits match the type numbers in the arrangement
datasets (1 Tap, 2 Drag, 3 Hold, 4 Flick).

### NA Player actions

| Code | Item | Definition |
| --- | --- | --- |
| NA0 | fresh hit | A new finger contact with the screen |
| NA1 | continued contact | A finger already down moves or stays to satisfy a checkpoint |
| NA2 | sustained occupancy | A finger held down for a Hold; it occupies one contact in the hand plan |
| NA3 | release | The finger leaves the screen; its timing is judged in the action phrase, not by a millisecond gap |
| NA4 | flick intent | Fresh-hit-and-flick, or flick from existing contact |
| NA5 | rest | An empty rhythmic slot with no playable object; preserved in hand analysis |
| NA6 | simultaneous set | Objects at one time; unordered with respect to hands |

### NF Hand plan

| Code | Item | Definition |
| --- | --- | --- |
| NF0 | hand assignment | Which hand or finger takes each fresh hit and contact |
| NF1 | two-finger route | A viable interpretation with one finger per hand; the default design target, not the only execution |
| NF2 | multi-finger route | An interpretation using extra fingers; welcome where dense |
| NF3 | same-hand repeat | Consecutive fresh hits by one hand (double tap, jack); needs a concrete musical reason |
| NF4 | role exchange | Anchor and traveling roles swap between hands |
| NF5 | anchor and travel | One hand locally stationary or repeating while the other travels |
| NF6 | working region | The screen region a hand currently covers; it shifts on its own, not tied to the other hand |

### NC Movement cells and phrase structure

| Code | Item | Definition |
| --- | --- | --- |
| NC0 | movement cell | A short repeated pattern of successive judgment positions per hand |
| NC1 | mirror | The spatial mirror of a cell, with hand roles mirrored together |
| NC2 | return | A purposeful return to an earlier position or cell |
| NC3 | wide-movement trill (位移交互) | Alternating fresh hits with substantial coherent travel per hand |
| NC4 | guidance (引导) | Establishing intended hands through progressive repetition |
| NC5 | contrast | A deliberate change of cell, density or geometry between sections |
| NC6 | stillness | A stationary anchor, repeated position or sparse passage chosen on purpose |

### NP Geometry

| Code | Item | Definition |
| --- | --- | --- |
| NP0 | judgment position | Where the player must hit or contact, after line transforms |
| NP1 | pure configuration (纯配置) | Exactly one static judgment line carrying every playable note |
| NP2 | contact region | The region a finger can satisfy given judgment tolerance and screen scale |
| NP3 | travel | Successive same-finger contact displacement, judged against NP2, not note-center distance |
| NP4 | scroll speed | Note approach speed; distinct from temporal density |

## 4. M — Music understanding

The Song Analysis Record (XR0) holds the song- and section-scale items; the
Phrase Rhythm Record (XR1) holds the phrase-, bar- and slot-scale items. Both
are the same registry: the macro framework fills some digits of an aspect,
the micro framework fills others, as the "Record" column says.

### MG Grid

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| MG0 | audio identity | SAR | Audio hash, duration, decoded sample rate |
| MG1 | tempo | SAR | BPM from pulse fit, with the half and double candidates and why they were rejected; never from the model |
| MG2 | beat zero | SAR | Audio time of beat 0, from the drum stem's kick phase |
| MG3 | meter | SAR | Beats per bar; checked per window |
| MG4 | tempo segments | SAR | Piecewise grid where tempo or meter changes, and free-rhythm spans with no stable pulse |
| MG5 | key | SAR | Optional; model answers are diagnostics only |
| MG6 | slot set | PRR | Per phrase: the subdivisions in use (1/4, 1/3, 1/6, 1/8 beat) and the share of onsets they explain |
| MG7 | swing | PRR | Mean displacement of off-beat subdivisions, when consistent |

### MF Form

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| MF0 | sections | SAR | Ordered `[start, end)` spans in beats and seconds with a function label (intro, verse, pre-chorus, chorus, hook, break, breakdown, build, drop, bridge, outro) |
| MF1 | recurrence groups | SAR | Which sections restate which (A, A', B...), with the measured similarity |
| MF2 | pickups | SAR | Anacrusis bars or beats before a section's arrival |
| MF3 | phrases | PRR | 4- or 8-bar phrases on the section grid, pickup bars marked |
| MF4 | bars | PRR | Bar lines on the grid; the unit of a rhythm cell |

### ML Layers

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| ML0 | layer inventory | SAR | Layers present per section (lead vocal, lead synth, guitar, bass, kick, snare, hats, pads, FX) and their foreground or background role |
| ML1 | entrances and exits | SAR | When a layer enters or leaves, in beats |
| ML2 | vocal ranges | SAR | Spans where the high-passed vocal stem is active |
| ML3 | lead layer | SAR | Per section, the layer a player should follow; `contradicted` when stem and model disagree |
| ML4 | lyric lines | SAR | Timestamped lines from the model, used for phrase boundaries, never for onsets |

### MR Rhythm

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| MR0 | drum pattern class | SAR | Four-on-the-floor, backbeat, half-time, breakbeat, absent; per section, from the drum stem |
| MR1 | layer lines | PRR | Per layer and bar, one string over the slot set: `X` accent, `x` attack, `~` sustain continues, `.` rest, with per-slot evidence strength |
| MR2 | cells | PRR | Distinct bar strings per layer, with occurrences, variants and the dominant cell per section |
| MR3 | fills and breaks | both | Bars that deviate from the dominant cell before a boundary; bars where a layer or all layers stop |
| MR4 | off-grid onsets | PRR | Onsets farther than a quarter slot from every slot; evidence against the grid, never notes |
| MR5 | gestures | PRR | Three or more consecutive attacks of one layer at the smallest subdivision with monotonic or constant pitch (run, roll, glissando) |
| MR6 | sustains | PRR | Pitched attacks with a quantized length of at least one slot and a release reason |
| MR7 | simultaneities | PRR | Two layers attacking in one slot with at least one accent |

### ME Energy

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| ME0 | energy per bin | SAR | Per 4-beat bin: model rating and measured level side by side |
| ME1 | tension | SAR | Building, steady or releasing, per section |
| ME2 | pairwise intensity | SAR | Which of two sections is more intense; both orders must agree |
| ME3 | climax candidates | SAR | Spans with a musical reason, ordered by the position prior (near the end of a regular song) |
| ME4 | drops, breaks and build-ups | SAR | Point events with beats |

### MH Hits

What the player plays. The output of music understanding and the input of
note arrangement.

| Code | Item | Record | Definition |
| --- | --- | --- | --- |
| MH0 | readings | PRR | Per phrase, two to four complete candidate hit-time sets, each a union of layer lines: R-lead, R-lead+kick, R-drums, R-dense, R-user |
| MH1 | thinning | PRR | Rhythm-preserving reductions applied to a reading: drop hats, accents only, gesture heads only, downbeats and anchors only; never "drop the weakest" |
| MH2 | articulation | PRR | Per event: strike, sustain start with length and release reason, gesture member, simultaneity member; rests explicit |
| MH3 | anchors | PRR | Section arrival, pickup, phrase downbeat, fill bar, break edge, last hit before a rest, climax entry; never thinned away |
| MH4 | density | both | Hits per second (mean, peak), smallest interval, chord fraction, sustain count; reported against the corpus range, never targeted |
| MH5 | user rhythm | PRR | A rhythm the user tapped or wrote for a phrase, quantized to MG6, status user-confirmed, propagated by MR2 |
| MH6 | background driver | SAR | The layer background-line choreography should follow in a section; consumed by performance (PR0) |

## 5. P — Performance

Items come from `prompts/charting/design.md`, `prompts/charting/rules.md` and the judgment-line
bank. More are added when step 3 is worked on.

### PL Lines

| Code | Item | Definition |
| --- | --- | --- |
| PL0 | receiver | The line receiving the current notes; must be identifiable by the player |
| PL1 | carrier | A line that carries notes but is inactive or hidden now |
| PL2 | background line | A decorative line with no notes; must actually perform |

### PM Motion

| Code | Item | Definition |
| --- | --- | --- |
| PM0 | impact dip | A short depression and recovery on a musical hit |
| PM1 | rhythmic translation | Receiver or background movement in x or y with accents on musical events |
| PM2 | rotation | Angle change with stated anchors |
| PM3 | formation | Several lines moving as one figure (sweep, fan, delayed followers) |
| PM4 | receiver change | Notes move to another line; needs a readable handoff |
| PM5 | static | No motion, chosen on purpose |

### PE Effects

| Code | Item | Definition |
| --- | --- | --- |
| PE0 | opacity change | Flash, fade, reveal, subordination |
| PE1 | speed event | Scroll change or stop |
| PE2 | entrance and exit | How a line or figure appears and leaves |

### PR Rhythm anchors

| Code | Item | Definition |
| --- | --- | --- |
| PR0 | driving layer | The musical layer a motion phrase follows (from MH6) |
| PR1 | motion accents | The events where direction changes, arrivals, pulses and flashes land |
| PR2 | phase and interval | For a repeating figure, the constant phase and spacing of visual changes |

### PV Readability

| Code | Item | Definition |
| --- | --- | --- |
| PV0 | receiver identification | Whether the player can tell which line receives the next notes |
| PV1 | approach lead time | Visible time from a note's appearance to judgment |
| PV2 | crowding | Simultaneous on-screen heads in a dense passage |
| PV3 | tail coverage | Hold tails and contact paths fully visible and on a clear carrier |

## 6. G — Game design

Reserved. Out of the roadmap's scope; named so that difficulty and pacing have
a home when they are discussed.

| Code | Item | Definition |
| --- | --- | --- |
| GD0 | target level | The difficulty the user asks for (EZ, HD, IN, AT and a number) |
| GD1 | difficulty identity | What makes this chart's difficulty feel like itself, beyond density |
| GP0 | pacing | Density and intensity across the whole song, by section |

## 7. X — Cross-cutting

### XS Claim status

| Code | Item | Definition |
| --- | --- | --- |
| XS0 | measurement-only | Only measurement supports it |
| XS1 | model-only | Only the audio-language model supports it |
| XS2 | corroborated | Two independent sources agree |
| XS3 | contradicted | Sources disagree; both sides kept visible |
| XS4 | user-confirmed | The user accepted it; beats everything |
| XS5 | propagated | A user-confirmed cell copied to another bar with the same measured cell |

### XE Evidence source

| Code | Item | Trusted for | Not trusted for |
| --- | --- | --- | --- |
| XE0 | measurement | Timing, tempo, energy and texture change, repetition, slot attacks | Function, which layer leads, pickups |
| XE1 | model | Function labels, instrumentation, vocal presence, lyrics, same/different, sung versus instrumental lead | BPM, meter, key, timestamps, subdivisions, patterns |
| XE2 | reference | How a function is typically charted, density ranges | The specific song |
| XE3 | user | Everything; the only acceptance gate | — |

### XT Time scales

| Code | Item | Definition |
| --- | --- | --- |
| XT0 | song | The whole audio |
| XT1 | section | One MF0 span |
| XT2 | phrase | One MF3 span, 4 or 8 bars |
| XT3 | bar | One MF4 span |
| XT4 | beat | One grid beat (MG1, MG2) |
| XT5 | slot | One subdivision of a beat from MG6; written `b<bar>.<index>` inside a phrase |
| XT6 | event | One attack, sustain or rest at a slot |

### XR Records and review artifacts

| Code | Item | Definition |
| --- | --- | --- |
| XR0 | Song Analysis Record (SAR) | One JSON per song with the SAR items of section 4 |
| XR1 | Phrase Rhythm Record (PRR) | One JSON per song with the PRR items of section 4 |
| XR2 | song project record | The per-song folder of design decisions, progress and evidence in `charts/` |
| XR3 | rhythm sheet | One-screen text view of a phrase: layer lines, cell ids, readings, anchors |
| XR4 | audition | A click track per reading over the original audio |

### XA Autonomy levels (alias of roadmap A0–A3)

| Code | Item | User provides |
| --- | --- | --- |
| XA0 | manual | Every placement |
| XA1 | directed | Per-passage intent |
| XA2 | supervised | Song-level intent and corrections after review |
| XA3 | autonomous | Only the song and target difficulty |

### XV Evaluation layers (alias of `research-tools/agent-evals` L0–L2)

| Code | Item | Definition |
| --- | --- | --- |
| XV0 | validity | Structural and physical feasibility checks |
| XV1 | detectors | Measured statistics against official distributions, not targets |
| XV2 | blind review | The user rates agent and reference output without knowing which is which |

## 8. Legacy names and reserved short codes

Codes used before this registry. Existing files and JSON keys keep them; new
writing uses the registry codes.

| Legacy | Where | Registry |
| --- | --- | --- |
| L0 Identity and grid | song analysis framework, `L0_identity_grid` | MG0–MG5 |
| L1 Form | `L1_form` | MF0–MF2 |
| L2 Layer inventory | `L2_layers` | ML0–ML2 |
| L3 Lead line | `L3_lead_line` | ML3, ML4 |
| L4 Rhythm vocabulary | | MR0, MR3 |
| L5 Energy and tension arc | `L5_energy` | ME0–ME4 |
| L6 Charting implications | | MH4, MH6, MR6 sustain candidates, MF1 relations |
| M0 Phrase grid | phrase rhythm framework, first draft | MG6, MG7, MF3, MF4 |
| M1 Layer rhythm lines | | MR1, MR4 |
| M2 Cell inventory | | MR2, MR3 |
| M3 Readings | | MH0, MH1, MH4 |
| M4 Articulation | | MH2, MR5, MR6, MR7 |
| M5 Anchors | | MH3 |
| A0–A3 | roadmap autonomy levels | XA0–XA3; the short form stays in the roadmap |
| L0–L2 | `research-tools/agent-evals` layers | XV0–XV2; the short form stays in the evaluation tool |
| N0–N7 | roadmap step 1 milestones | Not items; written "milestone N3" |
| A1, A4, B1, B3, C, CM, PI, VP, E1 | listening protocol call ids in `pilot_moss.py` and `calls/` | Not items; they name questions, not terms |
| R-lead, R-lead+kick, R-drums, R-dense, R-user | reading ids inside MH0 | Values of MH0, not codes |
| K1, S1, H2, L4 | cell ids inside MR2 | Values of MR2; the letter is the layer (K kick, S snare, H hat, L lead, B bass, V vocal, C chords) |
