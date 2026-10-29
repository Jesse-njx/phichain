# PhiChain development

This repository is our fork of Ivan-1F/phichain. Keep the editor and its MCP server together here.

- `origin`: https://github.com/Jesse-njx/phichain.git
- `upstream`: https://github.com/Ivan-1F/phichain.git
- MCP stdio server: `tools/phichain-mcp/server.py`
- Live editor bridge: `phichain-editor/src/mcp.rs` and `phichain-editor/src/mcp/`

## Chart terminology

When the user says “notes,” they mean the individual playable note objects the player must hit or interact with (tap, hold, drag, or flick), not musical beats. A range such as “notes 1–41” means the first 41 playable note objects in chart order, inclusive. Do not reinterpret it as beats 1–41 or silently extend the range to include additional simultaneous notes. If simultaneous notes make the ordering ambiguous, state the ordering convention or clarify the intended numbering. Use “beats” for musical timing only when the user explicitly refers to beats; beat positions may still be reported as timing information for the requested notes.

## Authoring architecture

Assume PhiChain is running with its MCP bridge and a project open for chart editing. The live editor is the single source of truth. Read context and the affected passage before editing; use current session/revision guards and shared undo history. If the editor or project is unavailable, report the prerequisite rather than creating an offline chart session.

Keep the MCP interface minimal. Do not add speculative AI-charting tools, presets, planning frameworks, or analysis workflows. The user will design and request new capabilities. Do not maintain a parallel standalone chart state or authoring server. The separate phigros-chart-mcp repository is historical reference, not a runtime dependency.

Preserve local charts, audio, credentials and generated artifacts under ignored local paths; do not publish them.

Treat PhiChain renders as visual ground truth for chart review: they are consistent with the in-game presentation. Inspect actual rendered frames when judging motion. A note shown early is still a playable note with a later judgment time; do not label it fake or move its hit time merely to animate it. Motion groups must account for the entire visible lifetime, including hold tails.

## Git and previews

Never use `codex/` in branch names. Use descriptive branch names. Do not open rendered artifacts in Codex; provide a link for the user to open in a browser.

## Verification

Whenever the MCP server or editor bridge is edited, update the documentation in the same task. Keep `tools/phichain-mcp/README.md` and the HTML reference at `local/mcp-reference/index.html` accurate for the current tools, arguments, behavior, and limits. Update `local/mcp-reference/build.py` as needed, rebuild with `python3 local/mcp-reference/build.py`, and check its schema examples and internal links. Update `tools/phichain-mcp/ROADMAP.md` when scope changes. Provide the HTML link without opening it in Codex.

Run `python3 -m unittest discover -s tools/phichain-mcp -p 'test_*.py'` for adapter changes and `cargo test -p phichain mcp::` for Rust bridge changes.
