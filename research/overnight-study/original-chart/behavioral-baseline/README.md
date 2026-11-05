# Sol6.1-medium behavioral baseline

The agent interpreted the eight visible natural-language prompts into public MCP operations. A Python SDK controller replayed those decisions, measured transport and checked resulting artifacts. This is a warm-context Sol6.1-medium baseline, not a new Luna run, hidden-task benchmark, or full-song quality evaluation.

| Task | Acceptance | Calls | UTF-8 arguments / results | Clarifications |
|---|---|---:|---:|---:|
| two_bar_four_key_stair | 5/5 checked; no critical error | 7 | 1963 / 20867 | 0 |
| approach_speed_not_rhythm | 4/4 checked; no critical error | 10 | 2396 / 8936 | 0 |
| independent_note_sway | 6/6 checked; no critical error | 10 | 3110 / 8323 | 0 |
| sustained_voice_and_answers | 5/5 checked; no critical error | 8 | 2790 / 9718 | 0 |
| rest_despite_audio_energy | 5/5 checked; no critical error | 9 | 2948 / 6005 | 0 |
| four_types_without_quota | 4/4 checked; no critical error | 7 | 2380 / 6878 | 0 |
| ambiguous_faster | 3/3 checked; no critical error | 7 | 1578 / 4335 | 1 |
| recover_without_duplicate | 4/4 checked; no critical error | 9 | 2080 / 5234 | 0 |

Shared public tool/resource context recorded once: 38,696 compact UTF-8 bytes. Prompt bytes are recorded separately per task. Argument/result bytes are transport measurements, not LLM token estimates; setup and artifact calls are included and labelled in the receipts.

The ambiguous task records: “Do you mean denser rhythms, faster note approach, or faster line movement?” No dependent planning/application occurred. The disconnected-client task restarted the stdio server, imported the durable checkpoint, read the requested phrase, found both existing heads and avoided replaying the lost apply.

No chart/interface repair was required in these eight tasks. Whole exported main event tracks independently strengthen the sway/rest acceptance evidence; a bounded phrase query alone can omit initial constant events that still determine the pose. All final native/official JSON and sidecars are retained under the task directories. Synthetic tasks have no supplied audio and are not playable song bundles.

Remaining limits: the same agent had already studied the server and charting concepts; no isolated model latency/token billing was recorded, no Luna trial occurred, and no result establishes human comfort or official-equivalent music interpretation.
