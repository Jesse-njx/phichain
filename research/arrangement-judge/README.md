# Arrangement judge dataset

Pure-arrangement data for a planned Transformer judge that scores note arrangements.
There is no model yet; this directory only prepares and verifies the data. Negative
samples are not designed yet.

## Scope

- Official IN and AT charts of songs released on or after 2024-01-01: 123 songs,
  123 IN and 31 AT charts.
- Release dates come from the Moegirl Phigros song list (page state 4.0.1,
  2026-10-02), read in a browser on 2026-11-06. They are in
  `provenance/release-dates.json`, which covers every song from 2023-01-01 on, so
  `--since 2023-01-01` (165 songs, 37 AT) needs no new lookup. A song added to a
  chapter later, or first released as a single, is dated by its earliest release.
  The page has no AT dates: AT charts are dated by their song, so an AT added to an
  older song after 2023 is not included.
- Source: the pinned snapshot from `../arrangement-training` (game version
  4.0.1.2). IN files are reused from that corpus after a SHA-256 check. AT files
  are fetched from the same pinned commit into `raw/` and checked against the
  pinned Git blob hashes.
- The music analysis tool and audio are not used.

## Representation

Charts are flattened with `flatten()` from `agent-tools/pure-configuration/convert.py`,
the pure-configuration converter used for the QQ bot. It keeps every note: each
note's horizontal judgment position at its head time (line translation and
rotation included) goes onto one static horizontal line. Line performance, y,
below-side approach and variable scroll are removed. Holds stay at their head x.

Each note is four numbers, `[time_s, type, x, hold_s]`:

| Field | Meaning |
| --- | --- |
| `time_s` | Seconds from the window start (absolute seconds in per-chart files) |
| `type` | 1 Tap, 2 Drag, 3 Hold, 4 Flick |
| `x` | `0.5 + positionX / 18`: official units span 18 across the screen. A few heads are off screen and keep x outside 0..1 |
| `hold_s` | Hold duration; 0 for other types |

Simultaneous notes share `time_s`. Window metadata: chart, song, level, constant,
release date, split, first-line BPM, and `max_contacts` (most simultaneous notes
plus active holds).

- No note filter and no two-finger screen. Dense chords stay in; training can filter
  on `max_contacts`. Flattening can stack notes that were vertically separated in
  the original, as the converter documents.
- Runs break only at pauses over 2.5 s. Windows hold 16 to 128 notes, span at most
  12 s, start about 48 notes apart and never cut a hold. They overlap, so window
  counts are not independent examples. Notes are missed only where those window
  limits cannot be met (long holds across boundaries, very dense or short runs).
- Song-disjoint split, seed 20261106: 99 train, 12 validation, 12 test songs. IN and
  AT of one song share a split.

## Result

| Measure | Count |
| --- | ---: |
| Notes | 164,727 |
| Unique notes in windows | 154,440 (94%) |
| Windows (train / validation / test) | 2,971 (2,424 / 313 / 234) |
| IN / AT windows | 2,253 / 718 |
| Notes with x off screen | 54 (in 25 windows) |

Windows by `max_contacts`: 1: 63, 2: 1,816, 3: 493, 4: 472, 5: 67, 6+: 60.

An earlier version used the masked-v1 geometry filter (approach within 20 degrees,
non-zero speed, stationary holds). It kept only 61% of notes and broke passages at
single slowly rotating holds, so it was replaced by the pure configuration.

`verify_dataset.py` checks the result independently, without the converter. Each
chart has exactly the original note count and note times. Each window contains
every chart note in its time span. It also checks for cut holds, sort order,
types, the release-date cutoff, AT checksums and split integrity. All checks pass
(`processed/verification.json`).

## Judge v1 (first trial, 2026-11-06)

ELECTRA-style replaced-note detection, trained locally on the M5 GPU (MPS).

- Generator: the masked-v1 architecture (1.86M parameters) retrained on this split
  (`train_generator.py`, 3,000 steps, 3.5 min). Test cross-entropy with all x masked
  is 4.31; with about half masked it is 3.20.
- Negatives: in 70% of windows, one generator pass refills 10–60% of x (random or
  contiguous). A sample within 2 bins of the original counts as unchanged. Timing,
  type and holds never change. There are no rule-based corruptions.
- Judge: a 6-layer, width-256 encoder (4.8M parameters) with a per-note "replaced"
  head and a window "official" head (`judge_model.py`, `train_judge.py`, 4,000
  steps, 8.5 min).

Test results (12 held-out songs, 234 windows):

| Measure | Result |
| --- | ---: |
| Replaced-note AUROC, mixed corruption | 0.60 |
| Clean vs corrupted window AUROC: 5% / 30% / 100% refilled | 0.52 / 0.55 / 0.69 |
| Official vs full iterative generation, window AUROC | **0.27 (inverted)** |
| Official vs 50%-locked generation, window AUROC | 0.46 |
| Mirror gap (mean absolute score change) | 0.03 |

**Not usable.** The signal is weak, and the judge ranks full iterative generations
as *more* official than real charts (mean window score 0.67 vs 0.30). It learned
the noise of single-pass, temperature-1 sampling. Iterative generation instead
collapses into stacked, low-movement arrangements, which look nothing like that
noise. So the judge learned the signature of one sampling procedure, not
arrangement quality. Validation scores were still rising at step 4,000.

## Judge v2 (2026-11-06)

Same generator and judge architecture. The negatives now include the generator's
real output procedure:

- `make_pool.py` precomputes 2 iterative generations per window (12 steps;
  temperature 0.7/0.9/1.1; 0/30/60/90% of notes locked to the official x).
  This took 2 minutes, and 48% of notes in a candidate are replaced on average.
  Test songs also get 4 held-out settings never used in training: temperature
  0.5 and 1.5, and 6 and 24 steps.
- Each training window is 40% clean, 20% one-pass refill and 40% pool. Mirroring
  is the only augmentation, applied identically to every kind; simultaneous notes
  are no longer shuffled, so their order can't become a shortcut.
- 10,000 steps took 23 minutes. Validation was selected at step 6,000 and was flat
  afterwards while training loss kept falling (overfitting on 2,424 windows).

Test window AUROC, official vs negative, next to the best single statistic
(mean |dx| between consecutive non-simultaneous notes):

| Negative | Judge v2 | Mean-movement statistic |
| --- | ---: | ---: |
| Full generation (0% locked) | 0.98 | 0.97 |
| Held-out sampling settings | 0.98–0.99 | 0.95 |
| 30% locked | 0.82 | 0.71 |
| 60% locked | 0.67 | 0.60 |
| 90% locked | 0.50 | 0.54 |
| One-pass refill of 10–60% | 0.50 | — |

The per-note replaced-detection AUROC is 0.74. The mean window score changes by
0.09 when a window is mirrored.

**Better than v1 but still not a useful judge.** v2 rejects whole generated
arrangements reliably, but a one-number statistic does nearly as well: the
generator moves too little. It cannot detect local changes. With 90% of notes
locked, or after a one-pass refill, it is at chance, and local changes are exactly
what an agent's revisions would look like. The bottleneck is the generator. Its
output is separable by simple statistics, so the judge learns those statistics
instead of arrangement structure.

## Judge v3 and generator surprise (2026-11-06)

v3 adds sparse random replacement. In 30% of training windows, 1–3 notes get a
random x bin drawn from the train-set distribution for their note type, so the
values look official, and each lands at least 2 bins from the original. The other
windows are 40% clean and 30% pool; one-pass refill is used for evaluation only.
10,000 steps took 24 minutes, and the best checkpoint was at step 4,000.

v3 keeps v2's whole-generation detection: window AUROC 0.99 at 0% locked, 0.98 on
held-out settings, 0.85 at 30% locked, 0.52 at 90% locked. Its mirror gap fell to
0.03. But it does **not** detect sparse random notes. Note AUROC is 0.52 on test
and 0.55 on training windows, and it ranks the replaced note first in 1.7% of
windows, which is chance. It fails to learn the task, not just to generalize.

The signal does exist. `pll_eval.py` scores each note by the masked generator's
surprise, -log p(x | all other notes), masking one note at a time. It needs no
negatives.

| Test (12 held-out songs) | Generator surprise | Judge v3 |
| --- | ---: | ---: |
| One random note: note AUROC | **0.86** | 0.52 |
| One random note: replaced note ranked most surprising | **33%** (chance 1.3%) | 1.7% |
| Two / three random notes: note AUROC | 0.88 / 0.86 | — |
| Window AUROC, sparse (mean surprise) | 0.52–0.55 | 0.52 |
| Full generation: window AUROC | **0.004 (inverted)** | 0.99 |

The two scores fail in opposite places. Generator surprise finds a locally wrong
note but prefers its own collapsed output to official charts. The discriminative
judge spots generator-style output but is blind to a single misplaced note.
Generator surprise also changes by 0.38 nats when a window is mirrored. "Random
note" is one specific kind of error; real agent mistakes may be more plausible and
harder to find.

## Combined judge (2026-11-06)

`combined.py` uses each signal where it works:

- **Per-note feedback**: generator surprise only. Mixing in the v3 note logit
  failed: a logistic fit on all negatives learned to invert surprise, because
  generator-made notes have *low* surprise.
- **Window flag**: two signals, each compared with official validation windows
  only. *Style* is the v3 "official" logit; *local* is the window's maximum note
  surprise. `p_*` is the share of official windows that look at least this unusual,
  and `p_combined = min(p_style, p_local)` flags a window when either is unusual.
  A linear combination was tried first. It lost generator detection (0.86) and
  was dropped.

Test window AUROC (combined / v3 alone / max surprise alone):

| Negative | Combined | v3 | Max surprise |
| --- | ---: | ---: | ---: |
| Full generation | 0.98 | 0.99 | 0.43 |
| Held-out sampling settings | 0.98 | 0.98 | 0.50 |
| 30% / 60% / 90% locked | 0.85 / 0.71 / 0.52 | 0.85 / 0.67 / 0.52 | 0.76 / 0.67 / 0.51 |
| 1 / 2 / 3 random notes | 0.59 / 0.63 / 0.65 | 0.51 / 0.53 / 0.53 | 0.63 / 0.68 / 0.72 |
| One-pass refill | 0.67 | 0.51 | 0.74 |

Per-note surprise finds random notes (note AUROC 0.87–0.89; the replaced note
ranks first in 37% of windows), but not generator-made notes (0.31–0.56).

`python3 combined.py score CHART.json --constant 15 --out report.json` scores an
official-v3 chart. It flattens and windows the chart, then reports each window's
`p_combined`, `p_style` and `p_local`, plus its most surprising notes (time, type,
x, surprise).

**Real-chart check.** I compared held-out official BRAINHACKER IN (780 notes, 14
windows) with the user-rejected AI chart Xterfusion Sol (902 notes, 19 windows).
The AI chart scored at least as official as the real one: median `p_combined`
0.40 vs 0.29, with 2 vs 1 windows below 0.05. The user rejected Xterfusion for
rhythm, line performance and Drag use, while calling its placement "somewhat
acceptable". This judge sees none of the rejected aspects, so the test is not
decisive. Still, nothing yet shows this judge separates real AI arrangements from
official ones. It needs blind-labelled AI windows before it can serve as a filter.

## Feel (手感) and per-note scores (2026-11-06)

No learned model. `player.py` simulates a player, `feel.py` counts official hand patterns,
`note_scores.py` puts every signal on every note.

**Simulated player.** A beam search (width 32) finds the cheapest finger assignment per
play style: `two` (index fingers), `four` (index + middle per hand), `free` (adds ring
fingers, 3.0 per use). Game rules from the project owner: every note's judgment region is
about 0.15 screen widths (+-0.075, measured from an in-game screenshot); tap, hold head and
flick take their own finger; a hold keeps its finger; one touching finger covers drags
within 0.15; crossing hands is free up to 0.1 screen widths. Costs: squared movement speed
beyond the judgment region, squared same-finger re-press rate, crossing, hand shape, notes
no finger can take, and a tiny near-hand preference (0.05 per screen width) so equal-cost
choices are not arbitrary. Thumbs are not modeled. Cost per second follows the chart
constant (Spearman 0.83 / 0.91 / 0.91 for two / four / free over 154 charts): the cost is a
difficulty measure, not a fault.

**Feel = hand pattern frequency given rhythm.** Each press group (tap, hold head or flick)
becomes a hand token ("L", "L+R", "L2" = two left fingers; index vs middle is a cost tie and
is dropped). Drag-only groups are left out: a sliding finger takes them and the hand is a
tie. Four consecutive press groups form a pattern, mirrored to a canonical form, counted on
the train-split charts given the rhythm: each group's press count, "h" if an earlier hold is
still held (the other hand plays alone), "d" if drags occur in or since the previous press
group (a hand may be busy sliding), and the three gaps in speed buckets. Rare rhythms back
off to kinds + rhythm shape + fastest gap, then kinds + shape, then kinds, with weight
ALPHA = 30; shape marks each gap "s" (within 1.4x of the fastest) or "l" (longer), so an
uneven rhythm is never judged by even-rhythm counts. ALPHA and the flags were chosen on
held-out test songs: official notes above the validation 95th percentile 3.5% (target 5%),
random-x notes 15.5% (9.6% without the flags).

Two-finger single-note runs at an even speed (train split, mirrors merged):

| Gap | Runs | LRLR | LRRL | LLRL | LRLL | LLRR | LLLR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| < 0.07 s | 2,823 | 88% | 4% | 2% | 2% | 2.6% | 0.4% |
| 0.07–0.1 s | 6,748 | 88% | 4% | 3% | 3% | 1.0% | 0.2% |
| 0.1–0.14 s | 1,916 | 69% | 11% | 7% | 7% | 3.9% | 0.9% |
| 0.14–0.2 s | 2,084 | 65% | 13% | 7% | 8% | 5.2% | 0.9% |
| 0.2–0.3 s | 491 | 52% | 15% | 8% | 10% | 7.9% | 3.1% |
| > 0.3 s | 544 | 54% | 9% | 9% | 8% | 5.9% | – |

Uneven density, fastest gap at most 0.1 s, by shape (s = as fast as the fastest gap,
l = longer); a longer gap resets alternation:

| Shape | Runs | LRLR | LRRL | LLRL | LRLL | LLRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| s s s | 10,351 | 89% | 4% | 3% | 3% | 1.5% |
| s s l | 1,563 | 78% | 1.5% | 4% | 16% | 0.7% |
| s l s | 1,083 | 68% | 25% | 2% | 4% | 0.5% |
| l s s | 1,577 | 78% | 5% | 15% | 1% | 0.4% |
| s l l | 639 | 65% | 17% | 1% | 15% | – |
| l s l | 411 | 36% | 1% | 21% | 20% | 22% |
| l l s | 679 | 59% | 15% | 18% | 5% | 0.9% |

Held-out test windows (12 songs; 3 of 234 windows have no press pattern), each played on
its own; `p_feel` = best of `two` and `four` against official validation windows:

| Windows | Median `p_feel` | Flagged (< 0.05) |
| --- | ---: | ---: |
| Official | 0.74 | 0% |
| Same timing, random x | 0.19 | 7% |
| Masked generator, full generation | 0.79 | 1% |

Official vs random x: AUROC 0.88. Per pattern: 0.65 for even rhythm, 0.59 for uneven
(uneven rhythm leaves more freedom). The generator's collapsed same-x output alternates
hands, so it feels fine; feel does not judge placement variety. AI studies (median
`p_feel`, none flagged): silent-180-sixteenths 0.98; four-key jack / speed / stream / tech
1.00 / 0.18 / 0.64 / 0.14; two-styles style-one / style-two 0.39 / 0.99.

**Per-note scores and rarity** (`note_scores.py`). Every note gets its finger, player cost
and feel per style (and `best` = the lower of two and four), the masked-generator placement
surprise and the window's style p. `rare_*` puts them on one scale: the share of official
notes at least this extreme. Feel and surprise are compared with the validation songs'
notes; cost with official charts within about 0.6 of the chart's constant. `python3
note_scores.py reference` rebuilds `runs/feel/note_reference.json`. Share of notes below
5% rarity (feel best / surprise): K.Moe (VIP) 6% / 5%, Cryogenic 4% / 7%, BRAIN HACKER
16% / 2%. BRAIN HACKER's fast one-hand runs (LRRR, LLLR) are rare in official charts, so
its feel is genuinely unusual, not a calibration error.

**Fault: one number for "unlike official charts".** `fault` is the more unusual of feel
(best style) and placement, re-calibrated on the validation notes (the plain minimum of two
rarities puts 8.6% of official notes below 5%; after calibration it is 5% by construction).
`fault_reason` names the signal that drove it. Player cost is not part of it: cost is
difficulty, not a mistake. Share of notes with fault below 5%: K.Moe (VIP) 5.7%, Cryogenic
5.7%, BRAIN HACKER 12.2% (mostly feel), Entrance to the Chaos 9.8% (mostly placement; a
validation song, so part of the reference); AI studies: silent-180-sixteenths 0%,
style-one 3.7%, four-key tech 6.8% (all feel).

Limits: the hand sequence is inferred, not observed; "common in official charts" is not
the same as "feels good"; no audio, so accents are unknown.

## Files

| Path | Contents |
| --- | --- |
| `build_dataset.py` | Selection, AT acquisition, flattening, runs and windows |
| `verify_dataset.py` | Independent dataset audit |
| `test_build_dataset.py` | Unit tests for flattening use, runs, windows and tokens |
| `judge_model.py`, `train_generator.py`, `train_judge.py` | Generator retraining, judge model, on-the-fly negatives, evaluation |
| `make_pool.py`, `pll_eval.py` | Iterative-generation negative pool; generator-surprise scoring |
| `combined.py` | Combined judge: fit references, evaluate, score a chart |
| `player.py`, `feel.py`, `test_player.py` | Simulated player per play style; feel (手感) pattern counts and checks; tests |
| `note_scores.py` | Every signal on every note of a chart, the official rarity scale and the fault score |
| `runs/` | Checkpoints, histories and results (ignored by Git) |
| `provenance/release-dates.json` | Song release dates from 2023 on |
| `manifest.json` | Selected charts with source path, blob hash and URL |
| `raw/` | Original AT JSON files |
| `processed/windows.json.gz` | Training windows |
| `processed/charts/` | Per chart: every note as tokens, grouped into runs |
| `processed/stats.json`, `splits.json`, `verification.json` | Totals, per-chart audit, split, checks |

JSON data is ignored by Git (`/research/**/*.json`); the scripts and this README
are tracked.

```sh
python3 research/arrangement-judge/build_dataset.py            # --since 2023-01-01 to widen
python3 research/arrangement-judge/verify_dataset.py
python3 -m unittest discover -s research/arrangement-judge
```

### Silent AI studies vs held-out official charts

`p_combined` is the minimum of two p-values, so a typical official window sits near
0.29, not 0.5. Medians over each chart's windows (full table:
`runs/combined/demo/silent-and-test-official.json`):

| Chart | User verdict | Windows | Median `p_combined` | Flagged < 0.05 |
| --- | --- | ---: | ---: | ---: |
| silent-180-sixteenths | Best AI arrangement, approved reference | 8 | 0.52 | 1 (12%) |
| silent-180-arrangement | Probably the earlier study whose movement the user found too small | 5 | 0.69 | 0 |
| silent-150 style one / two | Acceptable | 3 / 5 | 0.33 / 0.80 | 0 / 0 |
| silent-150 four-key jack / speed / stream / tech | Category studies; fixed lanes not the preferred full-chart design | 2–3 each | 0.00–0.01 | all |
| 13 held-out official charts | — | 12–24 each | 0.17–0.56 (median of charts 0.28) | 0–14% |

The approved sixteenths chart scores above 12 of the 13 official charts. The
fixed-lane four-key studies are flagged entirely by the style signal. The judge does
not catch the "movement too small" complaint about silent-180-arrangement. These are
eight short charts, which is too few to show agreement with the user.
