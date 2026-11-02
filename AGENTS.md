# PhiChain development

This repository is our fork of Ivan-1F/phichain. Keep the editor and its MCP server together here.

- `origin`: https://github.com/Jesse-njx/phichain.git
- `upstream`: https://github.com/Ivan-1F/phichain.git
- MCP stdio server: `tools/phichain-mcp/server.py`
- Live editor bridge: `phichain-editor/src/mcp.rs` and `phichain-editor/src/mcp/`

## Development scope and architecture

This file covers editor and MCP development. Before any chart authoring or chart review, read `local/AGENTS.md`, even when operating from the repository root. That file contains the charting workflow; song-specific requirements and progress belong in the corresponding local project records.

Keep the MCP interface minimal. Do not add speculative AI-charting tools, presets, planning frameworks, or analysis workflows. The user will design and request new capabilities. Do not maintain a parallel standalone chart state or authoring server. The separate phigros-chart-mcp repository is historical reference, not a runtime dependency.

Preserve local charts, audio, credentials and generated artifacts under ignored local paths; do not publish them.

## Git and previews

Never use `codex/` in branch names. Use descriptive branch names. Do not open rendered artifacts in Codex; provide a link for the user to open in a browser.

## Verification

Whenever the MCP server or editor bridge is edited, update the documentation in the same task. Keep `tools/phichain-mcp/README.md` and the HTML reference at `local/mcp-reference/index.html` accurate for the current tools, arguments, behavior, and limits. Update `local/mcp-reference/build.py` as needed, rebuild with `python3 local/mcp-reference/build.py`, and check its schema examples and internal links. Update `tools/phichain-mcp/ROADMAP.md` when scope changes. Provide the HTML link without opening it in Codex.

Run `python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py'` for adapter changes and `cargo test -p phichain mcp::` for Rust bridge changes.
