# Corpus coverage and evidenced lessons

## Current reference lookup (2026-11-02)

Read downloaded IN originals from `research/arrangement-training/raw/<source-chart-id>/IN.json` (repository-relative), using `research/arrangement-training/manifest.json` to resolve titles and paths. This snapshot contains 327 songs; Random retains only variant `.0`. See [the local corpus guide](../../arrangement-training/README.md). Do not redownload these charts through the website. Use original charts, not the angle-filtered training representation, for reference study. Existing AT/audio evidence remains in this study's `../corpus/manifest.json`. Source URLs below document the historical acquisition.

## Historical study

Study date: 2026-10-01, America/Toronto. Scope: all current charts labeled IN16 and AT17, with creation/rechart dates 2023-10-01–2026-10-01 prioritized.

Acquired 53 official-formatVersion3 charts: 38 IN16 and 15 AT17. All chart requests and all corresponding full song audio requests succeeded. Canonical line-local arrangement is separately plotted from presented contacts; normalization collapses approach axes but does not by itself solve cross-line hand assignment. Each resource has URL, byte count and SHA256 in `../corpus/manifest.json`. GitHub downloader: https://github.com/swordalt/phigros-chart-downloader ; UI: https://swordalt.github.io/phigros-chart-downloader/ ; actual resources: https://github.com/7aGiven/Phigros_Resource . Direct read-only requests avoided website download telemetry.

The broad wiki chart list was stale at 36 IN16 +13 AT17. The two additional songs in v4.0.0 are Entrance to the Chaos and Exoplanetary Mirage, each with IN and AT. Their individual wiki unlock pages confirm they were playable in the Sep25 release; the Oct2 continuation is later content. See https://wikiwiki.jp/phigros/Chapter%209%20%E9%9A%A0%E3%81%97%E6%9B%B2%204 and https://wikiwiki.jp/phigros/Chapter%209%20%E9%9A%A0%E3%81%97%E6%9B%B2%205 .

33 of these charts have a creation or explicitly identified rechart in the requested three-year interval. Dates use https://wikiwiki.jp/phigros/アップデート履歴/3 and chart-origin versions from https://wikiwiki.jp/phigros/高レベル譜面定数(CC)表 . The v3.11.0 level-label promotion is NOT treated as a newly made chart. Twelve pre-v3 origin/rechart dates remain exact-day-unverified, but are known to predate the three-year cutoff. Chronostasis and Lyrith are recent remakes despite older song introductions. Cycle of Redemption normal IN was introduced 2025-08-31; its 2024 April Fools SP is a different chart.

Every acquired chart was scanned in full numerically and inspected as a static schematic atlas (18 sheets, all 53 rows). Six snapshots plus the whole contact timeline are available in `atlas.html`. This is not a claim that every chart was watched in full gameplay, played, or validated by a human top player. The atlas uses official linear event transforms, speed-floor integration and a 16:9 sample; hold snapshot glyphs have short schematic tails; timeline tails mark actual duration at initial head x and do not trace moving held contacts. It does not model the complete official hit engine.

One explicit source discrepancy remains: Stardust:RAY IN is 1382 in both wiki aggregate and individual page, while the acquired current resource contains 1392 raw note objects. No assumption is made about why. Other 49 aggregate-confirmed charts match wiki note count; the four v4.0.0 charts match their individual pages.

## Four note roles and difficulty

- Official JSON types: 1 Tap, 2 Drag, 3 Hold, 4 Flick. Tap articulates a discrete strike; Drag judges contact along a sequence without a new press per object; Hold creates continuous ownership over a duration; Flick adds motion commitment/accent. Spatial proximity and judgment windows mean these are not four interchangeable colored taps.
- Distorted Fate IN: 1449 = 841 Tap, 430 Drag, 132 Hold, 46 Flick; AT: 1283 = 907 Tap, 115 Drag, 212 Hold, 49 Flick. AT has fewer objects but more strike/sustain ownership and 46 line objects versus24.
- Rrhar’il IN and AT both1300. IN: 802/410/53/35; AT: 991/44/123/142. Same total, very different physical articulation.
- Toy Rhapsody IN1418 versus AT1374: IN285/637/318/178; AT652/197/317/208. Again the AT reduces drag mass and makes more independent attacks.
- Verrückt IN: 837 Tap,398 Drag,50 Hold,0 Flick. Quality does not require all four types.
- Raw onset groups are not finger counts. A drag ribbon can contain many objects judged by one continuous touch. Conversely one new Tap during several held contacts can demand an additional free finger even with a small onset group. `raw_note_objects_plus_active_holds_peak` is deliberately named as a raw object statistic and is not a finger-capacity estimate. A practical fingering review needs spatial contact merging, hold tracking, hand travel, fresh press/release timing, crossing and occlusion.

## Aesthetic and compositional lessons

- Judge-line motion is both stage geometry and a playable coordinate transform. Decorative line objects often have no notes; line/event counts must not be read as simultaneous contact demand or aesthetic quality. Sampled easing exports can create thousands of tiny events for one authored movement.
- Broad recurring contrasts are stable stations versus traveling diagonals; dense strike fields versus sustained ownership; ornamental drag contour versus keyboard detail; symmetric construction followed by a deliberate asymmetry. These are visual observations of the atlas, not music-source attribution.
- IN→AT often changes how voices are owned, rather than uniformly increasing speed, density or moving-line chaos. The lower drag share makes individual strikes, holding fingers and flick commitments matter.
- Rest intervals frequently keep a few sustained owned voices. This creates breathing room and preserves continuity, then makes the return of fast detail meaningful. Removing those intervals would flatten the arrangement and physical arc.
- A 4K stair must be planned as an ordered lane/hand pattern with an entry finger, an exit/repeat decision and enough release time. Dense arbitrary left-to-right taps are not enough. Crossing an owned hold lane, striking through a drag carpet or interleaving a flick changes the required solution.
- Whole-chart templates should preserve phrase boundaries, repeated motif identity and a planned climax. Theme transfer should reuse a transformation rule (mirroring, orbital motion, frames, branching) at chosen musical anchors; it should not copy an entire official chart’s events and simply change the song.

## Per-chart static review

### 01 Non-Melodic Ragez (MUG Edit) IN 16.1

Long strike streams occupy a few repeating horizontal stations; short diagonal streams and a broad ending sweep break the grid. The oldest design uses only six line objects, showing that visual impact does not require a large line pool.

Evidence: [atlas](atlas/01-IN.png); samples 13.76s, 41.27s, 68.78s, 36.00s, 103.17s, 127.93s. Highest counted 8s bin 32–40s: 199 objects; lowest populated bin 40–48s: 12 objects. Creation/rechart: 1.5.0 / exact day unverified (older than cutoff).

### 02 Igallta IN 16.1

Opening gestures converge toward the middle before the chart settles into widely separated stations. The late run mixes mirrored diagonals and small flashes of flick color rather than increasing line count.

Evidence: [atlas](atlas/02-IN.png); samples 11.97s, 35.92s, 59.87s, 100.00s, 89.80s, 111.36s. Highest counted 8s bin 96–104s: 101 objects; lowest populated bin 64–72s: 37 objects. Creation/rechart: 1.5.0 / exact day unverified (older than cutoff).

### 03 Igallta AT 17.4

The sustained opening and ending bracket the dense central keyboard texture. Note totals remain relatively low; simultaneous sustain ownership and separated strike positions drive the AT identity.

Evidence: [atlas](atlas/03-AT.png); samples 11.97s, 35.92s, 59.87s, 116.00s, 89.80s, 111.36s. Highest counted 8s bin 112–120s: 132 objects; lowest populated bin 64–72s: 36 objects. Creation/rechart: 1.5.0 / exact day unverified (older than cutoff).

### 04 Chronos Collapse - La Campanella IN 16.3

At 75.67–76s the drag sequence draws a wide zigzag against crossing diagonals. The entire contact timeline combines repeated columns with curved ribbons; ornamental drags carry large portions of the visible contour.

Evidence: [atlas](atlas/04-IN.png); samples 15.13s, 45.40s, 75.67s, 76.00s, 113.50s, 140.74s. Highest counted 8s bin 72–80s: 167 objects; lowest populated bin 80–88s: 10 objects. Creation/rechart: 2.0.0 / exact day unverified (older than cutoff).

### 05 Rrhar'il IN 16.1

IN presents stable stations punctuated by crossing gestures and a long sustained respite in the latter middle. Mirroring and paired vertical runs create pattern recognition work without constant full-screen chaos.

Evidence: [atlas](atlas/05-IN.png); samples 13.01s, 39.03s, 65.05s, 76.00s, 97.58s, 121.00s. Highest counted 8s bin 72–80s: 136 objects; lowest populated bin 128–136s: 2 objects. Creation/rechart: 2.0.0 / exact day unverified (older than cutoff).

### 06 Rrhar'il AT 17.6

AT redistributes much of the drag texture into taps, holds and flicks at the same total count. The middle respite consists of separated sustained contacts, then the late timeline thickens into independent strike clusters.

Evidence: [atlas](atlas/06-AT.png); samples 13.01s, 39.03s, 65.05s, 116.00s, 97.58s, 121.00s. Highest counted 8s bin 112–120s: 133 objects; lowest populated bin 128–136s: 1 objects. Creation/rechart: 2.0.0 / exact day unverified (older than cutoff).

### 07 Retribution IN 16.2

The line grid changes from parallel diagonals to crossed diagonals and a lattice at 106.11s. The final 140s sampling shows a narrow drag column and surrounding strike gestures, giving the end a visual signature.

Evidence: [atlas](atlas/07-IN.png); samples 14.15s, 42.44s, 70.74s, 140.00s, 106.11s, 131.57s. Highest counted 8s bin 136–144s: 207 objects; lowest populated bin 8–16s: 11 objects. Creation/rechart: 3.0.0 / 2023-04-21.

### 08 DESTRUCTION 3,2,1 IN 16.3

At 78.10s the lines form a radial polygon; by 148s the ornamentation forms broad drag fans. Sparse preceding islands make the later density expansion visible in the timeline.

Evidence: [atlas](atlas/08-IN.png); samples 15.62s, 46.86s, 78.10s, 148.00s, 117.15s, 145.27s. Highest counted 8s bin 144–152s: 153 objects; lowest populated bin 8–16s: 17 objects. Creation/rechart: 3.0.0 / 2023-04-21.

### 09 DESTRUCTION 3,2,1 AT 17.3

AT expands the fan into dense repeated drag rows at 148s while preserving the radial line scene near 78s. Raw drag-object density is very high and must not be interpreted as independent fingers.

Evidence: [atlas](atlas/09-AT.png); samples 15.62s, 46.86s, 78.10s, 148.00s, 117.15s, 145.27s. Highest counted 8s bin 144–152s: 256 objects; lowest populated bin 8–16s: 18 objects. Creation/rechart: 3.0.0 / 2023-04-21.

### 10 Distorted Fate IN 16.3

The long late drag field has two broad alternating lobes around 108–118s. The earlier section stays comparatively legible with a modest baseline and small rotation.

Evidence: [atlas](atlas/10-IN.png); samples 15.72s, 47.16s, 78.60s, 108.00s, 117.90s, 146.20s. Highest counted 8s bin 104–112s: 160 objects; lowest populated bin 152–160s: 20 objects. Creation/rechart: 3.0.0 / 2023-04-21.

### 11 Distorted Fate AT 17.4

The AT timeline has fewer drag carpets and more separated sustain ownership, especially near 110–120s. At 117.9s multiple short holds form a keyboard-like spatial layout; fewer total notes still produces more finger independence.

Evidence: [atlas](atlas/11-AT.png); samples 15.72s, 47.16s, 78.60s, 140.00s, 117.90s, 146.20s. Highest counted 8s bin 136–144s: 114 objects; lowest populated bin 96–104s: 18 objects. Creation/rechart: 3.0.0 / 2023-04-21.

### 12 Entrance to the Chaos IN 16.8

Opening long holds lead into increasing broad diagonal motion, with a sparse middle reset. The 131.55s scene has a bank of near-vertical lines and several strike stations; the ending changes its articulation.

Evidence: [atlas](atlas/12-IN.png); samples 14.14s, 42.43s, 70.72s, 140.00s, 106.09s, 131.55s. Highest counted 8s bin 136–144s: 264 objects; lowest populated bin 8–16s: 1 objects. Creation/rechart: 4.0.0 / 2026-09-25.

### 13 Entrance to the Chaos AT 17.6

AT introduces crossing lines and separated sustain stations before the late keyboard burst. The middle reset is especially clear: held voices remain while rapid strikes recede, then the late scene reclaims broad space.

Evidence: [atlas](atlas/13-AT.png); samples 14.26s, 42.78s, 71.30s, 124.00s, 106.96s, 132.63s. Highest counted 8s bin 120–128s: 156 objects; lowest populated bin 8–16s: 2 objects. Creation/rechart: 4.0.0 / 2026-09-25.

### 14 Exoplanetary Mirage IN 16.9

The IN timeline alternates thick drag blocks with less dense strike fields. At 128–132s the horizontal yellow ribbon and broad diagonal scene make drag contour a prominent visual language.

Evidence: [atlas](atlas/14-IN.png); samples 17.12s, 51.38s, 85.62s, 132.00s, 128.44s, 159.26s. Highest counted 8s bin 128–136s: 227 objects; lowest populated bin 0–8s: 1 objects. Creation/rechart: 4.0.0 / 2026-09-25.

### 15 Exoplanetary Mirage AT 17.9

AT reduces the large drag share and doubles down on independent strike stations and sustained anchors. The 51–53s scene packs short yellow clusters around vertical separators; later the texture opens, then returns.

Evidence: [atlas](atlas/15-AT.png); samples 17.11s, 51.33s, 85.55s, 52.00s, 128.32s, 159.12s. Highest counted 8s bin 48–56s: 188 objects; lowest populated bin 8–16s: 23 objects. Creation/rechart: 4.0.0 / 2026-09-25.

### 16 Aleph-0 IN 16.0

Much of the playable texture uses repeated stations with occasional rotating diagonals. Long holds form a sparse latter-middle interval, making the final increased density feel like a distinct return.

Evidence: [atlas](atlas/16-IN.png); samples 13.20s, 39.60s, 66.00s, 68.00s, 99.00s, 122.76s. Highest counted 8s bin 64–72s: 97 objects; lowest populated bin 0–8s: 2 objects. Creation/rechart: 2.5.0 / exact day unverified (older than cutoff).

### 17 Chronostasis IN 16.0

The rechart uses drag fields as visible contour around the 100s dense interval. Several later short holds and a tilted line bring motion into the closing passage while keeping the main strike stations traceable.

Evidence: [atlas](atlas/17-IN.png); samples 14.00s, 41.99s, 69.98s, 100.00s, 104.97s, 130.16s. Highest counted 8s bin 96–104s: 118 objects; lowest populated bin 136–144s: 13 objects. Creation/rechart: 3.9.0 / 2024-08-31.

### 18 CROSS†SOUL IN 16.4

Only six lines organize a demanding mix of moving strikes, holds and dense drag passages. The 99s snapshot is a diagonal doubled drag stream; broad mid-chart sustain spans interrupt the densest fields.

Evidence: [atlas](atlas/18-IN.png); samples 13.20s, 39.60s, 66.00s, 20.00s, 99.00s, 122.76s. Highest counted 8s bin 16–24s: 167 objects; lowest populated bin 0–8s: 15 objects. Creation/rechart: 1.4.2 / exact day unverified (older than cutoff).

### 19 GOODRAGE IN 16.0

The first third uses traveling zigzags and flick paths, then the ending stabilizes into repeated strike stations. This contrast suggests a visual narrative of unsettled motion becoming an endurance finish.

Evidence: [atlas](atlas/19-IN.png); samples 11.78s, 35.35s, 58.92s, 100.00s, 88.38s, 109.59s. Highest counted 8s bin 96–104s: 111 objects; lowest populated bin 0–8s: 49 objects. Creation/rechart: 1.4.7 / exact day unverified (older than cutoff).

### 20 Cthugha IN 16.0

The middle timeline contains an unusually clear bank of closely repeated stations, then returns to broad hand travel. Holds add ownership while the final section increases repeated strike density.

Evidence: [atlas](atlas/20-IN.png); samples 15.39s, 46.18s, 76.97s, 68.00s, 115.46s, 143.17s. Highest counted 8s bin 64–72s: 107 objects; lowest populated bin 0–8s: 12 objects. Creation/rechart: 2.4.1 / exact day unverified (older than cutoff).

### 21 RESSiSTANCE IN 16.1

Drag density is very low, while holds and flicks are substantial. Visually stable stations and repeated rows make the physical striking work central; occasional twists and wide gestures punctuate it.

Evidence: [atlas](atlas/21-IN.png); samples 14.34s, 43.02s, 71.71s, 76.00s, 107.56s, 133.38s. Highest counted 8s bin 72–80s: 89 objects; lowest populated bin 88–96s: 20 objects. Creation/rechart: 2.1.0 / exact day unverified (older than cutoff).

### 22 零號車輛 IN 16.2

At 100s a dense diagonal lattice frames only a few strike objects, while the whole timeline remains organized by repeated stations and zigzag transitions. Background line spectacle and contact demand are separable layers.

Evidence: [atlas](atlas/22-IN.png); samples 14.18s, 42.52s, 70.88s, 100.00s, 106.31s, 131.83s. Highest counted 8s bin 96–104s: 137 objects; lowest populated bin 64–72s: 7 objects. Creation/rechart: 2.5.1 / exact day unverified (older than cutoff).

### 23 Ad astra per aspera IN 16.3

The wide contact field and short holds build endurance without an overwhelming drag share. Parallel line bands appear around 70.66s; latter-middle spacing creates a reset before the dense closing motion.

Evidence: [atlas](atlas/23-IN.png); samples 14.13s, 42.40s, 70.66s, 36.00s, 105.99s, 131.43s. Highest counted 8s bin 32–40s: 143 objects; lowest populated bin 136–144s: 47 objects. Creation/rechart: 3.1.0 / 2023-06-09.

### 24 +ERABY+E CONNEC+10N IN 16.3

The 16.07s scene uses intersecting drag ribbons and the full timeline contains several dense ornamental banks. A broad sustained interval precedes a closing expansion, so density is arranged in phrases.

Evidence: [atlas](atlas/24-IN.png); samples 16.07s, 48.21s, 80.35s, 68.00s, 120.52s, 149.45s. Highest counted 8s bin 64–72s: 137 objects; lowest populated bin 144–152s: 2 objects. Creation/rechart: 3.2.0 / 2023-08-31.

### 25 +ERABY+E CONNEC+10N AT 17.3

AT replaces much of the IN drag weight with strike clusters and flick accents. The 140s dense sampling appears deceptively sparse as an approach frame: fast movement and actual onset timing matter more than a single screenshot.

Evidence: [atlas](atlas/25-AT.png); samples 16.07s, 48.21s, 80.35s, 140.00s, 120.52s, 149.45s. Highest counted 8s bin 136–144s: 150 objects; lowest populated bin 144–152s: 2 objects. Creation/rechart: 3.2.0 / 2023-08-31.

### 26 Fractured Angel IN 16.3

The timeline alternates clear sparse islands with dense bursts. Holds anchor both hands while rapid detail appears around them; at 167.03s diagonal lines form a closing X scene.

Evidence: [atlas](atlas/26-IN.png); samples 17.96s, 53.88s, 89.80s, 156.00s, 134.70s, 167.03s. Highest counted 8s bin 152–160s: 101 objects; lowest populated bin 96–104s: 2 objects. Creation/rechart: 3.2.2 / 2023-10-27.

### 27 祈 -我ら神祖と共に歩む者なり- IN 16.4

The contact timeline is crowded almost throughout, with broad directional sweeps at several phrase boundaries. A drag fan and strike field coexist near 156s, illustrating why high total density can still contain traceable voice contours.

Evidence: [atlas](atlas/27-IN.png); samples 17.29s, 51.86s, 86.44s, 156.00s, 129.66s, 160.78s. Highest counted 8s bin 152–160s: 153 objects; lowest populated bin 0–8s: 14 objects. Creation/rechart: 3.4.0 / 2023-12-15.

### 28 祈 -我ら神祖と共に歩む者なり- AT 17.3

AT shifts some drag contour into hold and flick commitments at the same 2222 total. Repeated sustain stations and diagonal geometry appear in the middle; the final third increases spatial and strike demands.

Evidence: [atlas](atlas/28-AT.png); samples 17.29s, 51.86s, 86.43s, 164.00s, 129.65s, 160.77s. Highest counted 8s bin 160–168s: 182 objects; lowest populated bin 0–8s: 5 objects. Creation/rechart: 3.4.0 / 2023-12-15.

### 29 PRAGMATISM -RESURRECTION- IN 16.0

The early dense gesture gives way to an exceptionally clear sustain interval in the latter middle, then returns to busy mixed articulation. At 148s several short holds are spread as distinct owned voices.

Evidence: [atlas](atlas/29-IN.png); samples 15.52s, 46.55s, 77.59s, 148.00s, 116.39s, 144.32s. Highest counted 8s bin 144–152s: 152 objects; lowest populated bin 104–112s: 3 objects. Creation/rechart: 3.6.1 / 2024-04-26.

### 30 Bounded Quietude IN 16.2

The contact timeline has fast repeated station fields with a sparse interval before the closing burst. Vertical and diagonal line bundles at 111.86–116s concentrate the visual attention just before that climax.

Evidence: [atlas](atlas/30-IN.png); samples 14.91s, 44.74s, 74.57s, 116.00s, 111.86s, 138.70s. Highest counted 8s bin 112–120s: 144 objects; lowest populated bin 0–8s: 12 objects. Creation/rechart: 3.8.0 / 2024-07-26.

### 31 幻影鬼魅 (PLEASE) AT 17.0

The keyboard fields begin and end strongly, with a distinctly thinner middle separating them. At 114.37s the repeated flick columns add an accent texture to a strike-heavy grid.

Evidence: [atlas](atlas/31-AT.png); samples 12.30s, 36.89s, 61.49s, 116.00s, 92.24s, 114.37s. Highest counted 8s bin 112–120s: 145 objects; lowest populated bin 120–128s: 23 objects. Creation/rechart: 3.10.0 / 2024-10-19.

### 32 KIZUNA Resolution IN 16.4

A sparse middle with short hold ownership precedes a dense final return. The baseline remains low and readable in the samples even as near-vertical separator lines appear around 124s.

Evidence: [atlas](atlas/32-IN.png); samples 12.91s, 38.74s, 64.56s, 124.00s, 96.84s, 120.09s. Highest counted 8s bin 120–128s: 92 objects; lowest populated bin 0–8s: 14 objects. Creation/rechart: 3.12.0 / 2025-04-01.

### 33 AbsoluTe disoRdeR IN 16.3

Long dense strike sequences alternate with large drag sweeps. Strong line changes at 56.32s and 140.80s accompany different contact organizations; the long duration calls for explicit stamina phrasing.

Evidence: [atlas](atlas/33-IN.png); samples 18.77s, 56.32s, 93.87s, 108.00s, 140.80s, 174.59s. Highest counted 8s bin 104–112s: 140 objects; lowest populated bin 0–8s: 8 objects. Creation/rechart: 3.12.0 / 2025-04-01.

### 34 AbsoluTe disoRdeR AT 17.2

AT increases independent striking rather than simply adding longer holds. The latter-middle contains a large central drag gesture, followed by a sustained dense ending with repeated stations and flick punctuation.

Evidence: [atlas](atlas/34-AT.png); samples 18.75s, 56.25s, 93.75s, 116.00s, 140.62s, 174.38s. Highest counted 8s bin 112–120s: 197 objects; lowest populated bin 88–96s: 13 objects. Creation/rechart: 3.12.0 / 2025-04-01.

### 35 NO x IN 16.1

At 72s a yellow basin of drag objects sits among crossing diagonals, and at 108s another drag arc crosses the strike field. Sparse sustains at the start and midsection set up these spatially demanding gestures.

Evidence: [atlas](atlas/35-IN.png); samples 14.40s, 43.20s, 72.00s, 52.00s, 108.00s, 133.92s. Highest counted 8s bin 48–56s: 132 objects; lowest populated bin 0–8s: 5 objects. Creation/rechart: 3.13.0 / 2025-04-18.

### 36 Stardust:RAY IN 16.5

The broad timeline alternates hold commitments, short bursts and dense drag fields; the ending grows dense. At 140.10s the intersecting line scene surrounds a late return to strike density.

Evidence: [atlas](atlas/36-IN.png); samples 16.02s, 48.06s, 80.10s, 140.00s, 120.15s, 148.98s. Highest counted 8s bin 136–144s: 159 objects; lowest populated bin 160–168s: 5 objects. Creation/rechart: 3.14.0 / 2025-06-06.

### 37 Stardust:RAY AT 17.2

AT gives hold ownership an especially large share (309 objects), visible as repeated long stations and dense punctuated keyboard sections. The ending overlays multiple voices while the earlier space prepares the change.

Evidence: [atlas](atlas/37-AT.png); samples 16.02s, 48.07s, 80.12s, 156.00s, 120.18s, 149.03s. Highest counted 8s bin 152–160s: 136 objects; lowest populated bin 160–168s: 4 objects. Creation/rechart: 3.14.0 / 2025-06-06.

### 38 Retribution ~ Cycle of Redemption ~  IN 16.2

The full timeline repeatedly transitions between sustain islands, flick accents and broad drag crossings. The 68s peak scene consists of narrow columns around paired held contacts; raw count alone hides the hand-ownership problem.

Evidence: [atlas](atlas/38-IN.png); samples 17.23s, 51.68s, 86.13s, 68.00s, 129.20s, 160.21s. Highest counted 8s bin 64–72s: 113 objects; lowest populated bin 104–112s: 1 objects. Creation/rechart: 3.15.1 / 2025-08-31.

### 39 sølips IN 16.0

Drag contour carries a large share of the design. Crossed lines around 124s frame a returning dense section, while a sparse sustain scene earlier gives the contact field a clean structural break.

Evidence: [atlas](atlas/39-IN.png); samples 14.25s, 42.74s, 71.23s, 124.00s, 106.85s, 132.49s. Highest counted 8s bin 120–128s: 125 objects; lowest populated bin 0–8s: 4 objects. Creation/rechart: 3.16.0 / 2025-09-19.

### 40 QZKago Requiem IN 16.3

The IN contact texture emphasizes paired strikes and smaller drag inflections; it stays visually comparatively stable in the later samples. Several long sustained gestures divide the otherwise fast detail.

Evidence: [atlas](atlas/40-IN.png); samples 13.43s, 40.30s, 67.16s, 124.00s, 100.75s, 124.93s. Highest counted 8s bin 120–128s: 119 objects; lowest populated bin 72–80s: 8 objects. Creation/rechart: 3.16.0 / 2025-09-19.

### 41 QZKago Requiem AT 17.4

AT contains much denser clustered stations and a central drag bank, then a clean sustained respite before the final keyboard passage. 76s is a broad drag field; 124.84s shows multiple near-simultaneous strike stations.

Evidence: [atlas](atlas/41-AT.png); samples 13.42s, 40.27s, 67.12s, 76.00s, 100.68s, 124.84s. Highest counted 8s bin 72–80s: 213 objects; lowest populated bin 80–88s: 13 objects. Creation/rechart: 3.16.0 / 2025-09-19.

### 42 Hydra AT 17.1

The whole-chart timeline maintains frequent hold ownership and interleaved detail rather than relying on one giant climax. The final samples alternate diagonals and crossed line banks around compact strike fields.

Evidence: [atlas](atlas/42-AT.png); samples 14.78s, 44.32s, 73.88s, 36.00s, 110.81s, 137.41s. Highest counted 8s bin 32–40s: 123 objects; lowest populated bin 0–8s: 14 objects. Creation/rechart: 3.18.0 / 2025-11-21.

### 43 Incyde IN 16.2

The long chart has a clear quiet island near its middle before returning to mixed strike and drag density. At 148s several sustained contacts share a tilted line scene; the final run combines continuous ownership with new strikes.

Evidence: [atlas](atlas/43-IN.png); samples 19.07s, 57.20s, 95.33s, 148.00s, 143.00s, 177.32s. Highest counted 8s bin 144–152s: 112 objects; lowest populated bin 64–72s: 8 objects. Creation/rechart: 3.18.2 / 2026-01-16.

### 44 彩 IN 16.4

The contact field has a broad middle respite and busy banks on either side. Holds are relatively restrained in count, so long strike and drag runs organize most of the density.

Evidence: [atlas](atlas/44-IN.png); samples 15.95s, 47.86s, 79.77s, 140.00s, 119.66s, 148.37s. Highest counted 8s bin 136–144s: 106 objects; lowest populated bin 0–8s: 11 objects. Creation/rechart: 3.18.2 / 2026-01-16.

### 45 Verrückt IN 16.5

There are no flicks: fast strikes, drags and short holds carry all articulation. Dense alternating strike stations and contour ribbons fill most of the timeline, establishing difficulty through execution rather than a four-type checklist.

Evidence: [atlas](atlas/45-IN.png); samples 11.77s, 35.32s, 58.87s, 36.00s, 88.30s, 109.49s. Highest counted 8s bin 32–40s: 143 objects; lowest populated bin 56–64s: 38 objects. Creation/rechart: 3.18.4 / 2026-03-06.

### 46 玩具狂奏曲 -終焉- IN 16.0

The IN timeline uses unusually heavy drag contour and hold ownership compared with its AT counterpart. At 45.28s crossing line geometry and widely spaced contacts are part of the identity; the end retains strong crossed-direction demand.

Evidence: [atlas](atlas/46-IN.png); samples 15.09s, 45.28s, 75.46s, 140.00s, 113.19s, 140.36s. Highest counted 8s bin 136–144s: 143 objects; lowest populated bin 32–40s: 35 objects. Creation/rechart: 3.19.1 / 2026-04-24.

### 47 玩具狂奏曲 -終焉- AT 17.0

AT uses more taps and flicks while reducing drag count, even at a slightly lower total. Holds remain numerous, and the whole timeline shows a persistent keyboard texture with sparse sustained breaks.

Evidence: [atlas](atlas/47-AT.png); samples 15.09s, 45.28s, 75.46s, 84.00s, 113.19s, 140.36s. Highest counted 8s bin 80–88s: 121 objects; lowest populated bin 32–40s: 33 objects. Creation/rechart: 3.19.1 / 2026-04-24.

### 48 70 Minutes Fighters IN 16.5

A large bank of repeated flick stations is visible near 72.22s, followed by a substantial drag field around the 92s sample. The latter-middle contracts into sustained ownership before the last strike return.

Evidence: [atlas](atlas/48-IN.png); samples 14.04s, 42.13s, 70.22s, 92.00s, 105.34s, 130.62s. Highest counted 8s bin 88–96s: 220 objects; lowest populated bin 0–8s: 3 objects. Creation/rechart: 3.19.3 / 2026-06-12.

### 49 Gungnir Fracture IN 16.6

The central quiet interval consists of separated sustained contacts. The closing line/contact scene converges into a curved ending gesture; dense short-hold/tap interaction earlier creates ownership ambiguity that needs explicit fingering.

Evidence: [atlas](atlas/49-IN.png); samples 14.80s, 44.40s, 74.00s, 68.00s, 111.00s, 137.64s. Highest counted 8s bin 64–72s: 111 objects; lowest populated bin 144–152s: 2 objects. Creation/rechart: 3.19.4 / 2026-07-03.

### 50 夢の降る日に IN 16.6

Diagonal strike and drag gestures repeatedly cross the fixed contact stations. Around 94.02s a broad yellow zigzag frames the phrase return; the final section is a sustained fast field rather than a single large drag carpet.

Evidence: [atlas](atlas/50-IN.png); samples 12.54s, 37.61s, 62.68s, 76.00s, 94.02s, 116.59s. Highest counted 8s bin 72–80s: 136 objects; lowest populated bin 80–88s: 13 objects. Creation/rechart: 3.19.4 / 2026-07-03.

### 51 Der Schneid IN 16.1

IN organizes an opening flick/strike bank, then alternates dense fields with quieter sustained intervals. Near 112.30s the lines form a narrow angular scene, leading to a broad final strike field.

Evidence: [atlas](atlas/51-IN.png); samples 14.97s, 44.92s, 74.86s, 92.00s, 112.30s, 139.25s. Highest counted 8s bin 88–96s: 108 objects; lowest populated bin 64–72s: 16 objects. Creation/rechart: 3.19.4 / 2026-07-03.

### 52 Der Schneid AT 17.5

AT has more sustained contacts and more flick accents, while drag count falls sharply from IN. Several repeated keyboard stations are visible through the whole timeline; parallel sloped lines around 14.93s make the opening geometry explicit.

Evidence: [atlas](atlas/52-AT.png); samples 14.93s, 44.78s, 74.63s, 140.00s, 111.94s, 138.81s. Highest counted 8s bin 136–144s: 127 objects; lowest populated bin 64–72s: 6 objects. Creation/rechart: 3.19.4 / 2026-07-03.

### 53 Lyrith -迷宮リリス- IN 16.1

The 2024 rechart retains a rotating, traveling visual identity with denser strike/flick interactions. Several broad alternating diagonal gestures bracket the sparse middle interval; the closing field combines repeated stations and crossing motion.

Evidence: [atlas](atlas/53-IN.png); samples 14.45s, 43.34s, 72.24s, 124.00s, 108.35s, 134.36s. Highest counted 8s bin 120–128s: 124 objects; lowest populated bin 0–8s: 5 objects. Creation/rechart: 3.5.0 / 2024-02-24.
