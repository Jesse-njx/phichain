# PhiChain development

This repository is our fork of Ivan-1F/phichain. Keep the editor and its MCP server together here.

- `origin`: https://github.com/Jesse-njx/phichain.git
- `upstream`: https://github.com/Ivan-1F/phichain.git
- MCP stdio server: `tools/phichain-mcp/server.py`
- Live editor bridge: `phichain-editor/src/mcp.rs` and `phichain-editor/src/mcp/`

## Authoring architecture

Assume PhiChain is running with its MCP bridge and a project open for chart editing. The live editor is the single source of truth. Read context and the affected passage before editing; use current session/revision guards and shared undo history. If the editor or project is unavailable, report the prerequisite rather than creating an offline chart session.

Implement planning, evidence analysis and review as part of this repository's live MCP workflow. Plans may be prospective, but must target a live revision. Do not maintain a parallel standalone chart state or authoring server. The separate phigros-chart-mcp repository is historical reference for capabilities to port, not a runtime dependency.

Preserve local charts, audio, credentials and generated artifacts under ignored local paths; do not publish them.

## Git and previews

Never use `codex/` in branch names. Use descriptive branch names. Do not open rendered artifacts in Codex; provide a link for the user to open in a browser.

## Verification

Run `python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py'` for adapter changes and `cargo test -p phichain mcp::` for Rust bridge changes.
