# Phrase rhythm framework: design and evidence

Proposed 2026-11-08 at the user's request, after the song analysis framework
(`../song-analysis-framework/DESIGN.md`, the macro level) became reliably
usable. This is research: why the framework exists, how it is calibrated, what
the calibration showed and what remains open. The framework itself is
[prompts/analysis/phrase-rhythm.md](../../prompts/analysis/phrase-rhythm.md);
its code is `agent-tools/phrase-rhythm/`.

## 1. Why the old micro analysis does not work

Every previous attempt treated hit times as something to be **detected** in
the audio and then **filtered**:

| Attempt | Method | User verdict / measured result |
| --- | --- | --- |
| `research-tools/music-analysis/analyze.py` | Transient → attack → priority score → note | "Musically terrible". 1,497 taps where Verrückt IN has 803 heads; sustains became tap streams; 39 of 50 Verrückt holds shorter than its 300 ms hold gate (`../note-analysis/official-reference-review/`) |
| Timing pilot, refinement v2 | Chart-supervised MLP / CNN on spectral-flux candidates | No reliable gain over the baseline; the baseline already puts 82% of candidates within ±20 ms of a chart head at 8 candidates/s, so **timing precision was never the problem** |
| Override timing v2 | Three frequency-band tracks | Rejected: bands are not musical layers |
| Override voices v3 | Five stem + Basic Pitch tracks, 3,356 events | Rejected: too sensitive across the whole song |
| Override two-track v4/v5 | Fitted primary drum pulse + monophonic melody path | "Significantly better" but not usable: the drum pattern should be constant, many melody notes missing |
| Xterfusion audio-only run | Author agent selects detector candidates through "composed rhythmic masks" | Not accepted; the masks were invented, not transcribed |
| MOSS-Music for timestamps | Clip questions | Native resolution is a 2 s marker; wrong on every timing question (song analysis rules 6, 10) |

The same three mechanisms fail each time:

1. **Detection has no notion of rhythm.** A detector sees onsets; a chart is a
   rhythm. The user's complaints are rhythmic: "the drum pattern should be
   constant", "arbitrarily omitting some attacks but keeping others within a
   short phrase feels wrong", "similar regions should have similar chart
   regions". No per-event score can express "constant pattern" or "same as
   bar 9".
2. **Filtering by strength is the wrong operator.** Official charts do not keep
   the loudest events; they follow one layer per passage and keep that layer's
   rhythm whole, including its weak notes and its rests (song analysis design section 1,
   "Detectable ≠ chartable"; official review, change 5).
3. **Timestamps were treated as continuous.** Official note heads sit on beat
   fractions of the declared BPM: Verrückt's 63.025 ms spacing is a sixteenth
   at 238 BPM, Eternal Override's 73–74 ms gaps are sixteenths at 204, the
   0 / 11/32 / 21/32 cells in the tap-pattern study are quantized triplets.
   Once the grid and offset are fitted, timing precision comes from the grid;
   refining peak positions by a few milliseconds solved a problem that did not
   exist, while the real errors (wrong events, missing events) stayed.

So the micro question is not "where are the attacks" but **"what rhythm does
the player play in this phrase, on which layer, at which subdivision"**. The
timestamp is derived: grid slot → beat → seconds through the SAR grid (MG1–MG4).

## 2. Calibration before trusting it

The reference material exists: 40 songs with official IN charts and matching
audio in `../overnight-study/corpus/` (plus 6 supplemental), 327 IN charts
without audio in `../arrangement-training/raw/`, and the Arcaea Eternal AFF as
same-song human timing for Override and Xterfusion. Run, per song:

1. **Grid adherence.** Share of official note heads within ±5 ms of a slot in
   the 1/4 ∪ 1/3 set of the chart's own BPM and offset. This validates
   principle 1 before anything else; expected well above 95%. Heads that fail
   are listed and listened to (tempo change, triplet, author's choice).
2. **Layer coverage.** Share of official heads that coincide with an MR1 attack
   of *some* layer (recall of the layer lines), and the share of MR1 attacks
   that are charted (how much the charts leave out, per layer). A head with no
   layer attack is a missed transcription and goes into a failure list with
   the audio excerpt.
3. **Best reading per phrase.** For each official phrase, which default
   reading (with which thinning) explains the most heads with the fewest
   extras. Tabulated by section function and difficulty, this is the **corpus
   prior**: what layer a chorus, a verse, a break is normally charted on, and
   at what density. It replaces hand-set weights and is reported as a
   distribution, not a target (roadmap step 1 wording).
4. **Sustains.** Official Hold heads versus sustain candidates: how many Holds
   start on a candidate, and how Hold length relates to the quantized note
   length. Expected: Holds are a subset of candidates with shorter lengths.
5. **Gestures.** Official Tap-and-Drag runs versus MR5 gestures: whether the
   gesture spans match the Drag spans in Verrückt-style passages.
6. **Pilot songs for the user's ear.** Override (reviewed structure record,
   Eternal timing), NightTheater (instrumental, model-free SAR) and one corpus
   song with an official IN. The user reviews two phrases per section function
   from the sheets and auditions; the record notes accepted and rejected
   readings per phrase.

Until calibration is done, readings stay `measurement-only` (XS0) or `corroborated` (XS2)
and no reading is handed to an arrangement run without the user choosing it.

Done when: steps 1–5 produce one table over the 40 songs, the failure lists
have been listened to, and the pilot phrases have the user's verdicts.

## 3. Open points for the user

Whether the user hears the pilot readings as right (section 2 step 6), and the
known issues in section 4. The third pilot is Rrharil (mid density, 190 BPM,
already in `charts/other/`); its sheets carry an official-heads row for
comparison. No `R-user` rhythm has been collected yet.

## 4. Implementation results (2026-11-08)

Calibration code is in `research-tools/phrase-rhythm/`. `calibrate.py` runs section
2 steps 1–5 over the corpus and writes `layer-latency.json`, `corpus-prior.json`,
`calibration.md`, `calibration.json` and per-song failure lists to
`artifacts/phrase-rhythm-calibration/`. `make_viewer.py` exports the pilot PRRs
and calibration to `artifacts/prr-viewer/data.js` for the listening viewer.

```
python research-tools/phrase-rhythm/calibrate.py --relatency   # all corpus songs; names as arguments select a subset
```

Records (outside the repository):

| Pilot | Folder | Notes |
| --- | --- | --- |
| Override | `charts/override/override-prr-2026-11-08/` | SAR beat zero is 28 ms late (measured on MP3 stems that lag the mix by 25 ms); auto phase fit applied; median phrase explained 82% |
| NightTheater | `charts/other/nighttheater/prr/` | Kick sits on the SAR grid, but snare, hat and the other stem sit ~45 ms after the sixteenths (near a third of a beat: possibly a shuffle that the ±1/48 triplet window misses). Not auto-shifted (ambiguous); needs listening |
| Rrharil | `charts/other/rrharil-prr-2026-11-08/` | Grid from the official IN chart; sheets show the official heads as a `chart` row |

### Calibration results (43 songs: 38 corpus IN charts with audio, 5 supplemental)

Full table: `artifacts/phrase-rhythm-calibration/calibration.md`.

- **Detector latency.** With onset-first drums, kick/snare/hat onsets sit
  −0.2/−1.5/−1.6 ms from official heads (IQR within ±3 ms over songs); Basic
  Pitch lags by +7 (vocals), +5 (bass), +2 ms (other). The drum timing problem
  is solved; the remaining timing errors are SAR beat-zero errors, which
  `grid_check` now reports.
- **Step 1, grid adherence.** 91% of official heads within ±5 ms of a 1/4 or
  1/3 beat slot (median 94%); 97.7% (median 99.7%) with 1/8 and 1/6. Principle
  1 holds once 32nds and sextuplets are allowed. Low songs: multi-BPM charts
  (Aleph0, Chronostasis) and Chronos Collapse.
- **Step 2, layer coverage.** 69% of head times coincide with an attack of some
  layer (range 35–86%); 5% of heads fall off the phrase's slot set. Charted
  share of attacks: snare 64%, hat 52%, other 45%, bass 39%, kick 36%,
  vocals 24%.
- **Step 3, readings.** Mean F1 of each default reading against the heads at
  thinning level 0: R-lead 0.25, R-lead+kick 0.33, R-drums 0.40, R-dense 0.48.
  The best reading and thinning level per phrase reach F1 0.51 (low energy),
  0.57 (mid) and 0.58 (high). Best readings are almost always R-dense or
  R-drums; R-lead wins only in quiet phrases. Head density per phrase (the
  corpus prior): low 0.7–5.7, mid 4.7–8.5, high 6.4–10.1 hits/s (p25–p75).
- **Step 4, sustains.** Only 13% of official Holds start on an MR6 candidate
  (30% on any pitched attack); where they do, Hold length ≈ candidate length
  (median ratio 0.87).
- **Step 5, gestures.** 7% of official Drag runs match an MR5 gesture span;
  28% of pitched gestures are fully charted.

### What the numbers say

1. The grid-first principle is right (98% adherence) and the timing problem is
   gone. The bottleneck is now **transcription of the layers**: a third of the
   official heads have no attack in any layer line, and the lead lines
   (Basic Pitch on Demucs vocals/other) match charts worst. Official IN charts
   follow a composite of layers that R-dense only approximates.
2. **Slot-set escalation is still too eager**: 68% of corpus phrases add
   sextuplets and/or 32nds, while the charts themselves are 91% on sixteenths
   and triplets. Every extra slot shrinks the tolerance and inflates off-grid
   counts. Next step: decide the slot set per section (more onsets) or by a
   likelihood comparison, not per 4-bar phrase.
3. Holds and Drag runs are poorly predicted by MR6/MR5 as defined; the corpus
   says Holds start on pitched attacks only 30% of the time, so the hold
   source is probably not the lead's held notes alone (pads, vocals on other
   stems, sustained synths).
4. These are corpus averages against IN charts, which are denser than any
   single layer. They are not the user's ear: the pilot sheets and auditions
   are the acceptance gate (section 2 step 6). No reading is user-confirmed.

## 5. Why rules changed during implementation

The rule numbers refer to the framework prompt.

- **Rule 1, triplet test.** A 5% share fired on every phrase of the pilots.
  Detector onsets are scattered, and uniformly scattered onsets put about a
  third of themselves near a triplet slot. The control test asks whether the
  extra slots attract more onsets than chance.
- **Rule 2, layer presence.** Without it, a silent bar's noise would pass the
  relative threshold.
- **Rule 2a, phase alignment.** Added because both pilot SARs measured beat zero
  on unaligned MP3 stems.
- **Rule 3, drum onsets only.** Sung onsets are loose and flagged nearly every
  vocal bar.
- **Rule 5, drum labelling.** Band envelopes of the drum stem put the snare on
  every hat and timed the kick by its late sub-bass. The v5 monophonic lead
  decoder is used because the user judged it a real improvement in melody
  coverage.
- **Rule 7, accent level.** `X` versus `x` is detector strength noise.
- **Rule 8, sustain length.** "≥ 1 slot" made every legato eighth a sustain.
- **Rule 11, `R-lead+kick`.** "Snare where the lead rests" broke rule 13.
- **Rule 16, energy tercile.** The corpus songs have no SAR, so section function
  is unknown there, while energy tercile is measured the same way on every song.
  Function keys can follow once corpus songs have SARs.
