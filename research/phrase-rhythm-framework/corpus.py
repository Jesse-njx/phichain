"""Corpus list and evidence extraction for calibration (README section 6)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORPUS = REPO / "research/overnight-study/corpus"
OUT = REPO.parent / "artifacts/phrase-rhythm-calibration"


def songs():
    out = []
    for mf, chart_dir, music_dir in (
        ("manifest.json", CORPUS / "chart", CORPUS / "music"),
        ("supplemental-manifest.json", CORPUS / "supplemental/chart", CORPUS / "supplemental/music"),
    ):
        p = CORPUS / mf
        if not p.exists():
            continue
        for row in json.loads(p.read_text()):
            sid = row["id"]
            music = music_dir / f"{sid}.ogg"
            charts = sorted((chart_dir).glob(f"{sid}.*/IN.json")) or sorted(chart_dir.glob(f"{sid}*/IN.json"))
            if music.exists() and charts and sid not in {x["id"] for x in out}:
                out.append(dict(id=sid, title=row.get("title", sid), music=music, chart=charts[0], constant=row.get("constant")))
    return out


if __name__ == "__main__":
    import prr_audio

    todo = songs()
    print(len(todo), "songs", flush=True)
    for i, s in enumerate(todo):
        t = time.time()
        work = OUT / "songs" / s["id"] / "work"
        try:
            prr_audio.extract(s["music"], work, log=lambda m: None)
            print(f"[{i + 1}/{len(todo)}] {s['id']} {time.time() - t:.0f}s", flush=True)
        except Exception as e:  # keep going; the table lists failures
            print(f"[{i + 1}/{len(todo)}] {s['id']} FAILED {e}", flush=True)
