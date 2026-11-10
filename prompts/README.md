# Prompts

The system itself: everything an agent follows while charting, analyzing a song
or developing the editor. How to improve the system is in
[research/](../research/README.md).

| Task | Read |
| --- | --- |
| Chart authoring or review | [charting/rules.md](charting/rules.md), then [charting/design.md](charting/design.md) |
| Song structure analysis | [analysis/song-analysis.md](analysis/song-analysis.md); for a blind run, [analysis/blind-run.md](analysis/blind-run.md) |
| Which timestamps get notes | [analysis/phrase-rhythm.md](analysis/phrase-rhythm.md) |
| Editor and MCP development | [development/editor-and-mcp.md](development/editor-and-mcp.md) |
| Term codes such as `MG1` | [shared/terminology.md](shared/terminology.md) |
| Reference data and environments | [shared/references.md](shared/references.md) |
| Paths in older records | [shared/local-path-map.md](shared/local-path-map.md) |

## What belongs here

Write what an agent must do, and the conditions under which it applies. Do not
write how a rule came about: dates, run names, rejected attempts and calibration
history go to [research/rule-history.md](../research/rule-history.md) or the
framework's `DESIGN.md`.

[shared/references.md](shared/references.md) is the only file here that may point
into `research/`. Song-specific requirements belong in that song's project records.
