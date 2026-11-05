# Standalone Phigros chart authoring MCP: study and architecture proposal

Status: PLANNING ONLY. Implementation gate remains closed. Written 2026-10-01/02 for review, not a claim of completed tools or official-quality charting.

## Package and responsibility boundary

The proposed final home is a separate project, `/Users/jesse/Projects/phigros-chart-mcp`, with its own package metadata, tests, installation instructions and MCP entry point. It must install and operate without a PhiChain checkout, editor, binary, or running process. No authoring language interpretation or charting guidance belongs inside PhiChain.

A proposed package layout, not yet created:

- `phigros_chart_mcp/server`: standard MCP tool/resource registration and stdio transport.
- `phigros_chart_mcp/model`: editor-independent chart representation and source-preserving import records.
- `phigros_chart_mcp/formats/official`: official Phigros v1/v3 import and v3 export.
- `phigros_chart_mcp/authoring`: explicit patterns, selections, transformations, editable phrase plans, event compilation.
- `phigros_chart_mcp/analysis`: time mapping, musical evidence, geometry, gesture ownership, readability checks.
- `phigros_chart_mcp/resources`: portable authoring guide, study principles and reference manifests.
- `phigros_chart_mcp/adapters/phichain`: optional native format and live editor bridge adapter.
- `tests`: protocol, roundtrip, authoring, geometry and corpus regression suites.

The standalone core owns import, study, plan, check and export. A PhiChain adapter optionally owns conversion into its native format, session/revision reads, guarded transactions and renderer invocation. Other editor adapters can later implement the same capability interface. Lack of an editor never blocks offline Phigros operations.

Existing `tools/phichain-mcp/server.py` is integration evidence and a possible optional adapter consumer, not the final package boundary. Reuse its bridge contracts rather than maintaining a duplicate live state. Do not require importing this repository's Python modules in the standalone distribution. Any extraction/reuse must preserve license requirements and receive tests in the new package. Conversion algorithms should be independent package code; an installed PhiChain converter can be an optional compatibility check, not a mandatory runtime dependency.

Any MCP-capable AI client can use the same server schemas. Codex is one frontend. The agent interprets speech, chooses operations and explains judgments; deterministic server tools compile structured intent. No function claims to parse arbitrary natural language. Agent-specific setup examples are optional documentation, not core behavior.

## Deprecated exploratory code

`/Users/jesse/Projects/PhiChain/research/overnight-study/authoring/exploratory-draft.py` is a 510-line exploratory DRAFT, NOT the proposed package or a tested implementation. Only Python syntax compilation ran. Do not execute its mutating helper against a live editor or use its defaults to generate deliverable charts.

Known flaws discovered by study:

1. Draft opacity accepts 0..1 and defaults to 1, but native PhiChain opacity is 0..255. Native 1 is almost transparent; correct full opacity is 255.
2. Draft active-holds-plus-all-heads rejection confuses raw note objects with independent contacts. Legitimate shared drag/flick/hold gestures can exceed a two-object threshold in IN.
3. Supported easing is limited and the draft does not validate whole approach trajectories or sustained contact ownership.
4. Existing imported fields/easing must be preserved or explicitly reported unsupported, not rejected silently during unrelated edits.
5. No meaningful behavioral tests, protocol tests, package integration or export-equivalence tests have run.

The gate interrupted implementation. Preserve this file as historical draft; do not repair it until root verifies the completed study synthesis and full plan, then explicitly releases workers. Durable guidance and contracts below supersede its assumptions.

## Editor-independent units and source preservation

The public MCP schema must state units explicitly. Core fields use exact musical beat rationals, rational audio seconds with millisecond display, adapter-defined centered chart coordinates, degree rotation and normalized alpha. The position convention below is a proposed logical chart-canvas convention, NOT a claim that official positionX18 units span the physical full screen in every renderer. These are standalone model units, not implicit PhiChain units. A versioned source envelope preserves imported official events and unsupported extensions to support loss-aware roundtrips.

| Public/core field | Unit | Official JSON mapping | Optional PhiChain adapter |
|---|---|---|---|
| `beat` / `duration_beats` | Exact rational canonical triple | Per-line raw time converted through BPM; raw time 32 represents one beat at that line BPM | Native canonical triple; holds use positive duration `hold_beat` |
| `audio_time_ms` / `offset_ms` | Milliseconds | Official offset is seconds | Native offset milliseconds |
| `local_x` | Centered logical chart-canvas fraction; physical renderer scale separately declared | positionX = local_x * 18 as adapter convention, geometry test required | note x = local_x * 1350 under this adapter convention |
| `line_x`, `line_y` | Centered logical line coordinates with explicit viewport transform | Official normalized line coordinate = fraction + 0.5 for v3, subject to geometry tests | x * 1350 and y * 900; runtime y adapts to aspect ratio |
| `rotation_degrees` | Signed degrees | Preserve angle values; coordinate-system convention included in capability response | Native degrees; runtime converts to radians |
| `opacity` | Normalized 0..1 | Official event alpha directly | MUST multiply by 255; native output 0..255 |
| `note_speed_multiplier` | Dimensionless positive multiplier | Nonhold note speed directly; holds require format-specific encoding | Native note.speed directly |
| `line_scroll_speed` | Explicit official-speed units | Official speedEvents.value | Native value = official value * 9 / 2 |
| `side` | `above` or `below` | notesAbove / notesBelow arrays | Boolean `above` |
| `kind` | `tap`, `drag`, `hold`, `flick` | IDs 1,2,3,4 respectively | Native string values |

Core hold approach speed semantics need dedicated conversion design: official hold note speed stores a line-speed-adjusted value. Native export multiplies a hold's note.speed by line speed at the head, while nonholds preserve note.speed. Never claim cross-format speed equivalence based only on field names.

For official import, audio seconds = raw_time * 1.875 / line_BPM + offset_seconds. With global BPM changes, map audio time through the complete map rather than assuming all lines share one BPM. Maintain exact rationals where possible, with explicit numeric tolerances for source floating values.

Sources inspected: `phichain-chart/src/{note,event,serialization,bpm_list,easing}.rs`; `phichain-game/src/core.rs`; `phichain-format/src/official/{into_phichain,from_phichain,schema}.rs`; `phichain-editor/src/mcp{.rs,/quality.rs}`. Native opacity conversion is confirmed by runtime division by255, official import multiplication by255 and export division by255.

## Tool contracts

All tool inputs and outputs include a versioned schema, bounded arrays and unknown-field rejection. Offline chart handles are stable resource references plus content digest; live handles add opaque editor session/revision. Never assume a handle points to unchanged content.

### `chart_capabilities`

Input: `{}`. Output: protocol/schema version, enabled formats, offline capabilities, optional adapters, unit definitions, limits, unsupported features and transport version support. Do not claim editor availability until queried successfully.

### `chart_import`

Input: `{source_uri, format: "phigros_official", mode: "loss_aware"}`. The server resolves authorized local/provider resources, validates schema and returns `{chart_ref, digest, source_format, warnings, loss_report}`. Import preserves source file; it does not launch or modify an editor. Source-preserving import records distinguish authored IR from the original.

### `chart_read`

Input: `{chart_ref, digest, selection: {time_basis: "beat"|"audio_ms", start, end, line_ids?}, include_overlapping_holds: true}`. Output: IDs and complete note/event values, beat/audio mappings, visibility/motion context, source provenance and current digest. Holds beginning before the range and ending inside it are included. A note's head-selection policy remains explicit for transformations.

### `authoring_reference`

Input: `{reference_id, passage: {start_ms,end_ms}, requested_evidence: ["notes","line_events","metrics","commentary"]}`. Output: bounded passage, chart/source hash, title/difficulty, dates and date confidence, attribution, findings, media if available, and limitations. Study resources are portable server resources, not Codex-only paths. Raw note count is always labeled raw object count.

### `authoring_plan`

The following is an example instance illustrating the proposed schema; it is not executable code or a final schema:

```json
{
  "schema_version": "1",
  "chart_ref": "chart://example",
  "coordinate_convention":"phigros_logical_v1",
  "digest": "0000000000000000000000000000000000000000000000000000000000000000",
  "selection": {"time_basis":"beat","start":[32,0,1],"end":[40,0,1],"line_ids":["line-a"],"head_policy":"heads_in_range"},
  "musical_context":{"beats_per_bar":4,"bar_count":2,"subdivision_beats":[0,1,4]},
  "operations": [
    {"type":"insert_pattern","pattern":"stairs","start":[32,0,1],"onset_count":32,"step":[0,1,4],"lane_x":[-0.27,-0.09,0.09,0.27],"lane_order":[0,1,2,3],"note_kind":"tap","side":"above","note_speed_multiplier":1},
    {"type":"transform_notes","selection":{"time_basis":"beat","start":[36,0,1],"end":[40,0,1],"head_policy":"heads_in_range"},"mirror_local_x":true},
    {"type":"transform_notes","selection":{"time_basis":"beat","start":[39,3,4],"end":[40,0,1],"head_policy":"heads_in_range"},"note_kind":"flick"}
  ],
  "intent":{"difficulty_family":"IN","preferred_contacts":2,"musical_role":"keyboard phrase","reference_passages":[],"generation_mode":"regular_single_playing_anchor"}
}
```

This example explicitly assumes4beats per bar. Thirty-two onsets at1/4beat cover beats32 through39.75 in the8beat interval32–40. Mirroring36–40 affects16 heads; converting39.75–40 changes the final head to flick. The earlier16-onset draft covered only4beats and left the mirror selection empty; this corrected example supersedes it.

Plan operations evaluate sequentially against a prospective editor-independent model, including generated notes. Generated objects get stable symbolic IDs during planning. Lowering creates their final transformed versions once; it never emits native updates referring to not-yet-created engine IDs. Inherited top-level line selections constrain nested selections unless explicitly narrowed.

Operations support explicit note sequences/chords, all four note types, stairs with editable lane order, alternating/paired streams, sustained holds, drag paths, flick accents, translations/mirrors/scaling, speed edits and line x/y/rotation/opacity/scroll effects. Do not make all note types mandatory in every phrase. Hand/gesture annotations live in editable authoring sidecars and never silently alter gameplay semantics.

Output: `{plan_ref, source_digest, target_adapter?, proposed_operations, affected_ids, unchanged_field_policy, phrase_boundaries, findings, assumptions, unsupported_features, estimated_cost, preview_requirements}`. Live plans also include session/revision. No mutation occurs. Agent must resolve material ambiguities before requesting a concrete plan. Missing meter is not guessed as musical fact.

### `authoring_check`

Input: `{chart_ref|plan_ref, aspect_ratios:[...], gesture_policy, requested_checks:[...]}`. Output findings with severity, evidence class, code, IDs, interval, geometry and actionable interpretation. Hard errors cover invalid schemas, nonfinite values, malformed beats, invalid references and unsupported conversion that would lose required data. Physical/visual judgments are warnings or explicitly uncertain conclusions unless demonstrated by a defined model and assumptions.

Separate metrics: raw heads, fresh strikes, active sustain intervals, shared-gesture candidates, assigned independent contacts, hand travel, recovery windows, approach exposure, landmark visibility and event-boundary discontinuities. Never encode `max_contacts` as raw-object count. Gesture matching is a candidate analysis, not a proof of feasible player execution.

### `authoring_apply`

Input: `{plan_ref, source_digest, adapter:"offline"|"phichain", guard?, transaction_policy:"single_atomic"}`. Offline mode creates a new edited chart handle and preserves source. Live mode requires fresh session/revision and creates exactly one atomic transaction, at most1000 native operations. Update-note/event operations replace full objects with unchanged fields preserved. A revision mismatch rejects without editing. No automatic saves, broad deletes, undo or retries.

Larger live plans split by explicit phrases, with a fresh read/replan for each atomic transaction. A transport failure has unknown outcome: return an indeterminate receipt, read current state/history, and never blindly retry. If another actor changed the chart, regenerate the plan rather than attaching a new revision to stale operations.

### `chart_preview` and `chart_export`

Preview input includes passage and sufficient approach lead-in/release follow-through, viewport/aspect and renderer capability. Standalone renderer is a separate optional implementation milestone; do not claim preview exists merely because import/export exists. A PhiChain renderer adapter may provide optional preview. Export requires target format and conversion policy, produces a new artifact, reports loss/precision changes, and runs roundtrip checks. Official Phigros export must work offline without PhiChain.

## Utterance to agent/tool orchestration

“Make a four-lane ascending stair for two bars, mirror the last bar and finish with flicks.” Read chart/meter/selection, resolve subdivision, compile exact lane order and boundaries, preserve all unrelated fields, run check, apply one concrete plan, preview approach and recovery.

“Keep the sustained left hand and add a right-hand melody.” Read holds crossing the interval, preserve IDs/tails, annotate intended contact ownership, author the independent voice according to audio evidence, check moving world-space holds and melody travel/release windows. Do not infer capacity from raw note objects.

“Make it faster.” Agent distinguishes tighter beat spacing (rhythmic density), larger note_speed_multiplier (approach distance) and faster line_scroll_speed/rotation/translation (scene motion). Existing context may resolve intent; otherwise this is a necessary semantic clarification. Choosing one silently changes a different property.

“Have these notes fly in from the right.” Agent states whether this means a static line perpendicular to rightward flight or moving/rotating trajectory. With static line angle theta and positive scroll, above-note approach direction is (sin(theta),-cos(theta)); below is opposite. A moving line changes world trajectory. Native formats do not encode an enforced directional flick swipe; do not invent one.

## Corpus-grounded requirements

Evidence derives from `corpus/manifest.json`, `corpus/metrics.json`, original chart files and `research/atlas/index.json`. The atlas is an analytical transform/approach view, not a judgment simulation or human playtest. Specific notes below are quantitative evidence or visual observations; interpretation remains marked.

- Rrhar'il IN and AT both contain1300 notes. IN tap/drag/hold/flick=802/410/53/35; AT=991/44/123/142. Support gesture replacement, sustained ownership and accent roles without count targets.
- Distorted Fate IN1449 vs AT1283 notes; IN holds132 vs AT212 and lines24 vs46. IN drag sweep near108s contrasts with AT sustained-contact passages around110–120s. Support independent voices and scene choreography, not uniform densification.
- Igallta IN1018 vs AT1114, with holds27 vs115. Selection must include holds crossing boundaries and retain duration/ownership during edits.
- Bounded Quietude IN90.8571s has four objects (two taps+two drags); Stardust:RAY IN122.9268s has eight (four drags+two taps+two flicks); Hydra AT34.5s has four holds+four flicks. These are mandatory counterexamples to “objects=fingers.”
- Entrance to the Chaos IN/AT and Exoplanetary Mirage IN/AT atlas comparisons show distinct changes in drag streams, holds, taps and line count rather than one difficulty multiplier. Tools need per-phrase voice and gesture decisions.
- Decorative lines and scoring lines must be distinguishable in selection, summaries and checks. Number of event rows/lines does not itself establish visual complexity or quality.

A full-song phrase map, audio alignment and references are prerequisites for original chart creation. Templates are editable motifs, not a replacement for musical decisions. Server guidance should ask for a phrase's source voice, intended gesture, landmark and recovery, while preserving deliberate rests.

## Testing and implementation gates

1. Study gate: corpus coverage/date/provenance audited; real chart passages inspected; plan reviewed. No chart creation or implementation until root verifies completed study synthesis and the full plan, then explicitly releases workers.
2. Protocol tests: independent clean installation without PhiChain; MCP initialize/list/call/resource behavior; JSON schema errors; bounded requests; offline tools available while adapter unavailable; no editor launched by offline import.
3. Format tests: official v1/v3 import, v3 export; kind IDs; offset/time/BPM; above/below; holds; opacity0/0.5/1; x/y mapping; rotations; source preservation and explicit unsupported/loss behavior. Use source hashes and meaningful tolerances.
4. Adapter tests: native alpha0/127.5/255; line speed conversion; hold speed encoding; native deserialize; static/moving holds; cross-aspect position checks. A native hold integrates changing line scroll; official export samples onset speed. Compare actual appearance, not timestamps alone.
5. Authoring tests: exact fractional stairs/custom lane order, boundary transforms preserving hold duration and unrelated notes, chords/all types, event replacement/overlap behavior, pattern edits and reproducibility.
6. Geometry/gesture tests: parents and rotations, all lines globally, holds entering/leaving selection, shared drag/flick candidate groups, release ordering, hand travel, lead-in visibility, overlap/occlusion. Preserve legitimate corpus counterexamples; do not promote heuristics into hard contact proofs.
7. Transaction tests: stale guards, ID collisions, duplicate targets, partial/incomplete snapshots, generated endpoints,1000-op boundary, concurrent user change and indeterminate transport. No retry/save/undo side effects.
8. Quality gate: full-song audio phrase evidence, intended hand assignments, high-risk passage previews, alternate aspect previews, export roundtrip and honest remaining playtest limitations. Passing numeric checks never establishes official quality.

## Recommended concrete decisions

- **Runtime/package:** Python3.11+ with a separate `pyproject.toml`, installable CLI `phigros-chart-mcp`, the official Python MCP SDK for standard stdio transport and JSON Schema tool registration. Resolve and lock an SDK release during implementation from primary package documentation; no assertion of a latest version or untested pin is made here. Target the existing bridge-compatible MCP protocol2025-11-25, with negotiation/error tests. Optional other transports are a later milestone.
- **Initial formats:** official Phigros v3 import/export is the first mandatory milestone. v1 import is a later optional stage, explicitly unavailable in capabilities until tested. The optional PhiChain adapter supports format6 after native fixture tests; it is not required for offline operation.
- **Timing representation:** internal source-authoritative audio times are exact `Fraction` rational seconds constructed from source decimal values, not rounded native beats or binary floats. Each imported line retains its BPM and source raw-time mapping. The editable musical tempo map maps exact audio times to exact beats; meter/phrase annotations remain separate from absent source metadata. Serialization uses numerator/denominator integer pairs with bounded integer sizes and source decimal provenance. Public authored beats use canonical triples. Adapter quantization has a stated tolerance/loss receipt and can refuse conversion if unsupported; do not silently cap precision.
- **IDs/state:** server-owned UUID chart/object handles plus immutable revision/content digests. Live engine IDs remain opaque adapter IDs. Offline edits create new revisions and preserve imported source. Plans store the exact base digest; every application checks it.
- **Schemas:** public version1 JSON Schemas require explicit time basis, coordinate convention, selection head-versus-overlap policy, and operation type. Unknown fields fail validation. Arrays are bounded; single live batch limit1000. Schema changes become a new version rather than silently reinterpreting units.
- **Preview:** initial offline core supports data/arrangement/presentation study artifacts and official export. Gameplay-video preview is a declared optional capability supplied by a renderer adapter, initially PhiChain if installed. A standalone renderer is a later milestone; no editor availability is required for import/plan/check/export.
- **Gesture model:** explicit optional voice/hand/contact IDs, sustain intervals and candidate shared gestures. Candidate inference is advisory. Hard failure based on finger capacity requires an authored contact assignment and a clearly stated model; raw objects never define contacts.
- **Preservation policy:** loss-aware import retains source fields. Unrelated edits pass through supported and opaque unchanged source data. Modifying unsupported timing/easing/gameplay features fails with specific IDs and a loss report; the server never silently rewrites them.
- **Default layout:** one active main playing anchor, with technical note carriers and empty decorative lines. Special box/inversion/opposing modes are explicit. Main-axis projections preserve actual physical target separation and retain local/mirror/source provenance.

Implementation proceeds after root verifies the completed study synthesis and full plan, then explicitly releases workers. The user requested study and planning before building; this does not create an additional approval question or permission requirement.

## User-directed regular-chart baseline and two study views

Latest steering supersedes any assumption that multiple moving judgment axes are a default target. Study regular charts by squishing the arrangement onto the main judgment line, with a generally single falling axis. The default authored result is a simple, coherent single-axis chart. Aesthetic line motion may decorate phrases without remapping each one. Complexity must arise from music and meaningful gestures before unusual presentation is considered.

Add a standalone `chart_arrangement_view` tool distinct from `chart_presentation_view`:

- Arrangement view preserves exact timing, note roles, hold duration, voice/source-line identity, phrase relationships and lane/local ordering. It factors presentation transforms away rather than projecting every world-space note onto world x. It displays raw roles, sustain ownership and motif changes on a canonical main axis.
- Presentation view retains original line position, rotation, opacity, scroll and side. It reports real approach trajectories, orientation changes, overlap and spatial cues. Preserve both views; they answer different questions.
- Local coordinates and source line/order metadata survive flattening. A defined anchor/main-line coordinate system and explicit mapping explain whether ordering was preserved, mirrored or reassigned. No automatic arbitrary lane remapping is disguised as analysis.
- When multiple source lines share a local position at one time, retain separate source objects and gesture candidates. Coincident canonical points do not prove duplicate gameplay objects or independent fingers.
- Opposing-side notes can be displayed on one study axis only with original side retained as provenance and a clear analysis-only label. Concurrent opposing flights remain a presentation feature; do not silently convert them in an exported chart.
- A reversible analysis view is different from the authored `flatten_for_export` operation. The latter requires an explicit proposed mapping, collision/contact review, preservation/loss report and user-requested scope.

Proposed view request (schema illustration):

```json
{
  "chart_ref":"chart://example",
  "digest":"source-content-hash",
  "mode":"canonical_arrangement",
  "anchor":"main_judgment_line",
  "axis_policy":"single_falling_axis",
  "position_policy":"preserve_local_order",
  "retain_provenance":["source_line","side","voice","original_local_x"],
  "apply_to_chart":false
}
```

Output includes mapping rules, ambiguous/colliding groups, note-role timeline, stable ordering, holds and source provenance. If line-local coordinates cannot produce a defensible common arrangement without musical interpretation, expose the unresolved mapping instead of fabricating one. World-x projection is an optional explicitly labeled diagnostic, never the default flattening method.

The user identifies box layouts (Horizon Blue IN15, Shadow AT16), inverted presentation (Chronostasis), and concurrent opposing directions (Fully Auto Booster14, No One Yes Man, plus an unresolved title spelled “C-L-E-Y-E-R-A”) as special cases. Treat these as requested reference categories, not as already-verified chart facts beyond the inspected corpus. Resolve the unknown title before attaching provenance.

`generation_mode` defaults to `regular_single_axis`. `special_gimmick` must be requested or specifically proposed with musical/readability reasons. Box, inverted and opposing-direction modes need their own arrangement/presentation comparison, hand-contact plan, approach cues and recovery review. A chart family’s exceptions do not make those presentation patterns mandatory in ordinary generation.

Required tests: inverse-transform/canonical-order invariance under translated/rotated decorative lines; stable phrase ordering over motion; preserved hold tails/types/timing; provenance retained for opposing sides; ambiguous multi-line groups reported; analysis view never mutates source; export flattening explicitly distinct; regular defaults never introduce box/inversion/opposing-flight layouts accidentally.

### Clarification: physical target separation and main-axis projection

Refinement after review: preserving local x alone is insufficient. It discards meaningful line translations and separation between voices. For regular horizontal scenes, canonical arrangement should preserve actual physical judgment x after line transforms, projected onto a declared stable main-axis reference, while retaining source-local x and line/side provenance. This is a defined projection onto the main judgment axis, not indiscriminate world-x flattening across every rotating/box/opposing scene.

The mapping record therefore includes `main_axis_origin`, `main_axis_direction`, `time_reference_policy`, original world judgment position, projected position, original local x, hierarchy, source side, mirror/sign/permutation and ambiguities. A translating main axis may require factoring out shared scene translation while keeping relative target separation; the tool must state that choice. Rotations or independent line motion can alter ordering; preserve that evidence and flag unresolved authoring remaps. Never claim that flattening necessarily preserves physical difficulty.

A canonical mapping policy can be `physical_main_axis_projection`, `source_local_order`, or an explicitly authored lane map. Default for ordinary horizontal arrangements is physical main-axis projection with local provenance, one active playing_anchor and any number of technical carriers/decorative lines. No policy is silently chosen for ambiguous special scenes.

The unresolved title has now been identified as **Cleyera** by root study, with reference https://wikiwiki.jp/phigros/Cleyera. This resolves naming only; opposing-direction behavior still requires passage-level inspection before it becomes an asserted study finding.

## Stronger default: one main playing line, with technical carriers

Latest user clarification makes the regular default **one main playing judgment line at a time**, not merely parallel rails sharing a falling direction. Multiple engine lines do not imply multiple gameplay axes. Technical lines can subtly move notes left/right; dedicating one note to its own carrier line is valid. Empty lines provide pure aesthetics.

Add semantic roles in server authoring metadata:

- `playing_anchor`: the active visible main judgment locus for an interval. Regular mode has exactly one active main playing anchor at any scoring time. Planned anchor transitions include explicit intervals and cues.
- `note_carrier`: an engine line owning one or more notes and their approach/motion. A one-note carrier is an ordinary implementation choice. It targets a declared playing_anchor with an explicit placement/convergence plan.
- `decorative`: no scoring notes or generated scoring curves. It may be visible/invisible and move without consuming contact capacity.

These are MCP concepts and sidecar annotations; no change to PhiChain frontend or official gameplay schema is required. Adapters compile line structure and preserve role metadata separately. Treat source role inference as a hypothesis, especially when carriers and anchors are visually coincident.

A `note_carrier` is checked against its declared anchor at judgment: transformed target position, orientation when relevant, timing and allowed locus span. A hidden technical line is acceptable when the note remains visible and converges coherently onto the visible main anchor. Do not emit a blanket invisible-line warning merely because the note's owning carrier is hidden. Check the assigned playing_anchor and note visibility separately.

Runtime evidence: PhiChain `phichain-game/src/core.rs` sets opacity on the line Sprite color; note positions are child transforms, while note sprites have their own visual state. A zero-alpha carrier Sprite does not itself multiply opacity into child Sprite colors. Actual renderer/device previews remain required to verify note visibility, cover behavior and chosen approach window across exported formats. Opacity alone must not be conflated with hierarchy Visibility components.

Role-aware checks distinguish: anchor absent/invisible at hit, carrier miss of declared anchor, note hidden before sufficient cue, decorative/scoring misclassification, intentional versus accidental multiple active anchors, and continuity through sustained holds. Check hold contact throughout its active interval, not just head/tail or the carrier's original x. A main anchor's shared scene motion can be factored out for arrangement study while relative targets remain physical.

Long sustains plus empty aesthetic lines near the end of an AT17.5 reference are consistent with studying Der Schneid AT, whose corpus count contains232 holds versus IN61. Treat the user's identification as a study lead; do not infer the exact empty-line role or ownership of ending holds from counts alone. Inspect the passage and original line-note arrays.

Tests add: one-note carriers converging onto one anchor; hidden carrier/visible note; empty decorative lines excluded from scoring axes/contact counts; carrier translation preserved in physical arrangement view; anchor changes explicit and cue-checked; many engine lines with one playing anchor accepted; unplanned second anchor flagged; sustained contacts checked against active anchor over time. Generation may use many carrier lines internally while retaining one coherent main playing line.

## Public v1 planning schema and semantic checks

The proposed strict JSON Schema is `proposed-authoring-plan.schema.json`. It is a planning contract, not an implemented tool. The example above conforms to its field structure. Required `coordinate_convention=phigros_logical_v1` labels logical positions; physical geometry still needs adapter/viewport tests. Regular intent explicitly uses `regular_single_playing_anchor`. No “two bars” compiler infers meter: `musical_context` states4beats/bar,2bars,1/4beat subdivision.

Mandatory semantic checks beyond JSON Schema: end exceeds start; hold duration/step are positive; beat numerator < denominator; lane_order indices exist; alternating uses two stations; transform has at least one requested change; transforms selected by head preserve hold duration unless explicitly converted away from hold; coordinate/scroll channel matches unit; normalized alpha0..1; zero/negative line speed requires explicit special-mode findings; event overlap replacement is explicit and source-preserving; inherited line selection constrains nested operations; unknown or generated endpoint IDs fail with specific findings.

Effects are edits of event tracks, not additive overlays hidden behind native maximum-value semantics. A nonreplacement overlapping event is refused. Explicit replacement splits/trims affected source intervals and restores their inherited state afterward, with event continuity/loss evidence. Offline export must preserve inherited values in gaps; compatibility tests ensure the native exporter’s gap-filling policy does not accidentally reset the scene.

Initial pattern names are stairs, alternating, chord and drag_path; arbitrary syncopation/mixed roles use explicit insert_notes. Reusable voice-pattern sequences are a subsequent extension of the same model, not an NLP parser. Role assignments are versioned sidecar scene metadata read by checks/placement planning; their first schema requires line/object IDs, interval, role, declared anchor reference, target placement and inference confidence. Static note-count roles are evidence only; dynamic active-anchor inference remains annotated.

## Portable guidance, optional references and common-backend demonstration

The independently installed server bundles a portable authoring guide, pattern vocabulary, unit/capability guide and small derived reference examples as standard MCP resources/prompts. Resource identifiers are server-owned (for example `phigros-authoring://guide/v1`), not hardcoded PhiChain/Codex filesystem paths. A client can request a bounded passage example with timing/type tuples, source attribution, evidence class and uncertainty. Examples teach generic roles; full official chart/audio collections are not mandatory package data.

The large study corpus remains an optional configured `reference_directory` with a manifest/digests. Installation succeeds and the server's ordinary offline authoring tools operate when no corpus is present. Reference tools report which examples are bundled and which original assets are unavailable. No implicit download or dependency on this checkout. Any later distribution of source assets must retain appropriate attribution/license constraints; derive small guide examples instead of packaging the full media corpus by default.

The standard MCP prompt `author-chart-phrase` (proposed name) links capability/units resources, regular-single-anchor defaults, role-aware study/check workflow and reference uncertainty. It is optional client guidance, not a server pretending to parse arbitrary utterances. Tool contract behavior does not depend on a specific prompt, model or Codex installation.

The eventual original AT must exercise the same standalone backend and MCP protocol that other agents receive. The artist supplies editable structured phrase recipes and annotation decisions; a protocol client invokes chart_import or empty-chart creation, authoring_plan, authoring_check, authoring_apply and chart_export. Persist tool arguments, base digests, receipts and artifact references as an authorship/reproduction ledger. A proprietary song-generation script that directly emits native JSON and bypasses these tools does not demonstrate the requested authoring workflow.

The implementation demonstration can still automate calls: a deterministic MCP-client recipe replay is appropriate. It must go through public tool schemas and recorded revision checks, reuse the shared pattern/effect/compiler backend, and produce the same results as another agent/client. No duplicated song-specific compiler. Native project creation and previews are optional adapter actions after the core authored chart exists; the official v3 export comes from the standalone package.

Minimum end-to-end protocol demonstration after release: clean install without PhiChain; create/import an offline chart; use a two-bar corrected stair recipe and mixed hold/drag/flick voice example through planning/apply; inspect/check resulting revisions; export officialv3; reimport and compare timing/type/geometry/alpha under explicit tolerances. Then the original full-song phrase recipes run through that same route. Full-song musical/physical review remains separately reported; protocol success does not prove chart quality.

### Required offline empty-chart creation contract

Add `chart_create` to the initial core surface so original authoring does not depend on importing/recoloring an existing arrangement. Input: `{schema_version:"1", metadata:{title,composer?,charter?,difficulty_label?}, tempo_map:[{beat,bpm}], offset_ms, musical_context?, audio_reference?, coordinate_convention:"phigros_logical_v1", initial_scene:{playing_anchor:{name,line_x,line_y,rotation_degrees:0,opacity:1,line_scroll_speed}, generation_mode:"regular_single_playing_anchor"}}`. Tempo map begins atbeat0 and is strictly increasing; BPM positive finite. Metadata does not require inventing unknown authors. Audio is optional for general authoring; lack of audio disables evidence checks and is reported explicitly.

Output: `{chart_ref,digest,object_ids,capabilities,warnings}` with a new empty chart revision and one main anchor ID. All values use the public/core unit conventions. The regular initial scene is horizontal, visible and single-anchor; optional role-aware carriers/decorations are later planned operations. Creating an offline chart never launches an editor, changes imported files or implies a publish action. The original artist can initialize tempo/offset from verified source evidence while retaining the IN/SP charts solely as study references.


## Implementation handoff, October 2

Root released the completed study/plan gate. Production package is independently installed at `/Users/jesse/Projects/phigros-chart-mcp`; this architecture remains historical design, and package-discovered executable schemas are the actual public contract. Public names differ from some proposal names above. No live editor bridge is implemented; optional offline native export and a bounded renderer CLI adapter are available.

Cheap repeatable creation now uses local `evidence_import` records, compact `authoring_plan_phrase` configurations, cached bounded evidence reads, server-side motif expansion with cross-phrase annotated ownership, and persisted recipe/evidence sidecars. Normal explicit plan/apply remains available for repairs/carriers/decorations. Initial logical geometry checks use compiled channel tracks with source-overlap semantics preserved; no continuous approach simulation or human feasibility claim is made. Future Luna natural-language evaluation cases are bundled separately; no Luna model run or quality result is claimed. No final package dependency on the full reference chart/audio corpus is introduced.
