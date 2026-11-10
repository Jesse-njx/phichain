# Former local/ paths

The `local/` directory no longer exists. Older records may still use these paths, including absolute `/Users/jesse/Projects/PhiChain/local/...` forms.

Current paths are relative to the workspace root (the folder containing `main/`). `docs/`, `research/` and `runtime/` are now under `main/`, and the former `phichain/` repository is `main/`.

| Former path | Current path |
| --- | --- |
| `phichain` | `main` |
| `research/agent-evals` | `main/research-tools/agent-evals` |
| `local/AGENTS.md` | `docs/AGENTS.md` |
| `local/arrangement-training` | `research/arrangement-training` |
| `local/BUILD-INFO.txt` | `apps/BUILD-INFO.txt` |
| `local/build.log` | `apps/build.log` |
| `local/chart-design.md` | `docs/chart-design.md` |
| `local/chart-speed` | `deployments/chart-speed` |
| `local/converted-audio` | `charts/xterfusion/converted-audio` |
| `local/entrance-in-transfer` | `charts/other/entrance-in-transfer` |
| `local/entrance-study` | `charts/other/entrance-study` |
| `local/happy-ending-climax-diagnostics` | `charts/happy-ending/happy-ending-climax-diagnostics` |
| `local/happy-ending-five-authors` | `charts/happy-ending/happy-ending-five-authors` |
| `local/happy-ending-full-c-revision` | `charts/happy-ending/happy-ending-full-c-revision` |
| `local/happy-ending-guided-run02` | `charts/happy-ending/happy-ending-guided-run02` |
| `local/happy-ending-performance-run03` | `charts/happy-ending/happy-ending-performance-run03` |
| `local/happy-ending-sol-baseline` | `charts/happy-ending/happy-ending-sol-baseline` |
| `local/headless-development` | `artifacts/headless-development` |
| `local/judgment-line-study` | `research/judgment-line-study` |
| `local/line-phrase-transfer` | `charts/other/line-phrase-transfer` |
| `local/mcp-reference` | `docs/mcp-reference` |
| `local/motion-inspections` | `artifacts/motion-inspections` |
| `local/music-flow-study` | `research/music-flow-study` |
| `local/music-mcp.json` | `runtime/music-mcp.json` |
| `local/music-model` | `runtime/music-model` |
| `local/music-runtime` | `runtime/music-runtime` |
| `local/music-smoke-result.json` | `runtime/music-smoke-result.json` |
| `local/music-smoke.py` | `runtime/music-smoke.py` |
| `local/music-smoke.wav` | `runtime/music-smoke.wav` |
| `local/note-analysis` | `research/note-analysis` |
| `local/overnight-study` | `research/overnight-study` |
| `local/Override Final Version` | `charts/override/Override Final Version` |
| `local/override-arcaea-session` | `charts/override/override-arcaea-session` |
| `local/override-author-session` | `charts/override/override-author-session` |
| `local/override-gesture-sample` | `charts/override/override-gesture-sample` |
| `local/override-in15-session` | `charts/override/override-in15-session` |
| `local/override-sol-in163-performance` | `charts/override/override-sol-in163-performance` |
| `local/override-sol-in163` | `charts/override/override-sol-in163` |
| `local/override-tap-hold-session` | `charts/override/override-tap-hold-session` |
| `local/override-three-2026-11-02` | `charts/override/override-three-2026-11-02` |
| `local/passage-previews` | `artifacts/passage-previews` |
| `local/PhiChain Live.app` | `apps/PhiChain Live.app` |
| `local/phichain-launch.log` | `apps/phichain-launch.log` |
| `local/PhiChain.app` | `apps/PhiChain.app` |
| `local/poseidon-pure-configuration` | `charts/other/poseidon-pure-configuration` |
| `local/poseidon-study` | `charts/other/poseidon-study` |
| `local/projects` | `charts/other/projects` |
| `local/qa` | `artifacts/qa` |
| `local/rebuild.command` | `apps/rebuild.command` |
| `local/reference-studies` | `research/reference-studies` |
| `local/rpe-next-mcp-reference` | `docs/rpe-next-mcp-reference` |
| `local/rrharil-at-scroll-130` | `charts/other/rrharil-at-scroll-130` |
| `local/silent-150-four-key` | `charts/silent/silent-150-four-key` |
| `local/silent-150-two-styles` | `charts/silent/silent-150-two-styles` |
| `local/silent-180-arrangement` | `charts/silent/silent-180-arrangement` |
| `local/silent-180-sixteenths` | `charts/silent/silent-180-sixteenths` |
| `local/xterfusion-audio-only-run01` | `charts/xterfusion/xterfusion-audio-only-run01` |
| `local/xterfusion-iris-study` | `charts/xterfusion/xterfusion-iris-study` |
| `local/Xterfusion-Sol-20261102` | `charts/xterfusion/Xterfusion-Sol-20261102` |
| `local/Xterfusion` | `charts/xterfusion/Xterfusion` |

# Repository reorganization (2026-11-10)

Later records may use these paths from before `agent-tools/`, `research-tools/` and `prompts/` existed. All are relative to `main/`.

| Former path | Current path |
| --- | --- |
| `phichain-assets` | `agent-tools/Phichain/asset-loader` |
| `phichain-<crate>` (chart, compiler, converter, editor, format, game, i18n, renderer, telemetry) | `agent-tools/Phichain/<crate>` |
| `assets`, `screenshots`, `scripts`, `start.bat` | `agent-tools/Phichain/...` at the same name |
| `Cargo.toml`, `Cargo.lock`, `target` | `agent-tools/Phichain/...` at the same name |
| `PHICHAIN-README*.md` | `agent-tools/Phichain/README*.md` |
| `tools/phichain-mcp` | `agent-tools/Phichain/mcp` |
| `docs/mcp-reference` | `agent-tools/Phichain/mcp/reference/phichain` |
| `docs/rpe-next-mcp-reference` | `agent-tools/Phichain/mcp/reference/rpe-next` |
| `AGENTS.md` (development rules) | `prompts/development/editor-and-mcp.md` |
| `docs/AGENTS.md` | `prompts/charting/rules.md` |
| `docs/chart-design.md` | `prompts/charting/design.md` |
| `docs/terminology.md` | `prompts/shared/terminology.md` |
| `docs/local-path-map.md` | `prompts/shared/local-path-map.md` |
| `docs/roadmap` | `research/roadmap` |
| `research/phigros-finetune` | `research-tools/phigros-finetune` |
| `research/phrase-rhythm-framework/*.py` | `agent-tools/phrase-rhythm/`, except `calibrate.py` and `make_viewer.py` in `research-tools/phrase-rhythm/` |
| `research/phrase-rhythm-framework/README.md` | `prompts/analysis/phrase-rhythm.md` and `research/phrase-rhythm-framework/DESIGN.md` |
| `research/song-analysis-framework/*.py` | `agent-tools/song-analysis/` |
| `research/song-analysis-framework/BLIND-RUN.md` | `prompts/analysis/blind-run.md` |
| `research/song-analysis-framework/README.md` | `prompts/analysis/song-analysis.md` and `research/song-analysis-framework/DESIGN.md` |
| `Phichain/`, `tools/agent/`, `tools/design/` (intermediate layouts) | `agent-tools/Phichain/`, `agent-tools/`, `research-tools/` |
| `tools/<name>` | `agent-tools/<name>` or `research-tools/<name>` |
| `level_to_mania_star` in `convert_mania.py` | `agent-tools/mania-level/mania_level.py` |
