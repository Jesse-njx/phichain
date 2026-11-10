# AutoPhiChain

> **Always hesitate before adding information to this file.** Add something
> only if the user or a developer absolutely cannot skip it. Otherwise, do not.
> Details belong in the documents linked below.

AutoPhiChain is a fork of [phichain](https://github.com/Ivan-1F/phichain), a
Phigros chart editor, plus the MCP tools, agent prompts and research that aim
to make charting autonomous. The upstream editor README is archived as
[PHICHAIN-README.md](PHICHAIN-README.md) (with its translations).

This repository is the `main/` folder of a private workspace. Charts, audio and
generated artifacts live beside it, outside Git, and are never published. See
[CHARTS.md](CHARTS.md) for what can be re-downloaded.

## Goal and roadmap

Today an agent charts well when directed passage by passage. The goal is the
shift from an agent that follows charting instructions to one that makes the
charting decisions itself, with the user as reviewer, not director. Full
roadmap: [docs/roadmap/README.md](docs/roadmap/README.md).

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
single registry is [docs/terminology.md](docs/terminology.md); new terms are
added there first, and no other document defines competing codes.

## Read next

- [AGENTS.md](AGENTS.md): editor and MCP development, Git rules, verification.
- [docs/AGENTS.md](docs/AGENTS.md): chart authoring and review, the live editor workflow, the user's accumulated corrections.
- [docs/terminology.md](docs/terminology.md): the code registry.
- [docs/roadmap/](docs/roadmap/README.md): the three steps, milestones and current state.
