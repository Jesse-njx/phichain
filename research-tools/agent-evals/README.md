# Agent evaluation: judgement layers

Judges chart-authoring subagents by their output. The layers do not depend on which model
wrote the chart. The planned test subject is Sonnet 5.5 summoned from Claude Code by Opus 5.5;
the agent runner is not built yet.

| Layer | Question | Can it stop a chart? | Can it pass a chart? |
| --- | --- | --- | --- |
| L0 validity | Is it a valid, physically possible chart? | Yes | No |
| L1 detectors | What are its measured properties against official charts? | Only through a gate in `judge/gates.json`. There are none today. | No |
| L2 blind review | What does the user think, without knowing the source? | Yes | Yes, the only layer that can |

There is no quality score and no automatic revision loop. This follows `prompts/charting/rules.md`:
measured rates are reference distributions, and manual user review is the quality gate.

## Commands

Run from `research-tools/agent-evals/judge/`. Python standard library and ffmpeg only.

```bash
python3 judge.py CHART.json --start 129.315 --end 142.466 --max-fingers 2 --axes hand,line,approach --out report.json
```

```bash
python3 l2_review.py build SESSION/manifest.json SESSION
```

```bash
python3 l2_review.py ingest SESSION ratings.json
```

```bash
python3 build_bands.py
```

```bash
python3 calibrate_l0.py
```

```bash
python3 ../backtest/backtest.py
```

Tests, from the repository root:

```bash
python3 -m unittest discover -s research-tools/agent-evals/tests
```

`judge.py` outcomes are `invalid`, `stopped` or `review`. `review` means "send to L2", not approval.
Metrics outside the official p05 to p95 band are printed as review prompts. Use `--axes` to exclude
what a study does not test: a silent static study should use `--axes hand,approach`.

## L0

Every error rule must pass all 327 official IN charts (`bands/l0-corpus.json`). Official charts contain
duplicates, up to 9 simultaneous obligations and a few heads on lines parked off screen, so those are
warnings or limits a brief must state. Overlapping or reversed events are errors for native output only.

L0 does not check whether notes match audio onsets; that needs a song's timing ledger.

## L1

Motion windows reproduce `research/judgment-line-study/cadence.py`. A test confirms the numbers recorded
for Override and that one chart measures the same in native and exported form.

The main hand measure is `required_move_*`: the least travel any two-finger route needs, found by
search. It separates what simple note distance cannot: run02's consecutive notes are far apart, but its
hands can almost rest, because each hand stays in its own lane. It is a two-finger lower bound. It does
not describe multi-finger play or say that more movement is better.

### What L1 cannot see

Whether the choreography suits the music, whether motion looks noisy or stiff, whether notes visibly
belong to their line, sideways note approach, late release before a same-finger hit, and anything needing
audio. These caused many recorded rejections.

## L2

`build` cuts each clip to a re-encoded anonymous file, shuffles them and writes the page to `review/`.
Existing renders burn captions such as "Official IN reference" into the frame, and the progress bar, combo
and score reveal a full-song slice, so `build` masks those areas. Anything passing under a mask is hidden too, and renders with other caption placement
would still leak: check one frame of each clip first. Identities are only in `sealed/key.json`. Do not open that before rating. Ratings stay in the browser
until you press Download ratings.

Each session needs an `anchor_official` and an `anchor_rejected` clip. `ingest` marks a session
uncalibrated, and writes no labels, unless the official anchor outscores the rejected one. Calibrated
sessions with a `chart` field on their clips add labels to `backtest/labels.d/`. Blinding is imperfect:
you may recognize a song, a chart you have seen or official polish.

## Gates

`backtest/backtest.py` tests hypotheses written before the labelled charts were evaluated. A hypothesis
becomes a gate only if a threshold rejects no user-passed chart, is no stricter than the official band
edge, catches at least half the failed charts on that axis, and has at least three failed charts. The
three-chart rule was added after the first run, which would otherwise have made a gate from one chart.

### Current result: no gates

| Finding | Evidence |
| --- | --- |
| Best signal, but too little data | `required_move_under50_pct`: run02 90.6 sits outside the official p95 of 66.7, but a chart rated acceptable has 86.4 and run02 is the only explicit hand failure |
| Line metrics catch absence only | Rejected Iris and run03 both show 100% motion; run03 was rejected as too noisy |
| Before and after C differ clearly | `bg_two_plus_lines_moving_pct` goes 0 to 91.3, but one approved chart cannot set a threshold |
| No slow-approach gate possible | No chart in the labels has a recorded pass on approach speed |

Limits of this evidence: few labels, full-song verdicts applied to a 13-second slice, and labels
copied from records rather than collected blind. Expect these results to change as L2 sessions add labels.

## Layout

| Path | Contents |
| --- | --- |
| `judge/` | Layers, band builders, `gates.json` |
| `bands/` | Official IN distributions and L0 corpus check |
| `backtest/` | Labels from existing records, hypotheses, results; `labels.d/` for L2 labels |
| `sessions/` | L2 review sessions |
| `tests/` | Regression and behaviour tests |

## Benchmark

`benchmark/benchmark.py` runs L0 and L1 on AI-written charts and official IN charts. See `benchmark/summary.md`
for tables and `benchmark/results.json` for every metric. It uses official IN at constant 15+ as the comparison group.
