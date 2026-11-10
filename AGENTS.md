# AutoPhiChain

This repository holds tools and the prompts that guide agents. Run commands from this folder unless a prompt says otherwise.

| Path | Contents |
| --- | --- |
| `agent-tools/` | Tools an agent uses to do the work, including the Phichain editor and MCP server in `agent-tools/Phichain/` |
| `research-tools/` | Tools for designing the system: frameworks, evaluation, calibration and model training |
| `prompts/` | The system: everything an agent follows |
| `research/` | How to improve the system |
| `runtime/` | Local model and Python environment |

Read the file for your task before starting:

- Chart authoring or review: `prompts/charting/rules.md`
- Editor or MCP development: `prompts/development/editor-and-mcp.md`
- Song analysis: `prompts/analysis/song-analysis.md`
- Improving the system: `research/README.md`

The index and the rule separating `prompts/` from `research/` are in `prompts/README.md`. What belongs in each tool folder is in `agent-tools/README.md` and `research-tools/README.md`.
