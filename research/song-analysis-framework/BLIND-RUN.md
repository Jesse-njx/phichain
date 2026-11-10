# Blind run: standing instructions for the analysis subagent

You are a blind song analyst. Your only musical input is one audio file. Apply
the framework in this folder to it and produce a Song Analysis Record using
only what you can measure or hear from the audio. These instructions replace the
long per-run brief; the per-run prompt gives you only the audio path and the
scratch directory.

## Per-run prompt (what the main session sends)

```
Blind song analysis. Audio: <scratch>/input/music.mp3 (tag-stripped). Scratch
directory: <scratch>/. Read and follow
/Users/jesse/Projects/PhiChain/main/research/song-analysis-framework/BLIND-RUN.md.
Report back in the format its last section asks for.
```

## 1. Input boundary

- Read only: the audio file named in the prompt; `README.md`, `pilot_moss.py`,
  `summarize_pilot.py` and this file in
  `/Users/jesse/Projects/PhiChain/main/research/song-analysis-framework/`; and,
  as a format example only, one finished record of a different song:
  `/Users/jesse/Projects/PhiChain/charts/other/hate/song-analysis-record.json`
  with its `config.json` and `work/build_sar.py`. Do not reuse that song's
  musical content.
- Do not read anything else: nothing else under `charts/`, no other folders
  under `main/research/`, no docs, no git history, no `~/Music`, no
  `~/Downloads`, no other projects, no web search or fetch, no ID3 tag
  inspection. You must not learn the song's title, artist, tempo or structure
  from anywhere except the audio. If a tool result leaks such information,
  ignore it and say so in your report.
- Never create, edit or delete any file under `/Users/jesse/Projects/PhiChain`.
  Write everything under the scratch directory, in `work/`, `stems/`, `clips/`
  and `out/`. Run repository scripts by absolute path; `cd` only into the
  scratch directory.

## 2. Tools

- Model: `/Users/jesse/Projects/PhiChain/main/runtime/music-runtime/bin/python`
  runs `pilot_moss.py` with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`. Use
  `--protocol v3 --config <config.json> --out <scratch>/out --clips
  <scratch>/clips`; `--list` dry-lists the calls. Run it in the background and
  wait for completion rather than polling. Expect 90–110 calls and 6–8 minutes
  of model time for a 3-minute song.
- Measurement:
  `/Users/jesse/Projects/PhiChain/main/research/music-flow-study/.venv/bin/python`
  has librosa, numpy, scipy, soundfile and demucs 4 (torch, MPS). ffmpeg and
  ffprobe are on PATH.

## 3. Steps

README section 3 (model rules 1–11, measurement rules 12–16) and section 5
(reconciliation, including the climax position prior) are binding.

1. **Grid, from measurement only.** Follow rules 12 and 13: windowed tempo
   fits, beat-phase drift, kick/snare pattern per window, half and double
   candidates with reasons, beat zero from the drum stem, pickup bar check. If
   the tempo or meter changes, record a piecewise grid in
   `L0_identity_grid.tempo_segments` and keep seconds authoritative. Never take
   BPM, meter or key from the language model; ask it once for BPM only to
   document the error.
2. **Vocal presence, from measurement.** Demucs htdemucs, 20 Hz high-pass
   (rule 14), vocal-stem RMS in 2 s bins, `vocal_ranges_seconds` above −40
   dBFS. If there are no vocals, set the field to an empty list, skip lyric
   questions and let the lead-line analysis rest on the other stems and the
   pair questions. If Demucs fails, say so and omit the field.
3. **Candidate sections, from measurement.** MFCC and chroma novelty plus
   self-similarity (rule 15: MFCC at best lag and lagged sequence chroma, block
   chroma only as a side figure). Boundaries in seconds first, then in beats of
   the config grid. Prefer phrase-length multiples where the evidence allows,
   never force them. Propose recurrence groups and the pairs to test, with at
   least one control pair you believe is different.
4. **Config and protocol.** Write the config JSON per README "Running v3 on a
   new song" (for a piecewise grid use the longest stable passage's grid as
   `bpm`/`offset_seconds`), run the protocol, then run `summarize_pilot.py
   --config <config> <out>` on the output.
5. **Reconcile and write the record** per README section 5. Files in `out/`:
   `song-analysis-record.json`, `song-analysis-record.md`, `README.md` (what
   was measured, what the model added, what failed, elapsed time and call
   counts, what could not be determined, where the framework's assumptions
   held or broke), `digest.md`, `config.json`, `calls/`. Keep contradictions
   visible; nothing is user-reviewed.

## 4. Record schema the viewer depends on

Keep these field names and shapes exactly; `artifacts/song-analysis-viewer/build.py`
reads them. They are the legacy keys listed in `docs/terminology.md` section 8
(`L0_identity_grid` = MG, `L1_form` = MF, `L2_layers` = ML0–ML2,
`L3_lead_line` = ML3–ML4, `L5_energy` = ME); do not rename them in a record.

- `L0_identity_grid`: `bpm.value`, `beat_zero_offset_seconds.value`,
  `duration_seconds`, `meter`, optional `tempo_segments` (list of
  `{id, seconds:[a,b], bpm, meter, anchor_seconds, confidence, note}`).
- `L1_form.sections`: list of `{id, beats:[a,b], seconds:[a,b], function,
  group, lead, vocal, boundary:{value, source, status, evidence, note},
  function_status:{value, source, status, evidence, note}}` in song order,
  covering the whole audio. `seconds` must be correct even where `beats` is
  approximate.
- `L1_form.recurrence_groups`: `{group_letter: {value: <one-line description>,
  source, status, evidence, note}}`.
- `L2_layers.vocal_ranges_seconds.value`: list of `[start, end]` seconds.
- `L3_lead_line.lyric_lines` (`{abs_start, beat, text, call}`) when lyrics
  were transcribed, or `lyric_line_starts` (`{abs_start, beat, section,
  template}`) when only section-opening lines are kept.
- `L5_energy.climax_candidates.value`: list of `[start_beat, end_beat]` pairs,
  ordered per the climax position prior (latest strong candidate first; an
  early candidate marked in the note as `early peak`).
- Claim format everywhere: `{value, source, status, evidence, note}` with
  `source` in measurement | model | reference | user and `status` in
  corroborated | model-only | measurement-only | contradicted | user-confirmed.

## 5. Report back

Concretely and briefly: the grid (MG, single or piecewise) with uncertainty;
the section table (MF0: beats, seconds, function, group, lead, boundary status,
function status); recurrence groups; vocal presence result; climax candidates in
position-prior order; main failures or surprises, especially where the
framework broke; files written; any outside-the-audio information that reached
you.
