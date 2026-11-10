# Research tools

Tools for designing the system: frameworks, evaluation, calibration and model training. A tool belongs here if its output changes the system rather than a chart. Tools an agent runs to do the work are in [agent-tools/](../agent-tools/README.md).

- `agent-evals/`: judge chart-authoring agents by their output.
- `phigros-finetune/`: build datasets, fit and score the note generator.
- `music-analysis/`: first-pass MP3 analyzer and PhiChain importer. An acoustic baseline only, rejected as a source of notes.
- `phrase-rhythm/`: calibrate the Phrase Rhythm framework against official charts.

Research tools may import agent tools.
