> **Agent-assisted charting fork:** [Jesse-njx/phichain](https://github.com/Jesse-njx/phichain), based on [Ivan-1F/phichain](https://github.com/Ivan-1F/phichain). The live editor MCP server is included in [`tools/phichain-mcp`](tools/phichain-mcp/README.md), with its Rust bridge in `phichain-editor/src/mcp.rs`. See the [development roadmap](tools/phichain-mcp/ROADMAP.md).

> [!WARNING]
> Still in early stages of development, expect incomplete feature and unexpected behavior

## Phichain

[简体中文](https://github.com/Ivan-1F/phichain/blob/master/README.md) | [繁體中文](https://github.com/Ivan-1F/phichain/blob/master/README_tw.md) | **English** | [日本語](https://github.com/Ivan-1F/phichain/blob/master/README_ja.md)

[![GitHub License](https://img.shields.io/github/license/Ivan-1F/phichain)](https://github.com/Ivan-1F/phichain/blob/master/LICENSE)
[![Dev Builds](https://github.com/Ivan-1F/phichain/actions/workflows/cargo.yml/badge.svg)](https://github.com/Ivan-1F/phichain/actions/workflows/cargo.yml)

Phigros charting toolchain written in Rust and Bevy

- QQ Group: [768476938](https://phicha.in/qq)
- Discord: [discord.gg/ESUwcdMBPv](https://phicha.in/discord)

![screenshot](screenshots/phichain-editor-en.png)

## Thanks

- [Phira](https://github.com/teamflos/phira)
- Re:PhiEdit by [cmdysj](https://space.bilibili.com/252635690)
- The resource assets under `assets/image` and `assets/audio` are from [https://github.com/MisaLiu/phi-chart-render],
  and are licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)


### Judgment-line authoring roles (this fork)

The line list shows **Simple**, **Complex**, or **Decorative** beside each line.
Select a line and use **Role** in the line inspector to change it; changes support
undo/redo and persist in native PhiChain projects. Existing charts default to Simple.

- Simple: shared motion and scrolling for playable notes.
- Complex: independent note choreography, intended for one active note at a time
  across its full visible lifetime, including early appearances and hold tails.
- Decorative: visual line effects, intended to carry no playable notes. The
  inspector warns if notes are present; they remain playable.

Roles currently describe intent. They do not allocate carriers, enforce occupancy,
change animation, or make notes non-playable. Early-visible notes still have later
judgments. Native role labels are not preserved in RPE or official-format exports.

### Experimental Agent authoring MCP

The `rpe-agent-mcp` branch includes an alternative
[`agent_server.py`](tools/phichain-mcp/agent_server.py) entrypoint with partial
patches, expression transforms/generation and JavaScript candidate-document edits
against the live PhiChain editor. See the [setup, limits and source licensing](tools/phichain-mcp/README.md#experimental-rpe-next-style-authoring-server-this-branch).
