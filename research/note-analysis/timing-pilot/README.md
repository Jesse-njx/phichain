# Chart-supervised audio timing pilot

Current state: completed on 2026-11-02. This is an isolated feasibility experiment,
not a replacement for the music analyzer or a trained chart generator. No chart,
editor, MCP server, arrangement-training corpus, or existing analyzer was changed.

## Outcome

The existing chart/audio pairs are usable for a small training experiment. This
particular model does **not** yet demonstrate consistently better precise timing
than a simple spectral-flux baseline. It improves broader reference coverage but
loses strict timing accuracy. Continue controlled experiments rather than deploy
the model or scale training on the strength of this result alone.

At the predeclared primary budget of 8 candidates per second, macro-average
one-to-one coverage across eight held-out songs was:

| Method | Within ±10 ms | Within ±20 ms | Within ±35 ms | Within ±50 ms |
| --- | ---: | ---: | ---: | ---: |
| Spectral-flux baseline | 67.18% | 82.00% | 86.34% | 87.46% |
| Trained MLP, seed 17 | 65.74% | 83.37% | 89.12% | 89.93% |
| Trained MLP, seed 29 | 60.28% | 81.63% | 89.21% | 90.11% |
| Random-score density control | 15.58% | 31.29% | 51.41% | 63.02% |

All main methods produced the same candidate count for each test song and budget.
Actual mean density at the primary budget was 7.996 candidates/second. Higher
density alone increases coverage; results at 4 and 12 candidates/second are also
saved. Candidate budgets are experiment controls, not recommended chart density.

The average of the two training runs improves ±20 ms coverage by only 0.50
percentage points, with improvement on 4/8 songs. At ±35 ms it improves by 2.83
points, with improvement on 7/8 songs. Averaging run metrics is not an ensemble.
At ±10 ms the average change is -4.17 points.

The exploratory song bootstrap interval for the ±20 ms difference is
[-1.60, +2.59] percentage points; for ±35 ms it is [+1.29, +4.30]. These intervals
are conditional on just eight songs and two fitted models, not a claim about the
full music population. The random control makes the density effect visible; it
was added after training and did not affect model or threshold selection.

## Data and split

- Full local IN corpus at inspection: 327 charts and 300,631 objects.
- This pilot: 40 songs with provenance-recorded, locally available audio and v3
  charts. Audio and current source chart SHA-256 hashes were verified.
- A deterministic hash of song ID assigns 24 training, 8 validation and 8 test
  songs. Audio hashes and song IDs do not overlap between partitions.
- Training contains 17,122 distinct Tap/Hold head timestamps; validation 5,465;
  test 5,463. Simultaneous chart objects are collapsed to one timestamp.
- Drag checkpoints, Flicks, Hold tails, positions and line motion are not labels.
- Timing is `note.time * 60 / (32 * line.bpm) + chart.offset`, in decoded audio
  seconds. Every retained reference lies within the decoded audio duration.
- The local paired-audio collection favors difficult rhythm-game music. The
  split is song-disjoint, not composer-disjoint. This is a convenience sample.
- Some songs were inspected in earlier heuristic studies. No test labels were
  used for this run's parameter, checkpoint or offset selection; it is not a
  permanently sealed benchmark for future architecture development.

`protocol.json` records source hashes, split and fixed settings before feature
extraction or training. `dataset.json` adds durations and usable label counts.

## Model and supervision

FFmpeg decodes audio to mono at 22,050 Hz. Features use a centered 1,024-sample
STFT, 220-sample hop (9.977 ms), 32 log-mel levels and 32 positive log-mel changes.
Whole-song feature normalization is allowed because this is an offline tool.
The network sees nine neighboring frames, with a total audio receptive extent
of approximately 126 ms, including the FFT window.

The model is a 576 → 64 → 1 MLP with ReLU, 36,993 parameters, trained on CPU using
PyTorch 2.2.2. Each seed gets 40 fixed epochs, eight batches of 512 comparisons
per epoch, Adam learning rate 0.001. Training samples songs approximately
uniformly. The final epoch is used; there is no checkpoint search.

Each pair compares a chart-head frame with a nearby frame displaced by ±50,
±70, ±90 or ±110 ms. Distractors within 30 ms of another labeled head are
excluded. The loss is `softplus(-(score(head) - score(distractor)))`.

This is **weak local ranking supervision**. A displaced frame can contain a real
uncharted musical event; it is not a verified acoustic negative. No training
examples are explicitly sampled from distant uncharted sections, and chart
rests are not given silence labels. The model can still inherit chart-selection
bias, so its scores must not be described as complete acoustic-event probabilities.

## Evaluation and checks

Inference scans the audio without chart times or BPM. Peaks have a 40 ms minimum
separation and a fixed whole-song candidate cap of 4, 8 or 12 per second. The
baseline uses the mean positive log-mel change; it is a fresh, simpler baseline,
not the previously rejected analyzer's selected-note output.

One global timing shift per method is chosen solely on validation songs to
maximize ±20 ms coverage at 8 candidates/second. The search is -50 to +50 ms in
5 ms increments. Chosen shifts: baseline 0 ms; seed 17 0 ms; seed 29 -5 ms. No
per-test-song offset optimization or beat-grid snapping is performed. This
calibration criterion can favor ±20 ms at the expense of stricter tolerances.

Matching is ordered, one-to-one maximum-cardinality matching within the stated
tolerance. Reported percentages are per-song coverage averaged across songs,
not event precision, complete music recall, or chart quality. Scores at different
tolerances do not establish a distribution of true acoustic onset error.

Audit passed: script hash; disjoint song/audio identities; all labels inside
audio bounds; matching cardinality checks; identical per-song candidate counts
between main methods; zero score difference for repeated inference on a 400-frame
test slice using a different batch size. Repeatability is narrower than robustness:
gain, encoding, crop boundaries and source-separation invariance remain untested.

Neither intensity, source attribution, sustain boundaries nor climax has been
trained or evaluated. Official note timestamps alone do not supply those labels.
No human listening evaluation was performed for these predictions.

## Artifacts and reproduction

- `run.py`: inventory, feature extraction, training and evaluation.
- `audit.py`: independent post-run checks, density control and bootstrap.
- `protocol.json`, `dataset.json`: frozen run specification and source inventory.
- `results.json`, `audit.json`: aggregate and per-song results.
- `model-17.pt`, `model-29.pt`: model state dictionaries.
- `test-events-17.json`, `test-events-29.json`: audio-time candidates at 8/second.
- `features/`: audio-hash keyed cache for this exact feature implementation.
- `run.log`: progress and training results. Original run took about 33 seconds.

Run from the repository root:

```sh
research/music-flow-study/.venv/bin/python research/note-analysis/timing-pilot/run.py
research/music-flow-study/.venv/bin/python research/note-analysis/timing-pilot/audit.py
```

The feature cache belongs only to this protocol. Invalidate or version it before
changing extraction settings. Keep the original result set when trying a new
architecture. Subsequent iterations should use validation songs for selection
and reserve additional unseen songs before making a new generalization claim.

The next useful experiment is to separate event coverage from precise onset
localization, compare a temporal audio model with this strong simple baseline,
and inspect ambiguous chart/audio alignment on a small validation sample. Do not
use the held-out test results to retune the current run and then report them as
fresh evidence.
