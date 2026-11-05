# Fixed-candidate timing refinement — experiment 2

Current state: completed on 2026-11-02. **Keep quadratic peak interpolation as
the experimental timing baseline; reject the two CNN refiners from adoption.**
This task did not edit charts, the editor/MCP, the arrangement dataset, or the
existing music-analysis CLI. The first experiment remains unchanged.

## What changed and why

The previous model mixed event selection with timing. This experiment freezes
the candidate events first and moves only their timestamps. Every method sees
the exact same candidates, in the same order, with no insertions or deletions.
Corrections are bounded to 25 ms and cannot cross the midpoint between original
neighboring candidates. Candidate discovery remains the previous spectral-flux
baseline, capped at 8 events/second for this controlled experiment.

Compare five methods:

1. Original peak timestamps.
2. One validation-selected global offset.
3. Quadratic interpolation using each spectral peak and its two neighboring
   frames, plus a validation-selected global offset.
4. A small temporal CNN predicting an audio-dependent local correction, seed 17.
5. The same CNN trained with seed 29.

## Main result

These are macro-average one-to-one **chart-head coverage** percentages. They
are not acoustic precision, complete sound recall, or human listening ratings.

| Partition / method | Within ±5 ms | Within ±10 ms | Within ±20 ms | Within ±35 ms |
| --- | ---: | ---: | ---: | ---: |
| Previous test songs, raw | 44.78% | 67.18% | 82.00% | 86.34% |
| Previous test songs, interpolation | 49.51% | **69.13%** | 81.66% | 86.43% |
| Six fresh songs, raw | 60.36% | 83.62% | 95.50% | 97.61% |
| Six fresh songs, interpolation | **69.22%** | **85.76%** | 95.58% | 97.64% |
| Six fresh songs, CNN seed 17 | 22.35% | 74.69% | 95.64% | 97.62% |
| Six fresh songs, CNN seed 29 | 23.02% | 74.92% | 95.77% | 97.62% |

Interpolation already beats both CNNs on the **validation** primary metric:
67.18% versus 66.81% and 66.48% at ±10 ms. This choice does not depend on fresh
test results. Its selected global shift is zero. The global-offset-only method
selects -2.5 ms, and both CNNs select full correction strength plus -5 ms.

On the six fresh songs, interpolation improves ±10 ms coverage on all six, by
2.15 percentage points on average. The exploratory song-bootstrap interval is
[+0.86, +3.52] points. Six songs are a small sample; this is not a broad claim of
generalization. The fresh songs also have higher baseline coverage than the old
test songs: compare methods within each partition, not raw scores across them.

There is a small tradeoff on the old test set: ±20 ms coverage falls by 0.34
points. Broader ±35 ms coverage changes by +0.09 points on the old set and +0.03
points on the fresh set. Candidate count itself cannot change in this experiment.

## Localization independently of rediscovery

Before correction, mutually nearest chart-head/candidate pairs within 35 ms
are assigned permanent identities for the localization diagnostic. We do not
rematch these pairs after moving events.

On fresh songs, the mean of per-song median absolute chart-alignment errors
falls from **4.52 to 3.73 ms**; the mean of per-song 90th percentiles falls from
**10.00 to 8.22 ms**. These errors describe only the fixed matched subset, not
every candidate or all musical events. All-reference coverage is reported above.

An unresolved exception is **Shadow**: its ±10 ms coverage improves from 42.64%
to 46.94%, while ±20 ms coverage is 91.40%. The aggregate therefore does not
establish reliable sub-10-ms alignment on every song. We have not diagnosed
whether that discrepancy comes from audio attacks, chart offsets, source-version
alignment, or another factor. No test-song-specific retiming was applied.

## Data and frozen evaluation

- Reuse the original 24 training songs and 8 validation songs.
- The previous 8 test songs are now explicitly a regression set.
- Reserve all 6 locally available supplemental audio tracks outside the original
  40-song pilot as fresh tests: Horizon Blue, Shadow, FULi AUTO BUSTER,
  FULi AUTO SHOOTER, Cleyera, and NO ONE YES MAN.
- Use the current original IN charts from the verified arrangement corpus,
  including **IN** for Shadow even though its older supplemental chart was AT.
  All audio/chart hashes are recorded and checked. Identical audio hashes and
  song IDs cannot cross partitions.
- Fresh tests contain 3,114 unique Tap/Hold head timestamps. Their chart labels
  are not loaded into evaluation until `selection.json` has been written.
- Audio filenames and hashes establish source identity, not independent proof
  that each chart onset is the true acoustic onset for that audio version.

The run writes `protocol.json` before extraction/training. It records the source
inventory, settings, and script hashes. No architecture, checkpoint, or parameter
was changed after observing fresh-test results.

## CNN training

There are 14,807 mutually nearest training candidate/head pairs within 25 ms.
Only those pairs provide offset targets. Unmatched candidates and chart rests
receive no silence/negative label. This is weak chart-alignment supervision;
some matches can still join a chart object to a different acoustic event.

Features use 22,050 Hz mono audio, a 110-sample hop (4.989 ms), 512- and
1,024-sample FFTs, and 32 log-mel levels plus positive changes at each resolution.
Each candidate receives 33 frames of context. The network uses two temporal
convolutions, a small dense head, and tanh-bounded offset regression: 40,049
parameters. Train each seed for 30 fixed epochs, 8 batches of 256 examples per
epoch, Adam at 0.001, smooth L1 loss with a 5 ms transition. Use the final epoch.

On validation only, search correction strength in [0, 0.25, 0.5, 1] and a global
offset from -10 to +10 ms in 2.5 ms increments. Maximize ±10 ms coverage while
allowing no more than a 0.5-point drop at ±35 ms. The same offset search applies
to the simple controls. Both trained models perform worse on fresh strict-timing
tests; this does not establish that all neural approaches will fail.

## Stability and audit

Passed checks:

- Source script hashes, identical candidate identities/counts across methods,
  strict ordering, midpoint guards, and the 25 ms movement bound.
- Repeated inference produces exactly identical results for both CNNs and the
  full spectral-flux/interpolation pipeline on one validation song.
- For that song, multiplying PCM amplitude by 0.5 or 2.0 preserves 1,390
  candidates; 99.78% and 99.93%, respectively, still match within 1 ms.

This is one-song gain testing, not comprehensive robustness. MP3 re-encoding,
chunk boundaries, padding, all-song gain invariance and listening quality remain
untested. The global events/second cap is an evaluation control: changes to
audio duration can alter the selected candidate set. It should not silently
become the final agent-facing discovery policy.

## Artifacts and reproduction

- `run.py`: extraction, training, validation selection and frozen evaluation.
- `audit.py`: identity checks, repeat/gain testing and bootstrap comparisons.
- `protocol.json`, `training-data.json`, `selection.json`: source inventory,
  training pair counts, hyperparameters and validation choices.
- `results.json`, `audit.json`: aggregate and per-song results.
- `events.json`: raw and corrected timestamps for every evaluated method/song;
  array index preserves candidate identity within each song.
- `selected-events.json`: agent-readable export of the validation-winning method,
  with stable per-song IDs, original times and correction amounts. These are
  analysis candidates, not selected gameplay notes.
- `refiner-17.pt`, `refiner-29.pt`: rejected experimental model weights.
- `features-v1/`, `baseline-cache/`: local feature caches; do not reuse after
  changing extraction settings. The original experiment's cache is read-only.

```sh
research/music-flow-study/.venv/bin/python research/note-analysis/timing-refinement-v2/run.py
research/music-flow-study/.venv/bin/python research/note-analysis/timing-refinement-v2/audit.py
research/music-flow-study/.venv/bin/python research/note-analysis/timing-refinement-v2/export.py
```

The original extraction/training/evaluation run took about 49 seconds on the
available CPU. Source and feature caches make later runs different in duration.
Do not replace the frozen experiment with a retuned run using the same test set
and describe it as fresh evidence.

The demonstrated improvement is a small, deterministic sub-frame timing
correction. Musical source attribution, emphasis/intensity, sustain boundaries,
climax, and complete event discovery remain separate work. No trained model is
being promoted to the production tool on the basis of these results.

## Follow-up: Shadow and quiet music

After the user identified Shadow as quiet, `diagnose_shadow.py` performed a
post-test diagnostic, saved in `shadow-diagnostic.json`. It does not modify the
frozen results, model selection, or exported candidate timestamps.

- Multiplying Shadow's decoded PCM amplitude by four without clipping changes
  neither its 1,150 candidate count nor its 46.94% coverage at ±10 ms. All
  original candidates still match within 1 ms.
- Among nearby mutually nearest pairs, detected timestamps precede chart heads
  by a median 9.93 ms. Most 15-second windows share this direction; the amount
  varies, especially near 105–120 seconds.
- The quietest quarter of chart-head neighborhoods has 74.34% ±10 ms coverage;
  the loudest quarter has 26.49%. These subsets are observational, not controlled
  comparisons of identical sounds at different levels.
- Searching shifts using this test chart finds +12 ms with 86.12% ±10 ms
  coverage. This is an **oracle diagnostic**, not a validated automatic offset
  estimator or a new benchmark result. It was not applied.
- Cleyera's whole-song median frame RMS is lower (-13.78 dBFS versus Shadow's
  -8.87 dBFS) but its timing coverage is much higher. RMS is not perceived
  loudness, musical sparsity, or attack sharpness.

The evidence points toward a timing convention/alignment or attack-shape issue
more strongly than a simple amplitude threshold problem. Its cause remains
unconfirmed. A useful next step is an independent chart/audio timebase audit
across several clear attacks and soft entrances, followed by attack-shape-aware
localization if that audit supports it. Any chart-derived correction belongs in
the label-alignment metadata, not as a hidden song-specific inference rule.
