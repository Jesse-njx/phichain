# Step 2: Music understanding (outline)

Begins after step 1 reaches its exit criteria. Detail to be written then.

## The task

From audio alone, decide:

- Which sounds become notes (the hit times step 1 takes as input), per difficulty.
- Which musical layer each passage follows: drums, melody, vocal, bass, a mix.
- Phrase and section boundaries, repeats and variations.
- Intensity, build-ups, drops and climax.
- Hold boundaries for sustained sounds.

## What exists

The MP3 note-decision analyzer (`research-tools/music-analysis/`) is an acoustic heuristic
baseline. The music Q&A MCP can answer questions about clips. Neither is yet
judged against the timing of official charts or the user's accepted timing.

## Likely milestones

- Benchmark: official charts' timing as reference for which sounds were charted,
  plus the user's accepted timing on their own songs.
- Measure the analyzer's selection against that reference, per layer and per section.
- Phrase and section structure good enough to feed step 1's phrase planning (N5).
- End-to-end: audio to playable chart with steps 1 and 2 both autonomous.

## Notes

- 32/64-beat phrases are clues, not rules (see `prompts/charting/rules.md`).
- Separate audible evidence from inferred instrument identity or emotion.
