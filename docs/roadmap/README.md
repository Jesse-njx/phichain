# AutoPhiChain roadmap: toward autonomous charting

Set by the user on 2026-11-05. This folder records product direction. It does not
by itself authorize any particular tool, MCP capability or editor change; each of
those is still designed and requested by the user (see `main/AGENTS.md`).

## Where we are

Today AutoPhiChain works as a **guided** charting system. A person who cannot
chart can get a chart made by prompting an agent, but the person still directs
the work passage by passage: which line carries which notes, what kind of note
arrangement they want, where effects go, and so on. The agent executes those
decisions well; it does not make them.

This is the same place coding agents were a few model generations ago. You could
guide them to write code one instruction at a time, but left on their own they
did not produce working software. Now they largely do. **The breakthrough we are
going for is that same shift for charting: from an agent that follows charting
instructions to one that makes the charting decisions itself, with the user as
reviewer rather than director.**

See [current-state.md](current-state.md) for what already exists in the repository.

## The three steps of charting

No matter which rhythm game a chart is for, charting breaks down into three steps:

| # | Step | What it decides | Difficulty |
| --- | --- | --- | --- |
| 1 | [Note arrangement](01-note-arrangement.md) | Given hit times, where each note goes, its type, and how the player's hands move through it. | Easiest. **Current focus.** |
| 2 | [Music understanding](02-music-understanding.md) | Which sounds become notes, how the song is grouped into phrases and sections, intensity and climax. | Harder. |
| 3 | [Performance](03-performance.md) | Judgment-line motion, effects and visual choreography that express the music. | Hardest. |

Above all three sits macro-level game design (difficulty identity of a whole
chart, pacing across a song, how a chart sits among a game's other charts). It is
real, but **out of scope for this roadmap.**

## Order of work

1. **Note arrangement first.** It is the most tractable step: its inputs can be
   fixed (accepted timing), its outputs are concrete (positions, types, hand
   paths), and we already hold 327 official IN charts as reference. Solving it
   in isolation gives us a working autonomous component and the evaluation
   machinery the later steps also need.
2. **Music understanding second.** Once arrangement is autonomous, the remaining
   human input to a playable chart is the timing and phrase structure. Removing
   that input makes a fully autonomous *playable* chart from audio alone.
3. **Performance third.** With a playable chart produced autonomously, add the
   expressive layer.

Each step should be made autonomous on its own inputs before the next begins,
rather than advancing all three partially.

## Levels of autonomy

Used across all three steps to describe how much the user still decides.

| Level | User provides | Agent decides |
| --- | --- | --- |
| A0 Manual | Every placement. | Nothing; it only edits. |
| A1 Directed (today) | Per-passage intent: which line, which pattern, which hand style. | Concrete coordinates that realize the stated intent. |
| A2 Supervised | Song-level intent (difficulty, style) and corrections after review. | Every passage decision; asks only on genuine ambiguity. |
| A3 Autonomous | Nothing beyond the song and target difficulty. Reviews the result. | Everything in the step; the user's review is the only gate. |

The goal for each step is A3, judged by blind user review (below).

## How we know it worked

Manual user review stays the quality gate, as in `docs/AGENTS.md`. The roadmap
adds discipline around it:

- **Blind comparison.** The user rates agent output alongside official or
  human-made charts for the same passage without knowing which is which.
  `tools/agent-evals` already provides the L0 validity, L1 detector and L2 blind
  review layers.
- **Instruction count.** Track how many per-passage directions the user had to
  give to reach an acceptable result. Autonomy means this count falls to zero,
  not merely that output quality rises.
- **Held-out songs.** Evaluate on songs the agent and any model have not seen,
  and keep the benchmark fixed between runs so results are comparable.
- Measured statistics (density, travel, type ratios) are reference
  distributions, not targets. A run is not good because its numbers match.

## Files

- [current-state.md](current-state.md): what exists today and how it maps to the three steps.
- [01-note-arrangement.md](01-note-arrangement.md): detailed plan for the current focus.
- [02-music-understanding.md](02-music-understanding.md): outline.
- [03-performance.md](03-performance.md): outline.
