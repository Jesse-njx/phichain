# PhiChain development

This repository is our fork of Ivan-1F/phichain. Keep the editor and its MCP server together here.

- `origin`: https://github.com/Jesse-njx/phichain.git
- `upstream`: https://github.com/Ivan-1F/phichain.git
- MCP stdio server: `agent-tools/Phichain/mcp/server.py`
- Live editor bridge: `agent-tools/Phichain/editor/src/mcp.rs` and `agent-tools/Phichain/editor/src/mcp/`

## Development scope and architecture

This file covers editor and MCP development. Before any chart authoring or chart review, read `prompts/charting/rules.md`, even when operating from the repository root. That file contains the charting workflow; song-specific requirements and progress belong in the corresponding local project records.

The product direction is autonomous charting. It is recorded in the [product roadmap](../shared/references.md#product-roadmap), and note arrangement is the current focus. The roadmap sets direction only; it does not authorize any specific tool.

Keep the MCP interface minimal. Do not add speculative AI-charting tools, presets, planning frameworks, or analysis workflows. The user will design and request new capabilities, guided by the roadmap. Do not maintain a parallel standalone chart state or authoring server. The separate phigros-chart-mcp repository is historical reference, not a runtime dependency.

Keep local charts, audio, credentials and generated artifacts in the workspace outside this repository; do not publish them.

## Git and previews

Never use `codex/` in branch names. Use descriptive branch names. Do not open rendered artifacts in Codex; provide a link for the user to open in a browser.

## Verification

Whenever the MCP server or editor bridge is edited, update the documentation in the same task. Keep `agent-tools/Phichain/mcp/README.md` and the HTML reference at `agent-tools/Phichain/mcp/reference/phichain/index.html` accurate for the current tools, arguments, behavior, and limits. Update `agent-tools/Phichain/mcp/reference/phichain/build.py` as needed, rebuild with `python3 agent-tools/Phichain/mcp/reference/phichain/build.py`, and check its schema examples and internal links. Update `agent-tools/Phichain/mcp/ROADMAP.md` when scope changes. Provide the HTML link without opening it in Codex.

Run `python3 -m unittest discover -s agent-tools/Phichain/mcp -p 'test_*.py'` for adapter changes and `cargo test --manifest-path agent-tools/Phichain/Cargo.toml -p phichain mcp::` for Rust bridge changes.
