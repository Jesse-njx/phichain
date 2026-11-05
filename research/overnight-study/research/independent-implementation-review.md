# Independent implementation review

Standalone package `/Users/jesse/Projects/phigros-chart-mcp`; reviewer owns only `tests/test_independent_review.py`. No package core files were modified by this reviewer. Review continues for the original chart and performance.

**Current result:** all26 independent public-backend witnesses pass, including compact-phrase future reservations. All59 official sources pass a final complete unchanged import/export run on one settled core hash; `independent-corpus-import.json` records the tested package hash per source and source-file preservation. The final report contains one identical core hash for every row, and all source files remain unchanged.

Fixed issues found by independent review:

- Narrow chart_read leaked all notes through lines; returned metadata/tempo references allowed hidden mutation without digest changes.
- Legitimate zero-duration official records were rejected. Rrhar'il IN line1 speed events at raw2202 and2714 illustrate these records.
- Three sources contained zero-speed holds: Stardust:RAY IN, 彩 IN and 玩具狂奏曲 -終焉- AT. These now preserve opaque source-speed semantics and refuse unsupported conversion/edits explicitly.
- Reversed source records in Aleph-0 IN and FULi AUTO SHOOTER IN are now opaque and preserved; they are not normalized silently into authored events.
- Editing an unrelated line reset supplied nonzero floor bases on untouched lines. Untouched lines/channels/notes now preserve their source records; edited floors honor source bases.
- Missing source floorPosition fields incorrectly reset each speed segment to zero. The speed2→4 witness at120BPM now yields cumulative floor2 at raw48.
- Three-point hold sampling missed an interior triangular carrier excursion. Event boundaries inside the hold are now sampled and flagged.
- Sidecar digest tampering now fails import.

Other passing witnesses cover mixed per-line BPM/audio alignment; offset; a hold crossing tempo change; exact two-bar stairs and sequential transforms; hold-speed encoding/speed-boundary integration; restored effect suffix; native four-kind/x/alpha units; detached plan inputs; stale/used-plan atomic rejection; malformed-input atomicity; decorations forbidden to score; hidden carriers targeting visible anchors; export collisions/stale guards; caller-supplied evidence caching and pagination; deterministic gameplay export from varied repeated presets; and guarded revision restoration.

## Edited source compatibility and cost

`independent-edited-compatibility.json` records four real one-note edits. Rrhar'il IN, Stardust:RAY IN, 彩 IN and 玩具狂奏曲 -終焉- AT all preserve existing notes, source event tracks, unrelated lines and source files. Rrhar'il native export succeeds; the three zero-speed-hold sources explicitly refuse unsupported native conversion. Optimized Rrhar'il timings are1.18s import,0.80s plan,0.57s apply,0.63s official export and1.47s native export. Earlier conversion observations of several minutes were superseded by compiled track evaluation, rational caching and event sweep repairs. These are local measured timings, not a model token/cost prediction.

The new compact phrase witness reserves a future L-index hold at beats2–2.5, then requests a continuous drag thread1–3 whose sampled targets1/3 avoid the hold. The initial compiler checked only target vertices and incorrectly reused the same finger through the reserved interval. Whole-gesture overlap now prevents this assignment; the independent regression passes.

Root separately owns `tests/test_public_protocol.py` for actual SDK and fresh-process checks. Original chart originality, carrier geometry and contact QA are now recorded in independent-release-review.md. Passing software checks cannot establish official-level artistic quality or human playability. The compact-agent rubric is separate; no empirical Luna evaluation has occurred.
