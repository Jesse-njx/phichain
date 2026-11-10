# Step 1: Note arrangement (current focus)

## The task

**Given:** the hit times of a passage (which moments are notes, already decided),
the target difficulty, and the playfield (initially one static judgment line).

**Decide, without per-passage direction from the user:**

- Each note's position on the line.
- Each note's type: Tap, Drag, Hold (and its length), Flick.
- The intended hand plan: which finger takes each fresh hit, each finger's path,
  contact occupancy, entry and exit.
- Phrase-level structure: recurring cells, mirrors, returns, role exchanges,
  contrast between sections, and where to stay still.

**Not in this step:** choosing which sounds become notes (step 2), line motion and
effects (step 3), multi-line layouts beyond what a passage strictly needs.

Today the user supplies most of the "decide" list per passage (A1). The target is
A3: the user hands over timing and difficulty and only reviews the result.

## Why it comes first

- The input can be held fixed. Using official or user-accepted timing isolates
  arrangement quality from music-understanding errors.
- The output is concrete and checkable: positions, types and hand paths can be
  validated mechanically for physical feasibility before any taste judgment.
- We have direct reference: 327 official IN charts, already projected to a
  single-line representation.
- The user has already given extensive arrangement corrections (see
  `prompts/charting/rules.md`), so the decision rules are partly written down.

## Constraints carried over

- Start with **pure configuration**: one static receiver, straight approach.
- Two-finger viability is the default design target; multi-finger routes may also exist.
- Follow the action rules in `prompts/charting/rules.md`: same-finger travel is judged on
  successive actions of that finger, double taps need a concrete musical reason,
  rests are preserved in hand analysis, nonzero release gaps are not proof of a
  good transition.
- Do not copy coordinates or cells from approved examples; do not turn one
  approved example into a universal rule.

## Milestones

### N0. Task contract and benchmark

- Fix the input format (timed hits, optional phrase boundaries, difficulty) and
  output format (notes plus a hand plan an evaluator can read).
- Build a fixed benchmark: held-out official passages with timing kept and
  arrangement stripped, plus passages from the user's own songs with accepted
  timing. Cover distinct passage kinds: streams, jacks, chords, holds over
  rhythms, slow sections, bursts.
- **Done when:** one command produces the benchmark inputs, and the same inputs
  are used by every later milestone.

### N1. Evaluation harness

- Build the agent runner missing from `research-tools/agent-evals`: launch an authoring
  agent on a benchmark passage with no per-passage instruction, collect the result.
- L0: feasibility (contact occupancy, two-finger route exists, no impossible holds).
- L1: detectors reported against official distributions, not as targets.
- L2: blind review mixing agent output with the official arrangement for the
  same timing. Record ratings and instruction count.
- **Done when:** a single run yields a review session the user can rate in one
  sitting.

### N2. Baseline: current agent, no direction

- Run the current best agent with existing guidance on the benchmark, with timing
  given and no passage-level direction.
- Record where it fails: monotony, aimless travel, broken alternation, wrong type
  choices, lack of phrase identity, poor section contrast.
- **Done when:** there is a measured baseline and a ranked list of failure modes.

### N3. Decision rules from corrections

- Turn the user corrections in `research/rule-history.md` and the rules in `prompts/charting/` into
  rules an agent can apply on its own: how to pick a movement cell for a passage
  type, when to mirror, when to hold an anchor, when stillness is right.
- Each rule cites its source correction and the conditions where it applies.
- **Done when:** the N2 failure modes covered by existing corrections stop
  recurring on the benchmark.

### N4. Reference retrieval

- Given a passage's rhythm, find official passages with similar rhythm and density
  in the corpus and show the agent how they were arranged (as patterns and hand
  plans, not coordinates to copy).
- Evaluate the masked model as an alternative or complement: as a proposal
  generator the agent critiques, or as a scorer of candidate arrangements.
- **Done when:** retrieval or the model measurably improves blind ratings over N3.

### N5. Phrase and section planning

- Before placing notes, the agent writes a phrase plan: which passages share a
  motif, what varies on return, what contrasts between sections, how hands enter
  and leave each section.
- Uses phrase boundaries as given input in this step (from the user, the official
  chart's structure, or the music analyzer), so music-understanding errors do
  not leak in.
- **Done when:** whole-section output reads as composed rather than as
  independent passages, judged in blind review.

### N6. Full-song arrangement

- Arrange a complete song end to end from accepted timing, unattended, through
  the live editor workflow.
- **Done when:** the user can take a full song from timing to a reviewable chart
  with zero per-passage instructions, and most passages are accepted without edits.

### N7. Difficulty scaling

- Arrange the same timing at different difficulty targets, and later reduce or
  extend timing for lower and higher difficulties (this starts to overlap with step 2).

## Exit criteria for step 1

- Zero per-passage instructions on held-out songs.
- Blind review: agent arrangements are accepted at a rate the user considers
  comparable to the official arrangement for the same timing.
- Results hold on the user's own songs, not only on the official benchmark.

## Open questions

- What acceptance rate in blind review counts as "comparable"? The user sets it.
- Should the masked model be the arranger, or a tool the agent uses?
- When does arrangement need more than one line, and does that belong in step 1
  or step 3?
- How much of the hand plan should be stored with the chart for later review?
