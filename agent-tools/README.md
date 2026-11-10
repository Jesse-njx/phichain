# Agent tools

Tools an agent uses to do the work: charting, analyzing a song, producing a chart variant. A tool belongs here if a prompt tells an agent to run it, or an agent needs it to deliver a chart. Tools for building the system are in [research-tools/](../research-tools/README.md).

- `Phichain/`: the editor, renderer, converter and MCP server, as one Cargo workspace.
- `song-analysis/`: listening protocol for a Song Analysis Record.
- `phrase-rhythm/`: Phrase Rhythm Records and rhythm tracks.
- `chart-speed/`: scroll-speed variants of a chart.
- `pure-configuration/`: reduce a chart to one static judgment line.
- `mania-level/`: Phigros level to 4K osu!mania star rating.

Agent tools do not depend on research tools.
