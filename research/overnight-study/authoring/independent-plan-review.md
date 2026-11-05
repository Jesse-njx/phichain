# Independent review before study/plan release

Reviewed `design/proposed-original-at-plan.md`, `design/reference-lessons.md`, `research/pattern-ledger.md`, `research/line-roles.json` and the proposed MCP contracts. This review concerns an initial draft plan. It does not introduce a new requirement to hear unavailable audio, obtain human permission, or complete player testing before producing that draft. Root releases workers after verifying study synthesis and the concrete plan.

## Original AT plan

The main architecture now fits the user constraint: one active horizontal playing locus, lateral hand zones on that locus, technical carriers that resolve to it, decorative empty guides, no box/inversion/opposed-axis default. Staging a complete single-axis rhythm/lateral arrangement before effects is implementable. Phrase durations, mapped recovery spans, four-finger ownership hypotheses and later renderer/playtest checks provide useful constraints without promising official quality.

Concrete issues sent to the design owner:

1. **Accepted evidence method contradicts residual listening prerequisites.** Beat390–422 says “Listening must identify” the textural phrase; other rows say “if listening confirms.” The opening section explicitly accepts digital audio/source evidence. Replace these with corroborated attack/sustain/register/energy evidence and conservative unchanged/rest choices when ambiguous. Optional later listening can refine the chart; it is not an initial-draft gate.
2. **Rectangle/split-frame terms can imply a second playing geometry.** Beat240–272 and592–626 use “rectangle”;454–466 uses “split frame.” The architecture paragraph calls them cosmetic, but each local instruction should say empty decorative frame around stations on the same main line. Four hand stations are lateral points, not four input axes.
3. **Rest boundary loses the final source onset.** Beat592–626 acknowledges the last source run around626.125, while626–630 says the source stopped at626. Use the exact final source time, a rounded label explicitly marked approximate, or a deliberately chosen new-chart boundary. Do not call626–626.125 a proven source rest.
4. **Later testing language should not become an approval gate.** Candidate release margins call for “player approval during testing.” They are hypotheses to evaluate during later playtesting. Tight patterns can be flagged for review in the first draft rather than requiring unavailable player permission before drafting.

Also preserve intent rather than source copying: official onsets can support timing, but selecting all source attacks then globally mirroring/retyping would conflict with the originality contract. Phrase-specific gesture/voice choice should remain in the authoring sidecar, including why omitted or added attacks differ. Instrument names may remain provisional. The plan can use observable roles without inventing a bass/lead identity for every spectral band.

## Pattern ledger

Found a concrete false4K example: Igallta IN line1 at98.4130 had local stations[-2,2,-2,2], a two-station alternation, yet its paragraph asserted four symmetric stations[-6,-2,2,6]. Reported to corpus owner; owner corrected the category to require distinct positions, monotonic order and surrounding local station vocabulary, removed this false example, and retained a verified Chronostasis four-station segment. Other four-position stairs are correctly labeled candidates rather than proof of persistent4K layout.

Ledger tuples are source-local evidence. They do not prove the same source line resolves onto a fixed playing anchor, or that its order survives rotation/mirroring. The `jump_then_single` examples can lie on one side of the canvas, so distributing their two fingers across one or both hands remains an execution hypothesis. The corpus owner also corrected that wording. Hold-plus-stream and flick-near-release examples should retain movement/ownership caveats rather than treating same-time tail/head reuse as universally comfortable.

## Line-role evidence

`line-roles.json` gives reproducible static note-count/visibility categories; those categories are not a solved dynamic playing-anchor map.

- Cycle IN:19 multi-note carriers,2 single-note carriers and3 empty-visible lines. This supports the distinction between engine lines, note transport and empty spectacle.
- Der Schneid AT:9 multi-note carriers,5 single-note carriers and10 empty-visible lines; IN:4 multi-note carriers,6 single-note carriers and10 empty-visible lines. Many technical/decorative lines can coexist with a coherent gameplay locus.
- Distorted Fate AT:38 multi-note carriers,4 single-note carriers and4 empty-visible lines. These counts do not establish42 player axes.
- Bounded Quietude has24 note-bearing carriers and no empty lines in this static classification. Some visible guide composition can therefore come from technically scoring lines outside the inspected time interval. Calling every currently empty guide a globally decorative line would be wrong.

Add temporal role intervals and confidence. A line may carry one note elsewhere but be purely visual during a rest. Conversely, a line currently hidden may carry a visible note. Associate scoring objects with a declared playing anchor through transformed target geometry; never infer anchor multiplicity from line count alone.

## MCP contract corrections and final decisions

Corrected the “two bars” example: in declared4beats/bar meter,32onsets at1/4beat fill the8beat selection32–40 (last head39.75). The36–40 mirror affects16 heads. Final-head39.75–40 conversion creates the requested flick ending. The previous16onsets only covered4beats and left the mirror empty.

Planning operations execute sequentially on a prospective editor-independent model, then lower to finalized engine creates/updates. Generated notes receive symbolic IDs during planning; the adapter must not issue updates for unavailable live engine IDs.

Saved a strict public version1 schema proposal in `proposed-authoring-plan.schema.json`: explicit coordinate convention, exact beats, time-basis/head-policy selections, insert_patterns/explicit_notes, transforms and line effects; unknown fields fail. Required semantic checks and sidecar role decisions are documented in `standalone-mcp-architecture.md`. Schema/example JSON parse successfully. Full JSON Schema validation was not run because the local `jsonschema` package is unavailable; this is planning documentation, not evidence that a server tool exists.

Core choices are concrete: standalone Python3.11+ distribution; standard MCP SDK stdio; v3 import/export first; optional v1 later; source-authoritative rational audio time with per-line mapping; immutable offline revisions/digests; optional PhiChain/renderer adapter; one main playing anchor by default. PositionX18/native1350 conversions are explicit adapter conventions awaiting geometry roundtrip tests, not a claim about universal physical viewport coverage.

No implementation has changed during this review. The deprecated exploratory helper remains nonproduction and is not used to evaluate the plan.
