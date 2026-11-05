# Benchmark: AI-written charts against official IN

Comparison group: 132 official IN charts at constant 15.0+ (of 327 IN, 320 with a known constant).
Values inside the official range are not evidence of quality. No score is produced.

Base rate: an official chart itself gets 2 flags (whole, median), 1 (13 s slice, median).

## Whole songs: what separates AI from official

18 AI charts. A metric's official base rate is about 10%, by construction.

| Metric | Official p05..p95 | AI median | AI below | AI above |
|---|---|---|---|---|
| direction_change_pct | 71.1..86.76 | 89.94 | 1 | 12 |
| approach_heights_per_s_median | 1.2..1.44 | 1.77 | 1 | 11 |
| background_present_pct | 0..90.29 | 91.33 | 0 | 11 |
| strong_motion_pct | 43.17..96.71 | 24.03 | 11 | 0 |
| carrier_motion_pct | 55.13..99.02 | 46.06 | 10 | 0 |
| onset_step_under50_pct | 7.96..28.18 | 6.32 | 10 | 0 |
| required_move_200plus_pct | 21.26..52.38 | 19.31 | 10 | 0 |
| judging_carrier_motion_pct | 52.67..99.06 | 48.1 | 9 | 0 |
| required_travel_px_per_s | 699..1366 | 760 | 8 | 0 |
| any_motion_pct | 72.28..99.64 | 80.55 | 8 | 0 |
| onset_step_200plus_pct | 48.01..78.62 | 74.06 | 0 | 7 |
| required_move_median_px | 105..210 | 125 | 6 | 0 |
| onset_step_median_px | 197..375 | 340 | 0 | 6 |
| background_motion_pct | 0..89.03 | 79.1 | 0 | 6 |
| section_spread_cv | 0.2..0.61 | 0.23 | 6 | 0 |
| longest_carrier_still_during_play_s | 0.5..17.23 | 9.5 | 0 | 6 |
| section_line_activity_cv | 0.28..0.84 | 0.37 | 5 | 1 |
| x_spread_iqr_px | 394..547 | 482 | 4 | 1 |
| section_density_cv | 0.3..0.71 | 0.47 | 5 | 0 |
| required_move_under50_pct | 13.34..37.68 | 21.11 | 2 | 3 |
| carrier_response_gap_p90_s | 7.67..54.77 | 15 | 5 | 0 |
| bg_two_plus_lines_moving_pct | 0..78.06 | 54.08 | 0 | 4 |
| section_travel_cv | 0.36..0.8 | 0.54 | 3 | 1 |
| longest_all_still_during_play_s | 0.5..9.5 | 5 | 0 | 4 |
| bg_lines_moving_together_median | 0..4 | 2 | 0 | 2 |
| bg_three_plus_lines_moving_pct | 0..59.14 | 9.48 | 0 | 2 |
| fresh_onsets_per_s | 3.51..6.03 | 5.58 | 0 | 1 |

## Flags by recorded verdict

| Verdict | Scope | Charts | Flags, min / median / max |
|---|---|---|---|
| pending | whole | 3 | 6 / 10 / 11 |
| rejected | whole | 12 | 3 / 10 / 19 |
| unknown | whole | 3 | 7 / 11 / 12 |
| accepted | excerpt | 5 | 2 / 4 / 9 |
| approved | excerpt | 2 | 3 / 3.5 / 4 |
| corrected | excerpt | 1 | 5 / 5 / 5 |
| pending | excerpt | 1 | 1 / 1 / 1 |
| rejected | excerpt | 5 | 0 / 4 / 5 |
| unknown | excerpt | 3 | 1 / 1 / 5 |

## Whole songs

| Chart | Verdict | L0 | move px | <50px % | hits/s | approach | carrier % | bg % | strong % | 2+ bg % | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Official p05..p95** | | | 105..210 | 13.34..37.68 | 3.51..6.03 | 1.2..1.44 | 55.13..99.02 | 0..89.03 | 43.17..96.71 | 0..78.06 | |
| **Official median** | | | 158 | 25.06 | 5 | 1.32 | 85.98 | 44.84 | 82.12 | 24.86 | |
| he-sol-run01 | unknown | pass | 160 | 20.93 | 5.86 | 1.41 | 0 | 72.35 | 0.96 | 72.35 | 7 |
| he-presentation-r01 | rejected | pass | 152 | 19.91 | 5.86 | 1.41 | 38.91 | 61.09 | 5.47 | 10.61 | 6 |
| he-run02 | rejected | pass | 23.8 | 83.22 | 5.1 | 1.84 | 17.68 | 12.86 | 8.36 | 10.29 | 14 |
| he-run03 | rejected | pass | 150 | 16.62 | 5.1 | 1.84 | 76.21 | 97.43 | 93.25 | 97.43 | 9 |
| he-five-A | rejected | pass | 130 | 30.41 | 5.56 | 1.84 | 84.57 | 85.85 | 38.26 | 74.6 | 9 |
| he-five-B | rejected | pass | 160 | 20.6 | 5.77 | 1.84 | 78.78 | 90.03 | 26.37 | 69.45 | 5 |
| he-five-C | rejected | pass | 140 | 17.82 | 5.41 | 1.84 | 69.77 | 85.85 | 67.52 | 39.55 | 5 |
| he-five-D | rejected | pass | 95 | 31.77 | 5.8 | 1.84 | 77.49 | 89.07 | 78.78 | 58.52 | 11 |
| he-five-E | rejected | pass | 150 | 21.2 | 5.6 | 1.84 | 72.35 | 88.1 | 81.03 | 77.49 | 3 |
| he-full-c | pending | pass | 130 | 21.02 | 5.5 | 1.84 | 53.21 | 90.38 | 75.64 | 83.65 | 6 |
| override-sol-in163 | unknown | pass | 120 | 30.79 | 5.77 | 1.71 | 32.72 | 52.21 | 21.69 | 49.63 | 11 |
| override-sol-in163-perf | pending | pass | 120 | 30.79 | 5.77 | 1.71 | 91.18 | 99.26 | 90.81 | 90.44 | 10 |
| override-three-a | rejected | pass | 12.1 | 98.2 | 6.12 | 1.38 | 0 | 0 | 0 | 0 | 16 |
| override-three-b | rejected | pass | 95 | 6.83 | 5.1 | 1.38 | 0 | 0 | 0 | 0 | 19 |
| override-three-c | rejected | pass | 130 | 3.88 | 5.92 | 1.38 | 0 | 0 | 0 | 0 | 16 |
| xterfusion-first | unknown | pass | 77.7 | 43.14 | 4.06 | 1.13 | 12.12 | 16.67 | 18.79 | 16.67 | 12 |
| xterfusion-sol | rejected | pass | 100 | 34 | 3.99 | 1.38 | 0 | 6.67 | 0.61 | 6.06 | 12 |
| xterfusion-audio-only | pending | pass | 117 | 15.8 | 4.88 | 1.84 | 55.45 | 93.94 | 67.58 | 84.55 | 11 |

## Excerpts (band shown is 13 s; flags use the nearest length)

| Chart | Verdict | L0 | move px | <50px % | hits/s | approach | carrier % | bg % | strong % | 2+ bg % | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Official p05..p95** | | | 15.02..226 | 4.4..57.74 | 1.48..8.06 | 0.91..1.44 | 11.63..100 | 0..100 | 28.23..100 | 0..100 | |
| **Official median** | | | 158 | 23.86 | 5.04 | 1.32 | 73.91 | 84 | 87.5 | 68 | |
| climax-A | rejected | pass | 210 | 4.92 | 8.07 | 1.84 | 91.3 | 100 | 69.57 | 100 | 5 |
| climax-B | rejected | pass | 200 | 16.67 | 7.86 | 1.84 | 86.96 | 95.65 | 82.61 | 73.91 | 3 |
| climax-C-initial | rejected | pass | 200 | 10.71 | 7.3 | 1.84 | 95.65 | 91.3 | 78.26 | 0 | 4 |
| climax-C-orientation | rejected | pass | 200 | 10.71 | 7.3 | 1.84 | 95.65 | 91.3 | 73.91 | 0 | 4 |
| climax-C-ensemble | approved | pass | 200 | 10.71 | 7.3 | 1.84 | 95.65 | 100 | 100 | 91.3 | 3 |
| iris-original | rejected | pass | 110 | 20.51 | 8.3 | 0.99 | 100 | 100 | 94.74 | 100 | 0 |
| iris-revision-D | pending | pass | 110 | 17.95 | 8.3 | 2 | 100 | 100 | 100 | 100 | 1 |
| escapement-transfer | unknown | pass | 152 | 11.29 | 5.61 | 2 | 38.89 | 100 | 100 | 0 | 1 |
| entrance-transfer | unknown | pass | 152 | 9.68 | 5.61 | 2 | 100 | 100 | 100 | 100 | 1 |
| silent-180-wide-travel | approved | pass | 180 | 31.84 | 12.03 | 1.38 | 0 | 0 | 0 | 0 | 4 |
| silent-180-arrangement | unknown | pass | 80 | 36.46 | 7.04 | 1.38 | 0 | 0 | 0 | 0 | 5 |
| silent-150-style-one | accepted | pass | 30 | 86.36 | 4.8 | 1.38 | 0 | 0 | 0 | 0 | 9 |
| silent-150-style-two | accepted | pass | 120 | 15.62 | 4.29 | 1.38 | 0 | 0 | 0 | 0 | 2 |
| silent-150-tech | accepted | pass | 300 | 37.65 | 6.74 | 1.38 | 0 | 0 | 0 | 0 | 2 |
| silent-150-speed | accepted | pass | 300 | 32.99 | 10.1 | 1.38 | 0 | 0 | 0 | 0 | 4 |
| silent-150-stream | accepted | pass | 300 | 5.8 | 10 | 1.38 | 0 | 0 | 0 | 0 | 4 |
| silent-150-jack | corrected | pass | 0 | 78.57 | 5.1 | 1.38 | 0 | 0 | 0 | 0 | 5 |

## Named official charts, whole

| Chart | Constant | move px | <50px % | hits/s | approach | carrier % | bg % | strong % | 2+ bg % | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| AbsoluTe disoRdeR | 16.3 | 172 | 34.28 | 5 | 1.38 | 97.3 | 28.03 | 94.61 | 0 | 0 |
| Der Schneid | 16.1 | 150 | 29.39 | 6.3 | 1.35 | 71.19 | 91.86 | 96.95 | 88.81 | 6 |
| Entrance to the Chaos | 16.8 | 197 | 15.9 | 5.5 | 1.38 | 68.35 | 90.29 | 91.37 | 83.81 | 4 |
| Fractured Angel | 16.3 | 158 | 27.29 | 3.62 | 1.44 | 85.34 | 49.85 | 87.1 | 28.15 | 2 |
| Non-Melodic Ragez (MUG Edit) | 16.1 | 150 | 23.55 | 4.6 | 1.32 | 56.67 | 17.41 | 43.7 | 4.07 | 2 |
| QZKago Requiem | 16.3 | 158 | 26.13 | 4.73 | 1.38 | 78.2 | 83.46 | 84.21 | 48.12 | 0 |
| Verrückt | 16.5 | 162 | 31.01 | 7.39 | 1.44 | 89.4 | 60.37 | 75.12 | 51.61 | 4 |
| What do you want more than a Happy ending? | None | 210 | 25.9 | 5.59 | 1.38 | 99.35 | 0 | 94.5 | 0 | 7 |

## Excluded

- charts/other/projects/stardust-ray-in: human-charted official source
- charts/other/entrance-study, poseidon-study: official imports
- charts/other/rrharil-at-scroll-130: community chart with a speed change
- charts/other/poseidon-pure-configuration: adaptation that keeps existing note timing
- override-gesture-sample: under 8 s of play
- speed-revision-01, Iris calibration B and C, override pilot: near-duplicates of included charts
