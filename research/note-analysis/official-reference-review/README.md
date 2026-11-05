# Official-chart timing and selection review

## Current conclusion — the first analyzer is rejected

2026-11-02. The user rejected the Override visualization as musically terrible.
They initially described an unnamed line as broad candidate-time guidance, then
withdrew it because the editor may have been closed without saving and they were
uncertain about it. Do not recover, invent, score against or reconstruct that line.
No new chart edits or replacement chart were requested in this review.

The existing spectral detector is not an adequate note-selection model. The
comparison below exposes over-selection, irregular timing, weak sustain
representation, and conflation of new strikes with continuous gestures. The
earlier 0.02 ms JSON-to-native timing agreement was serialization accuracy only;
it did not establish alignment with intended musical attacks or good charting.

## Actual work and provenance

- Ran the unchanged current `analyze.extract/structure/decide` implementation on
  complete cached audio for Verrückt IN, Retribution ~ Cycle of Redemption ~ IN,
  and Stardust:RAY IN. Default priority threshold 50 and minimum gap 45 ms.
- Compared timestamped results against the cached official-format chart files.
  Chart and audio SHA-256 hashes were checked against
  `../../overnight-study/corpus/manifest.json` before analysis.
- Also decoded Happy Ending IN's complete chart structure and compared
  Stardust:RAY IN/AT timing sets. Happy Ending's matching audio was not located in
  this study, so no audio-driven claims are made for it.
- Sources are previously downloaded community extractions of official charts,
  not newly downloaded files or verified bytes from an installed game. The
  exact paths, URLs and hashes are retained in each comparison JSON and the
  pre-existing acquisition manifests.
- No editor connection, authoring, chart replacement, source-code tuning, HTML
  generation, model training or human listening/playtest is claimed here.

Reproduce with the workspace's existing audio environment:

```sh
research/music-flow-study/.venv/bin/python research/note-analysis/official-reference-review/compare.py
```

The script verifies cached detector outputs against both the audio hash and
current analyzer source hash; it refuses stale cache results. It writes analysis
evidence only. The additional duration and quarter-offset diagnostics are stored
in the per-song comparison JSON; the main runner produces the base comparisons.

## Whole-song result

Each official playable object is counted once at its head. Simultaneous
Tap/Hold heads are deduplicated for the fresh-time column. Drag is a contact
continuation; Flick's fresh-hit versus continued-contact intent is not inferred
from type alone. No hold scoring ticks are converted into attacks.

| Reference | Official Tap / Hold / Drag / Flick objects | Distinct Tap/Hold head times | Detector selected Tap / Hold |
| --- | --- | ---: | --- |
| Verrückt IN | 837 / 50 / 398 / 0 | 803 | 1497 / 1 |
| Cycle of Redemption IN | 637 / 251 / 485 / 129 | 685 | 2156 / 6 |
| Stardust:RAY IN | 609 / 250 / 434 / 99 | 790 | 1871 / 6 |

These are different representations, not a target note-count prescription.
The significant problem is apparent in concrete phrases: sustained or connected
parts repeatedly become independent attacks, while some uniform attack runs
lose their intended temporal shape.

## Concrete temporal examples

### Cycle of Redemption: retain a phrase, including its space

Between 11.066667 and 12.8 seconds, the reference has a Tap at the first time,
then two simultaneous Hold heads at 12.8 seconds. The analyzer inserts many
additional attacks between them: 11.1978, 11.3197, 11.4126, 11.4881, 11.5403,
11.6158, and so on. This is a different rhythmic reading, not higher timing
precision. A detectable sound is insufficient justification for a new strike.

Across 12–16 seconds, the reference uses 3 Hold objects at 2 distinct head times,
1 Flick and 15 Drags. The detector produces 54 selected attacks and no Holds.
The reference's held-contact coverage within this window totals 5.333 contact
seconds across overlapping holds. Continued motion and simultaneous voices
cannot be represented faithfully by a stream of peak-triggered taps.

### Verrückt: gesture continuation differs from repeated fresh hits

The reference's passage begins:

| Seconds | Object |
| ---: | --- |
| 43.613445 | Tap |
| 43.676471 | Drag |
| 43.739496 | Drag |
| 43.802521 | Drag |
| 43.865546 | Tap |
| 43.928571 | Drag |
| 43.991597 | Drag |
| 44.054622 | Drag |
| 44.117647 | Tap |

The 63.025 ms object spacing describes a connected gesture with periodic new
strikes. It does not mean every object is a separate screen hit.

In a different passage, 49.411765–50.357143 seconds, the reference actually uses
16 consecutive Tap objects at approximately 63.025 ms spacing. The current
detector selects only 14 events in the 49.4–50.4 window, at uneven intervals.
It both overfills some phrases and breaks others. Raising a single threshold
cannot address both failures.

### Short Holds are normal in these references

| Reference | Holds shorter than current 300 ms gate | Median Hold duration |
| --- | ---: | ---: |
| Verrückt IN | 39 / 50 | 126.05 ms |
| Cycle IN | 218 / 251 | 133.33 ms |
| Stardust:RAY IN | 199 / 250 | 182.93 ms |

The current tonal-ridge/300 ms rule excludes a large fraction of these authored
articulations by construction. Removing the gate alone would still not infer
good Hold intent or duration. Hold choice needs phrase/articulation context,
not merely a stable dominant spectral pitch.

### Happy Ending: local contrast cannot be inferred from a global density target

The chart has 114 objects in 60–70 seconds: 73 Taps, 6 Holds, 24 Drags and 11
Flicks. In 80–90 seconds it has only four Hold heads, at 87.671233, 88.767123,
89.315068 and 89.863014 seconds. There are no earlier Holds crossing into that
window. This proves strong authored temporal contrast; without matching audio
here it does not establish the exact sound/phrase reason for the contrast.

### Stardust:RAY: higher difficulty does not mean a strict timestamp superset

IN has 790 distinct Tap/Hold head times, AT has 854. With a one-to-one 1 ms
comparison, 661 are shared, 129 are IN-only and 193 are AT-only. Including every
object type gives 1,181 distinct IN head times versus 1,138 AT head times despite
AT containing more individual objects (1,570 versus 1,392).

Different multiplicities, gestures and sustained representations matter. An
unmatched head is not necessarily an unrepresented sound. Reference timestamps
should be examples of conditional authored decisions, not one universal label set.

## Timing diagnostics and their limits

Comparisons use per-line official BPM and declared chart offset. Matching
deduplicates timestamps and uses ordered one-to-one pairing at ±20/35/50 ms;
one detector event cannot match several reference events. Full results are in
`summary.json` and `*-comparison.json`.

At ±20 ms, current selected events cover 36.7% of Verrückt's distinct Tap/Hold
times, 49.9% of Cycle's, and 40.9% of Stardust:RAY's. At ±35 ms those rise to
75.6%, 92.0%, and 88.2%. Dense output and widened windows can inflate apparent
coverage. These numbers diagnose agreement, not aesthetic quality or definitive
correctness of individual choices.

An exploratory global shift scan favors adding 38 ms to Verrückt's detector
times, 18 ms to Cycle's and 20 ms to Stardust:RAY's at a 20 ms matching window.
Quarter-wise optima vary: Verrückt 34/40/32/38 ms; Cycle 22/18/26/16 ms;
Stardust:RAY 22/20/20/20 ms. This suggests a timing-calibration problem worth
investigating, but beat aliases and dense candidates remain confounders. No
source chart, project offset, analysis timing or musical grid was adjusted.

## Changes required before proposing another automatic chart

1. Separate candidate musical events from selection. Candidate evidence should
   retain onset, sustain, pitch/articulation changes and uncertainty. A missing
   chosen note is not automatically a missing sound, and a peak is not a decision.
2. Make rhythmic phrase hypotheses explicit. Repeated cells and their entry,
   continuation and release must have a coherent rhythm; do not let independent
   frequency-band peaks determine every next note time.
3. Distinguish fresh strike, continued contact, sustain and deliberate omission.
   The current mostly-Tap output does not represent these alternatives adequately.
4. Use references as conditional examples across phrases and difficulties.
   Compare both chosen and unchosen events, preserve multiple plausible readings,
   and reserve whole songs/phrases for validation rather than tuning on every example.
5. Keep intensity independent of eligibility. A weak sound may complete a key
   rhythmic motif; a loud texture may remain unplayed. Hand-picked score weights
   are not a learned or validated musical selection policy.
6. Before expanding a replacement, inspect a short song-specific passage in
   the live editor with the user. Structural validation and accurate file
   conversion are prerequisites, not approval of musical choices.

This review establishes failure cases and reference constraints. It does not
claim that the replacement musical model has been implemented or proven.
