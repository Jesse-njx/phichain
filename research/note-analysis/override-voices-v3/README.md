> Superseded and rejected by the user: the five-track result was too sensitive across the entire song. The current two-track experiment is [v4](../override-two-track-v4/README.md). The material below is historical, not an accepted result.

# Override — source-aware evidence probe

**Current deliverable:** the full-song five-track result is complete; see
[FULL-RESULT.md](FULL-RESULT.md), `override-voices-full.mp4`, `project/` and
`analysis.json`. The text below records the earlier 12-second diagnostic history.

Current state: a 48–60 second diagnostic probe, created on 2026-11-02 after user
feedback that frequency-band tracks fail to distinguish foreground melody/vocals
from accompaniment. This is not a completed musical-role classifier or accepted
note-selection result. No editor was reopened and no chart was edited.

## Corrected analysis target

Track persistent musical voices and their own timing before interpreting their
relationships. Source identity and musical role are separate attributes: a vocal
can be backing material; piano/guitar can contain both melody and accompaniment;
the leading voice can change between phrases. Frequency is a useful internal
audio feature but is not the output grouping requested by the user.

A future role-aware event should preserve its source/voice identity, phrase,
raw timing, onset/pitch-change/sustain evidence, possible musical role and role
uncertainty. Near-simultaneous events in different voices remain separate.
Beat-relative phase can describe their relationship without synchronizing them.
Repeated accompaniment does not imply every interval must be identical, and
irregular timing alone does not establish foreground melody.

## Existing sources and timebase

The earlier local music-flow study already contains HTDemucs vocals, drums,
bass and other estimates for the exact original Override MP3 source hash
`7284ea9019ef8ea3a90f7c92c3394aa4447ffc9cd29bc8b5df2b6c6c30407e29`.
Its provenance is recorded in `research/music-flow-study/provenance.json`.
HTDemucs's source categories do not separate melody from accompaniment within
the same instrument: see the [official Demucs documentation](https://github.com/facebookresearch/demucs).

The sum of the stored stems is delayed by 1,105 samples at 44,100 Hz relative
to the current canonical PCM: 25.0567 ms. Correlation tests at 5, 30, 60, 100
and 125 seconds all find the same lag, with correlations 0.99862–0.99876.
Stem samples are read with this delay removed before the probe; no chart offset
or original stem file is changed. This verifies a common waveform timebase,
not the separation quality of individual sources.

## Probe outputs

- `alignment.json`: source hashes and five alignment measurements.
- `probe.py`: independent source analysis with 250 ms of edge context.
- `probe.json`: four source streams, a vocal pitch contour, onset-envelope
  repetition candidates, and explicit vocal-to-drum timing relationships.
- `vocals-48-60.wav`, `drums-48-60.wav`, `bass-48-60.wav`, `other-48-60.wav`:
  aligned source excerpts at their existing relative levels.
- `summary.json`: candidate counts, not musical-note counts or quality metrics.

The probe retains 83 vocal, 74 drum, 84 bass and 107 other spectral-change
candidates. These may include consonants, within-note changes, separation leakage
and other false attacks. No candidate cap or cross-source suppression is used.
The 83 vocal attack candidates include 34 more than 30 ms from the nearest drum
candidate. This is a relationship among detector outputs, not proof that all
34 are genuine displaced musical notes. No events were merged or snapped.

The vocal pYIN contour is a monophonic pitch estimate; it is not syllable
segmentation, polyphonic transcription, or a validated main-melody note sequence.
All musical roles remain explicitly unclassified in the JSON. The other stem
can contain both lead melody and accompaniment. Repetition-period candidates
are not automatically assigned BPMs or accompaniment labels.

Checks passed for unique event IDs, source ownership, corrected clip times,
and references between independent streams. No listening review was performed.

## Next implementation boundary

1. Review separated evidence and identify coherent phrases, including where the
   leading source changes. Do not relabel all other audio as background.
2. Within pitched sources, distinguish new articulation, pitch change without
   new articulation, sustained notes and repeated accompaniment patterns.
3. Evaluate voice/source association and pattern continuity before millisecond
   timing scores. Existing chart head labels alone do not label these roles.
4. Present resulting voices/roles as separate PhiChain tracks once this
   representation is meaningful; retain timing differences between streams.

The previous timing benchmark remains useful for within-voice localization, but
improved global onset coverage does not establish musically useful voice tracking.
