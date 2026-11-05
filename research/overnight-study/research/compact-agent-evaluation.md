# Compact authoring workflow evaluation

The user wants repeatable tools and guidance that enable a lower-capacity agent such as GPT-6 Luna to create good charts cheaply. Current workers remain Sol6.1 medium. No Luna run has occurred; deterministic workflow success cannot establish Luna capability or official-like artistic quality.

## Repeatable tasks

A. **Recipe reuse.** Define a four-station, eight-onset quarter-beat motif and instantiate it at beats8 and24. The second occurrence changes its lane permutation, accent kind and sustained voice while retaining an explicit musical role. Verify exact timing, declared variants and unchanged notes outside both phrases. Compare recipe size with an explicit note list. Guidance should teach positions, rhythm and roles without exposing the full corpus.

B. **Preserve ownership during edits.** Add an outer hold voice and two inner answers on one playing anchor. Read only the phrase, including overlapping holds. Transform the answers and verify unchanged hold tails, voice/contact labels, unrelated lines and effects. The sidecar distinguishes anchor, carrier and empty decoration. Hand assignments remain editable hypotheses; local x and raw note counts cannot establish feasibility.

C. **Safe replay.** Replaying the same input from the same base must produce the same structural chart digest. Exclude receipt and handle IDs from equivalence. Reapplying a plan must return its existing receipt or a specific duplicate/stale error, never duplicate notes. An intervening edit invalidates the old digest. Mutating input or returned read dictionaries cannot change stored plans.

D. **Bounded context.** Capabilities, compact guidance and an eight-beat read should suffice for these tasks. Responses state limits/truncation/pagination and include overlapping tails. A pattern lookup returns a small attributed passage. Missing reference assets should be reported without implicit downloads. No full-song or full-corpus dump is required.

E. **Cached evidence.** Unchanged audio with identical analysis settings should reuse cached evidence keyed by asset hash and settings. Changed assets/settings invalidate the cache. If audio analysis is not implemented, report that limitation and use the precomputed study evidence; do not claim the MCP provides FFT analysis. Core authoring must operate without the optional large corpus.

## Measurement protocol

Retain public MCP requests and responses, exact UTF-8 JSON bytes in each direction, call count, largest and total payloads, elapsed tool time, separate renderer time and artifact digests. Report cold setup separately from warm replay. Separate optional downloads, audio analysis and rendering from authoring costs. These are local workflow measurements, not token bills or model capability predictions. Report bytes/characters instead of claiming token counts without an actual tokenizer.

## Rubric

**Deterministic pass/fail:** timing/BPM/offset, four note kinds and units, positive hold tails, event boundaries/floor/speed, unselected content preservation, immutable plans and digest guards, export/reimport agreement, regular single-anchor checks, bounded responses and absence of implicit external writes. Every failure needs a minimal witness.

**Evidence-based review:** musical attack/sustain/rest correspondence, contact ownership/travel/recovery, approach cues and visible landmarks, purposeful motif variation, phrase contrast and replay provenance. Score each separately:0 unexamined,1 weak,2 explicit hypothesis,3 rendered structural evidence,4 human playtest/listening corroboration. Alignment to detected onsets is not musical transcription truth.

**Subjective review:** aesthetic coherence, surprise, reward, comfort, fun, musical interpretation and polish. This requires human or an actually authorized model evaluation with declared limits. Automated checks can facilitate inexpensive iterations; they do not prove quality for arbitrary songs or that Luna matches Sol.
