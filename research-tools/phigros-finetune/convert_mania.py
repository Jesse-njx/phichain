"""Convert official Phigros charts into a 4K osu!mania Mapperatorinator dataset.

Drags are left out. Flicks count at half weight by splitting them between two
beatmaps of each chart, as in convert.py. A note's column comes from its position
on the judgment line. Notes in one column never overlap: a hold that would run
into the next note in its column is cut short, or becomes a tap if too little
remains. Star ratings come from level_to_mania_star.

    python convert_mania.py [output_dir]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import rosu_pp_py as rosu

import convert as C

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent-tools/mania-level"))
from mania_level import HIGH_LEVEL, LOW_LEVEL, level_to_mania_star

KEYS = 4
X_RANGE = 7.0
HOLD_GAP = 0.03
MIN_HOLD = 0.05
OUT = Path(__file__).resolve().parents[3] / "artifacts/phigros-finetune/dataset-mania4k"


def column(x: float) -> int:
    return int(np.clip(np.floor((x + X_RANGE) / (2 * X_RANGE) * KEYS), 0, KEYS - 1))


def objects(notes):
    """(ms, column, end_ms or None) with no overlap inside a column; drags excluded."""
    by_col: dict[int, dict[int, dict]] = {}
    for n in notes:
        if n["kind"] == C.DRAG:
            continue
        ms = int(round(n["t"] * 1000))
        by_col.setdefault(column(n["x"]), {}).setdefault(ms, n)
    out = []
    for col, items in by_col.items():
        times = sorted(items)
        for i, ms in enumerate(times):
            n = items[ms]
            end = None
            if n["kind"] == C.HOLD and n["hold"] > HOLD_GAP:
                end = ms + int(n["hold"] * 1000)
                if i + 1 < len(times):
                    end = min(end, times[i + 1] - int(HOLD_GAP * 1000))
                if end - ms < MIN_HOLD * 1000:
                    end = None
            out.append((ms, col, end))
    out.sort()
    return out


def object_lines(objs):
    lines = []
    for ms, col, end in objs:
        x = int((col + 0.5) * 512 / KEYS)
        lines.append(f"{x},192,{ms},128,0,{end}:0:0:0:0:" if end is not None else f"{x},192,{ms},1,0,0:0:0:0:")
    return lines


def osu_text(notes, bpm, offset, title, version, set_id, map_id):
    head = C.osu_text([], bpm, offset, title, version, set_id, map_id).replace("Mode: 0", "Mode: 3")
    assert "Mode: 3" in head and "CircleSize:4" in head
    return head.rstrip("\n") + "\n" + "\n".join(object_lines(objects(notes))) + "\n"


def star_ratio(text: str) -> list[float]:
    """Star rating at each dataset speed, relative to speed 1.0."""
    beatmap = rosu.Beatmap(content=text)
    value = []
    for s in C.SPEEDS:
        d = rosu.Difficulty()
        d.set_clock_rate(clock_rate=float(s))
        value.append(d.calculate(beatmap).stars)
    return [v / value[C.SPEEDS.index(1.0)] for v in value]


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    (out / "data").mkdir(parents=True, exist_ok=True)
    levels = {}
    for row in (C.CORPUS / "difficulty.tsv").read_text().splitlines():
        cells = row.split("\t")
        levels[cells[0]] = [float(x) for x in cells[1:]]
    # held-out songs sort last so the train/test split is a simple index range
    chart_dirs = sorted(C.CORPUS.glob("chart/*.0"), key=lambda d: (d.name[:-2] in C.HOLDOUT, d.name))
    rows, skipped = [], []
    rng = np.random.default_rng(7)
    set_id = 0
    for d in chart_dirs:
        sid = d.name[:-2]
        audio = C.CORPUS / "music" / f"{sid}.ogg"
        if not audio.exists():
            skipped.append((sid, "no audio"))
            continue
        made = 0
        folder = f"{set_id + 1:03d}"
        for name in ("IN", "AT"):
            path = d / f"{name}.json"
            if not path.exists():
                continue
            chart = json.loads(path.read_text())
            bpms = {float(l["bpm"]) for l in chart["judgeLineList"]}
            idx = C.LEVELS[name]
            level = levels.get(sid, [])
            if len(bpms) != 1:
                skipped.append((sid, f"{name} has {len(bpms)} line BPMs"))
                continue
            if idx >= len(level):
                skipped.append((sid, f"{name} has no level"))
                continue
            if not LOW_LEVEL <= level[idx] <= HIGH_LEVEL:
                skipped.append((sid, f"{name} level {level[idx]} outside {LOW_LEVEL}-{HIGH_LEVEL}"))
                continue
            bpm = bpms.pop()
            notes, offset = C.notes_of(chart)
            kept = [n for n in notes if n["kind"] != C.DRAG]
            pick = rng.random(len(kept)) < 0.5
            (out / "data" / folder).mkdir(parents=True, exist_ok=True)
            for half in (0, 1):
                use = [n for n, p in zip(kept, pick) if n["kind"] != C.FLICK or p == bool(half)]
                map_id = set_id * 100 + idx * 10 + half + 1000000
                file = f"{name}-{half}.osu"
                text = osu_text(use, bpm, offset, sid, f"{name}{half}", set_id + 1, map_id)
                (out / "data" / folder / file).write_text(text)
                star = level_to_mania_star(level[idx])
                rows.append(dict(BeatmapSetId=set_id + 1, Id=map_id, BeatmapSetFolder=folder, BeatmapFile=file, AudioFile="audio.ogg",
                                 StarRating=[star * r for r in star_ratio(text)], DifficultyRating=star, ModeInt=3, Ranked=1, UserId=0, HoldOut=sid in C.HOLDOUT, Song=sid,
                                 RankedDate=datetime(2023, 1, 1), SubmittedDate=datetime(2023, 1, 1), DifficultyName=f"{name}{half}"))
                made += 1
        if made:
            link = out / "data" / folder / "audio.ogg"
            if not link.exists():
                os.symlink(audio, link)
            set_id += 1
    df = pd.DataFrame(rows)
    df.to_parquet(out / "metadata.parquet")
    print("mapsets", set_id, "train", df.loc[~df["HoldOut"], "BeatmapSetId"].nunique(), "held out", df.loc[df["HoldOut"], "BeatmapSetId"].nunique(), "beatmaps", len(df))
    print("star range", round(df["DifficultyRating"].min(), 2), round(df["DifficultyRating"].max(), 2), "skipped", skipped)


if __name__ == "__main__":
    main()
