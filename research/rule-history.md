# Rule history

Where the charting rules came from. The rules themselves are in
[prompts/charting/](../prompts/charting/rules.md) and are written without this
history, so that an agent reads what to do and not the story behind it. Use this
file to judge whether a rule still holds, or to find the evidence behind one.

When a correction from the user changes a rule: edit the rule in `prompts/`,
keeping the conditions under which it applies, and add a row here.

Chart paths are relative to the workspace root.

| Date | Source | What happened | Rule it produced |
| --- | --- | --- | --- |
| 2026-11-02 | Poseidon AT adaptation | The user clarified that pure configuration means one judgment line carrying every playable note, and that modest rotations of 20–30 degrees do not change the configuration by themselves. | `rules.md`, Terminology and timing |
| 2026-11-02 | Happy ending run02 | The user rejected sparse decorative punctuation, occasional receiver dips and slowly drifting two-lane note paths. Applies when a task requests wide travel and sustained performance. | `rules.md`, Movement and performance density; `design.md`, principle 7 |
| 2026-11-02 | Happy ending run03 | Four continuously moving crossing lines felt like the same noisy animation throughout the song, and the wide-travel arrangement was still boring. Movement coverage and wide-step statistics did not establish interesting play. | `rules.md`, Movement and performance density; `design.md`, Motion coverage is not an objective |
| 2026-11-02 | Happy ending run03 | This correction replaced an earlier blanket requirement to fade idle lines. | `rules.md`, Playable-line visibility and motion |
| Undated | First Happy ending run | The user rejected it for leaving idle carriers visible, confusing which line receives notes, and decorative movement that felt slow, stale and off rhythm, although validation and source timestamps matched. | `design.md`, Playable-line readability and rhythmic articulation |
| Undated | First climax diagnostics | The user rated them still very poor and ranked variant C relatively best. Its receiving-plane change remained ambiguous. | `design.md`, Receiver identity through orientation |
| Undated | 150 BPM repeated-hit study | The user expects many players to use extra fingers for the fast groups and explicitly welcomes this. | `rules.md`, Player actions and two-finger arrangement |
| 2026-11-07 | 168 BPM sixteenth wide-travel study | Otherwise rated good, but the user noted that most players would use multi-finger rather than L,R for most of a dense stream. | `rules.md`, Player actions and two-finger arrangement |
| 2026-11-07 | 126 BPM Sonnet study | Rejected. In slow passages any fingering works, so guidance cells have nothing to guide. | `rules.md`, Pattern families and concrete design records |
| 2026-11-07 | [Sonnet styles study](../../charts/silent/sonnet-styles-2026-11-07/README.md) | Rejected for cramming notes into one shared central window. The user explained that each hand has its own working region and moves independently. | `rules.md`, Four-key and moving multi-finger arrangements |
| 2026-11-07 | User terminology | **键盘** is the usual term for multi-finger charts, and **多押** means simultaneous hits. Multi-finger charts are described as Jack or Stream, not organized around 技 and 乱. The names 叠、技、乱、切 replaced the assistant's earlier labels 叠、技、速、耐. | `rules.md`, Four-key and moving multi-finger arrangements |
| Undated | [Four 10-second studies](../../charts/silent/silent-150-four-key/README.md) | The user rated 技、乱、切 "pretty much correct" and corrected the speed convention for 叠. | `rules.md`, Four-key and moving multi-finger arrangements |

## Moved out of the rules

The limit of 24 total judgment lines for the current Override chart was a
song-specific requirement. It belongs in that song's project records under
`charts/override/`.

## Other rule provenance

- Song analysis rules: [song-analysis-framework/DESIGN.md](song-analysis-framework/DESIGN.md), section 2.
- Phrase rhythm rules: [phrase-rhythm-framework/DESIGN.md](phrase-rhythm-framework/DESIGN.md), section 5.
