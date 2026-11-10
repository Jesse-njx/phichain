# Chart speed profiles

Analyze and record a chart's rules once, then generate speed variants with one
command. Python 3.9+ standard library only. Generation needs no LLM, network,
editor, MCP host, renderer, converter executable, installation or API key.

## Official originals and reviewed sidecars

The `apply` route accepts an official original JSON and a separate pinned rule.
At **1x it copies the original bytes directly**: it does not read the sidecar,
parse/validate the chart, run the transformer, or repair opacity. This also works
for charts whose original timelines the transformer does not support.

```sh
python3 agent-tools/chart-speed/chart_speed.py apply original.json --rule rule.json --multiplier 1.25 -o variant.json
python3 agent-tools/chart-speed/chart_speed.py apply original.json --multiplier 1 -o unchanged.json
```

The sidecar contains the original `source_sha256` and either `schema_version: 1`
with a `policy`, or `schema_version: 2` with per-line approach `plans`.
Optional `metadata` records the title and review
limitations. Non-1x generation rejects a source hash mismatch. JSON output can
then be packaged with unchanged music/illustration by the caller. This route
does not fetch or upload official resources or call an LLM.

The 47-chart review records and independent coordinator verification are under
`../deployments/chart-speed/batch-20261102/`. Candidate sidecars are provisional mechanical
results, not visual or player approval; read their chart-specific limitations.
Do not silently substitute a diagnostic policy for a blocked chart.

### Schema 2: final-approach helpers

Each original line has a plan with `line`, `whole_line`, `direct`, `helpers`,
`preserve`, and a `reason`. Whole-line plans scale ordinary scroll on the original
carrier. Otherwise the three arrays partition every original note exactly once;
addresses use `side` and `note` indices. `direct` changes a non-Hold's speed;
`preserve` keeps the complete original object and carrier trajectory. A helper
entry additionally records `start` and `visible_from` in line-local ticks.

For a helper note with head time T, approach start A, and multiplier X:

```text
B = T - (T-A)/X
w(t) = t              for t < A
       A              for A <= t < B
       T + X*(t-T)    for B <= t < T
       t              for t >= T
```

The hidden helper replays the original movement, rotation and scroll at `w(t)`.
This preserves earlier staging, then delays and accelerates the reviewed final
approach, returning to the original contact clock at T and throughout a Hold.
It carries the original note, not a duplicate. Notes sharing a head/start on the
same source carrier share a helper. Original visible line animation remains exact.
Helper alpha is clamped to at most zero forever, retaining negative-alpha note
visibility semantics. Before the conservatively determined `visible_from`, the
helper is offscreen and hidden. No runtime visibility inference or LLM is used.

Schema 2 supports speed-up only within its pinned range (currently 1–2x). Plans
are source-hash guarded. Zero/reverse/impulse arrivals and authored special offsets
may remain unchanged; a zero-duration regular approach is not invented. A moving
or rotating carrier alone is not an exclusion. 1x bypasses all these operations.

Current records: `../deployments/chart-speed/batch-20261102/revision-3/`. The final batch
contains 47 schema-2 rules plus the accepted proportional Rrharil behavior bridged
to its official source. About 94% of all 70,937 notes are selected; chart-specific
coverage is recorded, and some charts retain considerably more exceptions.
Numerical verification is not player/visual approval. Discontinuous animation
boundaries can differ by floating-point left/right selection at about 1e-12 ticks;
neighboring samples and judgment/contact geometry were checked separately.
Original real-time block-area masks are retained; their visual interaction with
accelerated geometry and mobile rendering performance remain unverified.

Dense helper animation can make large JSON: the largest current case is about
111.6 MB, compressed to 11.3 MB before media. Generation measured about 800 MB
peak process memory on macOS. Consumers must budget memory and execution time,
run one isolated conversion at a time, and delete temporary outputs.

### Expanded IN/AT 16.0+ registry

The follow-up batch `../deployments/chart-speed/batch-16plus-20261102/` adds the remaining
39 charts (28 IN, 11 AT) in the pinned v4.0.1.2 catalog at rating >=16.0. Each has
its own agent review and source-pinned rule, followed by coordinator checks.
Together with the earlier 48 rules this covers 87 charts (42 IN, 45 AT).
The catalog is pinned; these counts do not claim to track future game updates.

Aleph-0 IN contains two backwards constant-zero opacity records. They are retained
exactly on the original carrier, rather than repaired or reordered. Validation
permits only this constant-zero opacity case; reversed motion/rotation or nonzero
opacity ranges remain rejected. For a helper whose source alpha endpoints are all
nonnegative, clamping alpha to zero is identically zero: emit the hidden constant
directly, avoiding interpolation of malformed legacy opacity records. Negative
alpha note-visibility semantics continue through the original replay path.

Some charts have many special arrivals: Message AT retains 383/777 notes. The
largest new helper-heavy case is +ERABY+E CONNEC+10N IN, about179MB JSON and21MB
compressed before media. Report actual coverage and test resource limits rather
than describing every chart as almost fully accelerated or player-approved.

### Legacy compiled Rrharil bundle

The older `generate`/name-based examples below retain compiled-baseline identity
for compatibility. They are **not** the official-original 1x bypass. Official
requests, including Rrharil 1x, must use `apply` with the actual official original
instead of the historical native-export baseline.

The current local **Rrharil AT** profile reuses the original-line 130% behavior
the user accepted and adds explicit transparent tails to fix lingering carriers.
It retains all 24 lines, 1,300 notes, their line membership, judgment times,
positions, types, Hold durations, BPM and audio offset.

```sh
# Run from the repository root. 1.5 means 150% of the original scroll speed.
python3 agent-tools/chart-speed/chart_speed.py "Rrharil AT" --multiplier 1.5

# The corrected 130% package; repeated identical commands reuse the same output.
python3 agent-tools/chart-speed/chart_speed.py "Rrharil AT" --multiplier 1.3

python3 agent-tools/chart-speed/chart_speed.py list
python3 agent-tools/chart-speed/chart_speed.py "Rrharil AT" --multiplier 1.7 --dry-run
python3 agent-tools/chart-speed/chart_speed.py "Rrharil AT" --multiplier 1.4 -o /tmp/rrharil-140.json
```

`generate` is an optional explicit subcommand before the chart name. `--speed`
is an alias for `--multiplier`. Use an absolute script path to run from another
working directory; the default registry/output locations remain repository-local.

Default output: `../deployments/chart-speed/outputs/<profile-id>/<profile-id>-scroll-<percent>.pez`.
Use `-o` for JSON or PEZ elsewhere. Different existing output bytes require
`--force`; an identical output is reused without rewriting. Original sources,
media and compiled bundles cannot be overwritten, including through aliases.
Publication is atomic. A dry run computes and verifies without creating output
directories/files. Errors exit nonzero without silently choosing another chart.

## One-time compilation

Recipes are explicit review results, not automatic artistic judgments. A person
or agent supplies a rule for **every original line**, optional individual speed
event overrides, an allowed multiplier interval, the source hash and review
notes. Compile this once:

```sh
python3 agent-tools/chart-speed/chart_speed.py compile path/to/reviewed-recipe.json
```

The compiler makes an immutable bundle in
`../deployments/chart-speed/profiles/<id>/`: original source bytes, corrected 100% baseline,
audio, cover and a manifest containing hashes and equations. Every generation
starts from that baseline; generating 150% after 130% does not produce 195%.
Hashes are checked on every run. A changed chart needs a newly reviewed,
versioned profile; compilation will not replace an existing one. `--profiles`
selects another registry. Song content and profiles stay under the workspace outside this repository.

Minimal recipe for a **one-line synthetic chart** (provide all actual lines in a
real chart). Asset paths are relative to the recipe, not the current directory:

```json
{
  "schema_version": 1,
  "id": "example-at-v1",
  "name": "Example AT",
  "aliases": ["example-at"],
  "source": "source.json",
  "source_sha256": "<64 lowercase hex characters from the reviewed file>",
  "music": "music.ogg",
  "illustration": "cover.png",
  "metadata": {
    "level": "AT", "difficulty": 0, "charter": "Original charter",
    "composer": "Original composer", "illustrator": "Original illustrator",
    "aspectRatio": 1.7777777777777777, "backgroundDim": 0.6,
    "lineLength": 6, "offset": 0, "holdPartialCover": false
  },
  "policy": {
    "multiplier_range": [0.5, 2],
    "transparent_tails": true,
    "lines": [{"line": 0, "gain": 1, "reason": "Reviewed ordinary approach"}],
    "review": "Record the actual coverage, user feedback and remaining limits."
  }
}
```

JSON input must be official `formatVersion: 3`. RPE, native PhiChain, v1 and fake
note extensions are rejected. Export those deliberately before compiling. This
is a stateless conversion tool, not another chart authoring session or server.
Input music/cover bytes are copied without decoding; they must already be valid
media matching their extensions. Credits/metadata are supplied explicitly and
retained; generated titles include the percentage. No new rating is inferred.

## Equations and constraints

For speed event `j`, with original value `v[j]`:

```text
factor[j](X) = 1 + gain[j] × (X − 1)
v_out[j]    = v[j] × factor[j](X)
F_out(t)   = integral of the output speed from 0 to t
note.floorPosition_out = note.floorPosition_base + F_out(T) − F_base(T)
hold.speed_out         = hold.speed_base × factor[event active at T](X)
```

`T` is the original head time. Each line's own BPM converts official ticks to
seconds (`seconds = ticks × 1.875 / BPM`). Ordinary note-speed fields remain
unchanged; official Holds carry absolute speed, so they are adjusted separately.
Authored floor offsets/source floating-point residuals are retained rather than
silently snapped away. Event floor positions are recomputed from the integral.
Negative speeds keep their direction and zero-speed stops remain zero. Speed
event timing, motion, rotation and opacity keyframes are not retimed.

Gain 1 gives `X`; gain 0 preserves the speed; intermediate gains provide an
explicit partial response. Other finite gains are accepted only if their affine
factor stays positive over the complete allowed multiplier interval. An optional
`events` array on a line rule overrides individual **speedEvents indices**:

```json
{"line": 0, "gain": 1, "reason": "Ordinary approach", "events": [
  {"event": 12, "gain": 0, "reason": "Keep this reviewed release impulse"}
]}
```

For a mixed carrier, keep its line gain and every speed-event gain at zero and
select reviewed ordinary **non-Holds** independently:

```json
{"line": 0, "gain": 0, "reason": "Preserve shared staging and Holds", "note_gains": [
  {"side": "notesAbove", "note": 12, "gain": 1, "reason": "Reviewed ordinary approach"}
]}
```

This applies `note.speed_out = note.speed_original × (1 + gain × (X − 1))` only
to selected objects. Every unselected note and the entire shared scroll timeline
remain byte-for-field identical, so their original trajectories are protected
over their full lifetime, not merely at sampled timestamps. Motion, rotation,
opacity, floor positions, note membership and original line count stay unchanged.
Per-note gains cannot be combined with nonzero line/event gains, cannot target a
Hold, and cannot change an explicitly protected note window unnoticed.

This is a per-object selection, not time-varying final-approach gating. Selected
notes' distance histories scale throughout their lifetime. Only ordinary notes
without known staging conflicts should be selected. A partial rule must disclose
its unboosted objects; freezing all Holds is not a full Hold-acceleration solution.

The Phira parser at revision `750579396cbc5dc61e6379fbfb2aa1adb70751a6`
(`prpr/src/parse/pgr.rs`) uses the integrated line scroll and each non-Hold's speed.
It ignores official `floorPosition` and sets internal Hold speed to 1, computing
Hold length from the integral at its tail. The exported floor/absolute-Hold fields
are still maintained for other consumers, but a change in those fields alone is
not evidence of a visual change in Phira. The primary-source snapshots and
chart-specific second-pass reviews are under `../deployments/chart-speed/batch-20261102/revision-2/`.

Holding an event's speed fixed does **not** by itself preserve an early-visible
note's position: future changed speed contributes to the same note's distance.
For exact protected choreography, add `policy.preserve_windows`:

```json
[{"line": 0, "side": "notesAbove", "note": 7,
  "from": 640, "to": 672, "reason": "Keep this early display unchanged"}]
```

Indices address the pinned baseline; times are line-local official ticks, **not
seconds or quarter-note beats**. Windows must precede the head. The compiler
checks head distance at both endpoints and every internal speed boundary, plus
Hold length. Piecewise constant speeds make these checks sufficient for the
entire window; unchanged position/rotation keeps the same spatial trajectory.
The supported equations are affine in X, so multiplier-range endpoints also
check these constraints throughout that interval. Conflicts reject compilation
instead of moving notes to new lines, changing timing, or claiming preservation.
This is a verifier of supplied equations, not an automatic compensation solver.

There is no fixed screen direction assumption. However, the current accepted
Rrharil profile is **proportional original-line scaling**, not exact per-note
“only during final approach” gating. Different visible phases on one shared line
cannot always be represented independently in the standard format. Review and
encode compatible rules; do not claim that merely labeling a note solves this.

## Transparent endings

`transparent_tails: true` preserves an already-authored final zero opacity by
appending a constant-zero event through the chart horizon. An always-hidden
carrier with only a negative-time event receives an explicit zero from time 0.
Existing fades/events remain unchanged. A nonzero final opacity or missing
opacity channel is rejected rather than guessed. Applying the repair twice is
idempotent. `X=1` reproduces the **compiled baseline bytes**, including this
separately recorded repair, rather than promising identity with the uncorrected
input. Set the flag false when no such repair is intended.

This addresses a concrete export gap in the accepted Rrharil package: hidden
lines had only negative-time opacity events and visible fades lacked sustained
zero tails. Target-player retesting is still required to confirm the reported
visual symptom is fully resolved.

## Verification and limits

```sh
python3 -m unittest discover -s agent-tools/chart-speed -p 'test_*.py' -v
```

Tests cover inverse motion, stops, release impulses, mixed BPM clocks, Hold speed,
authored floor offsets, preserved-window conflicts, exact baseline identity,
repeat generation, deterministic packages, transparency tails, source hash
guards, alias ambiguity, dry runs and overwrite/hardlink protection.

Speed timelines must be ordered, contiguous, begin at zero and cover every note
head/tail. Zero-duration official markers are retained at their original indices
and contribute zero integral; the following segment supplies the speed at the
shared timestamp. Zero-speed Holds are accepted without inventing a positive
speed. Negative durations, gaps, overlaps and nonpositive ordinary-note speed
remain rejected. This version does not infer gap semantics or repair overlapping
speed events. Schema 1 does not allocate lines or reassign notes. Schema 2 only
relocates the explicit helper subset and replays their channels on the stated
clock; original hit times are never quantized. Neither route calls a model.

The local Rrharil profile supports factors 0.5–2.0 mechanically. 130% was accepted
by the user, subject to the opacity correction; the range is not a human
playability/readability certification. Its source is the same prior native-to-
official baseline used for that accepted trial, retaining those earlier import
and fitting choices. New variants do not repeatedly round-trip through a
converter. All local chart assets and verification output remain untracked.
