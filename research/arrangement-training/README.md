# Phigros IN arrangement corpus

This ignored local directory holds original chart data for a proposed small,
two-finger note-arrangement model. Preprocessing and an initial masked Transformer
training run are executed on the user's Mac mini. No live editor state is changed.

## Verified snapshot

Acquired on 2026-11-02. Source metadata reports game version **4.0.1.2**;
both source branches were last committed on 2026-10-23.

| Measure | Result |
| --- | ---: |
| Songs covered | 327 |
| Retained IN files, one per song | 327 |
| Notes across all retained files | 300,631 |
| Notes in one primary (`.0`) variant per song | 300,631 |
| Raw JSON bytes | 1,317,476,145 |
| Tap / Drag / Hold / Flick | 171,957 / 75,370 / 32,250 / 21,054 |
| Format v3 / v1 files | 322 / 5 |
| Missing catalog songs or source IN files | 0 |

The source initially supplied 333 files and 305,059 notes. At the user's request,
Random variants `.1` through `.6` (4,428 notes) were removed; `.0` is retained.
These were alternate variants, not byte-identical files. Their source identities
and checksums remain in `provenance/excluded-charts.json`; future acquisition
honors these exclusions instead of restoring the removed charts.

All retained Git blob hashes and independently reread SHA-256 hashes match. No files
are byte-identical. Source charts omit the optional root `numOfNotes` field, so
totals above count actual note objects. Format v1 files are Burn, Next Time,
Rubbish Sorting, mechanted, and Mopemope; their geometry needs the appropriate
version decoder during later preprocessing.

## Acquisition

For ordinary chart reference work, read `manifest.json` and the original files
under `raw/` directly. This local collection is the default IN reference source;
the websites and download script below document acquisition and reproduction,
not a prerequisite for using the charts. Keep the originals unchanged and use
the editor workflow in `prompts/charting/rules.md` for requested chart edits.

The public Swordalt chart downloader reads assets from
<https://github.com/7aGiven/Phigros_Resource>. Its resource URL implementation was
inspected at Swordalt commit `1b3c451c75157e4d99b711063ab420a2dca0defd`.
The chart files can be retrieved directly without browser exports, login,
audio, illustrations, or download-notification calls. Ordinary hosting rate
limits can still apply; the absence of a website login is not a guarantee of
unlimited requests.

`acquire_in.py` pins the chart and metadata commits in
`provenance/source-lock.json`, inventories the complete chart tree, downloads
one compressed source snapshot, and extracts only non-excluded paths ending in `/IN.json`.
The temporary transport archive contains other difficulties but is deleted
after successful validation; no AT files are retained in the corpus.

Every retained file is the original, unmodified JSON. Validation checks its
byte size and Git blob SHA-1 against the pinned tree, computes SHA-256, parses
the JSON, and counts actual notes. The acquisition compares the resulting
inventory against the difficulty catalog. This verifies completeness relative
to this community repository snapshot, not every historical or future game
release. Availability of the files is not evidence of a model-training or
redistribution license.

- `raw/<source-chart-id>/IN.json`: original chart bytes.
- `manifest.json`: per-file source, checksum, metadata, note counts, and format.
- `summary.json`: totals, source version, and coverage discrepancies.
- `provenance/`: immutable source revisions, tree inventory, and song metadata.
- `verification.json`: independent local integrity and grouping audit.

To resume or reproduce this pinned acquisition:

```sh
python3 research/arrangement-training/acquire_in.py
```

## Preprocessing v1

The user's proposed representation keeps notes approaching from above within
20 degrees of vertical, then projects their screen-space judgment x positions
onto one horizontal judgment line. Timing is preserved. AT is excluded for the
initial two-finger model.

`preprocess.py` implements the following explicit interpretation:

- Decode format v1 packed movement coordinates and v3 x/y events; convert each
  line's clock with `seconds = raw_time * 1.875 / line_bpm + chart_offset`.
- Use 16:9 screen geometry and the simulator-compatible lateral scale 0.05625
  screen widths per source x unit. Evaluate line translation and rotation at
  the judgment instant. Keep screen-space x, type, duration, and original time.
- Filter the oriented approach normal to +/-20 degrees from upward, accounting
  for note side and effective scroll direction. Check six evenly spaced samples
  in the final 250 ms, plus rotation/speed event boundaries. Reject zero approach
  speed. This describes the carrier's approach axis; it does not certify the
  full rendered trajectory when line translation contributes additional motion.
- Preserve all original note identities and exclusion reasons in the audit.
  Screen-off contacts are excluded from the merged output. Moving holds whose
  x changes by over 1/128 screen width are excluded from training because a
  stationary single-line hold cannot express them faithfully.
- Break training runs at ineligible simultaneous groups and pauses over 2.5 s.
  Never stitch over missing notes. Screen out clear contact-count overloads and
  projected tap collisions using conservative heuristics, not a fingering oracle.
- Build 16-128-note windows spanning at most 12 seconds, roughly 48 notes apart.
  Do not cut simultaneous groups or enter/exit a window through an active hold.
- Split by song with fixed seed 20261102: 261 train, 33 validation, 33 test.
  Mirroring and simultaneous-note permutation happen in the training split only.

Measured results:

| Stage | Notes / windows |
| --- | ---: |
| Raw | 300,631 notes |
| Angle and nonzero-speed eligible | 261,018 notes |
| Merged, on-screen | 260,645 notes |
| Representation eligible (including stationary-hold check) | 256,805 notes |
| Unique notes covered by complete windows | 181,944 notes |
| Complete windows, including overlapping windows | 4,080 |
| Train / validation / test windows | 3,233 / 486 / 361 |

All windows were independently checked against the full source timeline for
interior-note completeness, no cut holds, and consistent song-level splits.
Overlapping windows contain 265,869 note occurrences; this is not the count of
independent notes. Geometry unit tests cover angles, side inversion, legacy
decoding, per-line BPM, offsets, moving holds, and broken phrases.

Limitations and future checks:

- A line's angle at the hit instant alone does not prove the note approached
  from above. Moving/rotating lines and speed events require an explicit
  approach interval and direction rule. The v1 filter checks the oriented normal
  over the stated interval, not the derivative of the final rendered trajectory.
- Projecting different y positions to one line can merge contacts or change
  movement. Audit collisions and gesture feasibility after projection.
- IN labels alone do not certify two-finger feasibility. Simultaneous object
  count alone is also not a finger count, particularly for drags and holds.
- Keep all versions of a song in one dataset split if variants are added later.
  Only the `.0` `Random.SobremSilentroom` IN variant is currently retained.
- Report usable complete windows and retained notes after filtering. Raw note
  counts and overlapping windows are not independent training examples and do
  not establish whether a trained model will generalize.

## Remote training

Host: `ssh macmini`; Apple M4, 32 GB unified memory.
Directory: `/Users/jessebot/Projects/phichain-arrangement-training`.
An isolated Python 3.11 virtual environment uses PyTorch 2.8.0 and NumPy 2.2.6.
MPS availability and actual GPU forward/backward execution were verified. VPN
connectivity checks reached Google (204), GitHub raw files, PyPI and Hugging Face
(200); no VPN settings were changed.

`masked_model.py` defines a four-layer, width-192, six-head bidirectional
Transformer with a 768-wide feedforward network. It predicts 128 discrete x
positions conditioned on timing features, note type, hold duration, difficulty,
and any visible x positions. No audio or pretrained language model is used.
The v1 model generates positions only; it does not change timing or note types.

`train.py` mixes full masks, random masks, and contiguous masks. Training uses
mirror augmentation, AdamW, gradient clipping, warmup/cosine decay, a maximum
of 3,000 steps, and validation-based early stopping/checkpoint selection. The
test split is evaluated only after selecting the checkpoint. A smoothed
per-note-type position-frequency baseline is reported; this is not a retrieval
baseline or a human preference benchmark.

Model checks verify no target-x leakage through fully masked inputs, correct
mirror/padding behavior, GPU backpropagation, and preservation of locked notes
during iterative generation. `runs/masked-v1/` contains config, history,
checkpoints, status, and held-out candidate samples when the run finishes.

```sh
# Run these commands inside the remote training directory.
.venv/bin/python -m unittest test_preprocess test_model
.venv/bin/python preprocess.py
.venv/bin/python train.py --steps 3000 --batch-size 32 --run masked-v1
```

Research output is not yet a validated two-finger arrangement tool. Held-out
loss improvement alone does not establish coherent movement or enjoyable play.

The inference CLI is `arrange.py`. A request contains `bpm`, optional numeric
`difficulty`, and 16-128 chronological `notes` with `time`, `type` (1 Tap, 2 Drag,
3 Hold, 4 Flick), and `duration` in seconds. Optional `locked` maps zero-based
note indices to normalized x values. Windows must span at most 12 seconds and
end after all holds complete. Locked x values are quantized to the 128-position
grid. Output contains several candidate x arrangements with unchanged timing,
types, and durations; it does not apply edits to an editor.

```sh
.venv/bin/python arrange.py request.json --output candidates.json --candidates 4
```

The first measured training throughput on the M4 was approximately 0.095 seconds
per step at batch size 32, implying roughly five minutes for the initial 3,000-step
run with validation, substantially less than the earlier unbenchmarked estimate.

## Initial model result

`masked-v1` completed 3,000 steps. It contains 1,858,688 parameters; validation
selected step 3,000. Training plus validation took 272.39 seconds (4 min 32 s),
excluding setup, preprocessing, and final held-out sampling.

| Held-out test metric (lower is better) | Model | Type-frequency baseline |
| --- | ---: | ---: |
| All x positions masked: cross-entropy | 4.1975 | 4.2480 |
| Approximately half the x positions masked: cross-entropy | 3.0040 | 4.2471 |

This indicates useful conditional completion behavior, with only a small
improvement in the fully masked one-pass prediction task. One-pass marginal
prediction is not a direct measurement of iterative generation quality.

Generation audit: 36 unfiltered candidates across 12 held-out windows; **24/36**
triggered a simultaneous Tap proximity screen (two tap centers less than 2/128
screen width apart). That threshold is a conservative research screen, not the
official game's judgment tolerance. This is an unresolved failure, not a
successful playability result. The first model is **not ready to serve as a
reliable automatic arrangement tool**. Joint simultaneous-note constraints and
generation-quality evaluation require further work; no human playtest has
validated these candidates.

The finished `result.json`, `history.json`, `heldout-generations.json`, and
`best.pt` preserve this baseline for comparison. They should not be relabeled as
a quality-approved or two-finger-certified model.
