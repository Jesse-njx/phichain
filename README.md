# AutoPhiChain

> **Always hesitate before adding information to this file.** Add something
> only if the user or a developer absolutely cannot skip it. Otherwise, do not.
> Details belong in the documents linked below.

AutoPhiChain is a fork of [phichain](https://github.com/Ivan-1F/phichain), a
Phigros chart editor, plus the MCP tools, agent prompts and research that aim
to make charting autonomous. The upstream editor README is archived as
[agent-tools/Phichain/README.md](agent-tools/Phichain/README.md) (with its translations).

This repository is the `main/` folder of a private workspace. Charts, audio and
generated artifacts live beside it, outside Git, and are never published. See
[CHARTS.md](CHARTS.md) for what can be re-downloaded.

## Goal and roadmap

Today an agent charts well when directed passage by passage. The goal is the
shift from an agent that follows charting instructions to one that makes the
charting decisions itself, with the user as reviewer, not director. Full
roadmap: [research/roadmap/README.md](research/roadmap/README.md).

Charting breaks down into three steps, with a fourth above them:

| Code | Step | Decides | State |
| --- | --- | --- | --- |
| N | Note arrangement | Given hit times: position, type, hand plan | **Current focus** (roadmap step 1) |
| M | Music understanding | Which sounds become notes, phrases and sections, intensity and climax | Macro analysis usable; micro (which timestamps) proposed |
| P | Performance | Judgment-line motion, effects, choreography | After N and M |
| G | Game design | Difficulty identity, pacing | Out of the roadmap's scope |

Each step is made autonomous on its own inputs before the next begins. Autonomy
is measured on four levels, A0 manual to A3 autonomous; the target for every
step is A3. The quality gate is the user's blind review of agent output
against official charts for the same passage, and the count of per-passage
instructions the user had to give, which must fall to zero.

## Terminology

Every term has a three-character code: **component letter, aspect letter, item
digit**, for example `MG1` = music understanding, grid, tempo. Component letters
are N, M, P, G above and X for cross-cutting vocabulary (claim status, evidence
source, time scales, records). The digit is an identifier, never reused. The
single registry is [prompts/shared/terminology.md](prompts/shared/terminology.md); new terms are
added there first, and no other document defines competing codes.

## Read next

- [prompts/](prompts/README.md): the system agents follow, including chart authoring and review, the live editor workflow, editor development and the term registry.
- [research/](research/README.md): how to improve the system, including the roadmap and where each rule came from.
