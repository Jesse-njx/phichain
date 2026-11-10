"""Convert official Phigros charts into a Mapperatorinator (MMRS) dataset.

Drags are left out of the training data. Flicks count at half weight: each chart
becomes two beatmaps that split the flicks between them, so every flick is seen
half as often as a tap. For a yes/no note decision that is equivalent to halving
the loss on flick positives. Holds become sliders; tap and hold positions come
from the note's line position and side.

    python convert.py [output_dir]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
CORPUS = WS / "main/research/overnight-study/corpus"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else WS / "artifacts/phigros-finetune/dataset"
HOLDOUT = {"Rrharil.TeamGrimoire", "BoundedQuietude.FiniteLimitvsSiLiS", "Incyde.YbeLL"}
LEVELS = {"EZ": 0, "HD": 1, "IN": 2, "AT": 3}
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
SV = 1.4
TAP, DRAG, HOLD, FLICK = 1, 2, 3, 4


def level_to_star(level: float) -> float:
    """Star rating of a balanced osu! map with the speed rating of a Phigros chart at this level.

    Fitted on 337 official charts by star_conversion.py, with chords rated as one
    object. Phigros has no cursor aim, so the fit uses the speed rating and the
    balanced-map star formula rather than the aim of converted positions.
    Valid for levels 7 to 18. A single chart differs from it by about 0.7 stars.
    """
    level = max(level, 7.0)
    return 0.07197 * level**2 - 0.98233 * level + 5.70821


def notes_of(chart: dict):
    out = []
    offset = float(chart.get("offset", 0.0))
    for line in chart["judgeLineList"]:
        bpm = float(line["bpm"])
        for side, name in ((-1, "notesAbove"), (1, "notesBelow")):
            for n in line.get(name, []):
                out.append(dict(t=n["time"] * 1.875 / bpm + offset, kind=int(n["type"]), x=float(n.get("positionX", 0)),
                                hold=float(n.get("holdTime", 0)) * 1.875 / bpm, side=side))
    out.sort(key=lambda n: n["t"])
    return out, offset


def object_line(n, beat_ms):
    x = int(np.clip(256 + n["x"] * 28, 0, 512))
    y = 192 + 48 * n["side"]
    ms = int(round(n["t"] * 1000))
    if n["kind"] != HOLD or n["hold"] <= 0:
        return f"{x},{y},{ms},1,0,0:0:0:0:"
    beats = n["hold"] * 1000 / beat_ms
    spans = max(1, int(round(beats)))
    length = SV * 100 * beats / spans
    end = x + (int(length) if x < 256 else -int(length))
    return f"{x},{y},{ms},2,0,L|{end}:{y},{spans},{length:.3f}"


def osu_text(notes, bpm, offset, title, version, set_id, map_id):
    beat_ms = 60000 / bpm
    first = offset * 1000
    while first < 0:
        first += beat_ms
    head = f"""osu file format v14

[General]
AudioFilename: audio.ogg
AudioLeadIn: 0
PreviewTime: -1
Countdown: 0
SampleSet: Soft
StackLeniency: 0.7
Mode: 0
LetterboxInBreaks: 0
WidescreenStoryboard: 1

[Editor]
DistanceSpacing: 1
BeatDivisor: 4
GridSize: 8
TimelineZoom: 1

[Metadata]
Title:{title}
TitleUnicode:{title}
Artist:Phigros
ArtistUnicode:Phigros
Creator:Phigros
Version:{version}
Source:
Tags:
BeatmapID:{map_id}
BeatmapSetID:{set_id}

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:8
ApproachRate:9
SliderMultiplier:{SV}
SliderTickRate:1

[Events]
//Background and Video events

[TimingPoints]
{first:.3f},{beat_ms:.6f},4,2,1,100,1,0

[HitObjects]
"""
    return head + "\n".join(object_line(n, beat_ms) for n in notes) + "\n"


def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    levels = {}
    for row in (CORPUS / "difficulty.tsv").read_text().splitlines():
        cells = row.split("\t")
        levels[cells[0]] = [float(x) for x in cells[1:]]
    chart_dirs = sorted(CORPUS.glob("chart/*.0"))
    # held-out songs sort last so the train/test split is a simple index range
    chart_dirs.sort(key=lambda d: d.name[:-2] in HOLDOUT)
    rows, skipped, totals = [], [], {TAP: 0, DRAG: 0, HOLD: 0, FLICK: 0}
    rng = np.random.default_rng(7)
    set_id = 0
    for d in chart_dirs:
        sid = d.name[:-2]
        audio = CORPUS / "music" / f"{sid}.ogg"
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
            if len(bpms) != 1:
                skipped.append((sid, f"{name} has {len(bpms)} line BPMs"))
                continue
            bpm = bpms.pop()
            level = levels.get(sid, [])
            idx = LEVELS[name]
            if idx >= len(level):
                skipped.append((sid, f"{name} has no level"))
                continue
            notes, offset = notes_of(chart)
            for n in notes:
                totals[n["kind"]] += 1
            seen, kept = set(), []
            for n in notes:
                key = (round(n["t"], 3), n["x"], n["side"])
                if n["kind"] != DRAG and key not in seen:
                    seen.add(key)
                    kept.append(n)
            flicks = np.array([n["kind"] == FLICK for n in kept])
            pick = rng.random(len(kept)) < 0.5
            (OUT / "data" / folder).mkdir(parents=True, exist_ok=True)
            for half in (0, 1):
                use = [n for n, f, p in zip(kept, flicks, pick) if not f or p == bool(half)]
                map_id = set_id * 100 + idx * 10 + half + 1000000
                file = f"{name}-{half}.osu"
                (OUT / "data" / folder / file).write_text(osu_text(use, bpm, offset, sid, f"{name}{half}", set_id + 1, map_id))
                star = level_to_star(level[idx])
                rows.append(dict(BeatmapSetId=set_id + 1, Id=map_id, BeatmapSetFolder=folder, BeatmapFile=file, AudioFile="audio.ogg",
                                 StarRating=[star * s for s in SPEEDS], DifficultyRating=star, ModeInt=0, Ranked=1, UserId=0, HoldOut=sid in HOLDOUT, Song=sid,
                                 RankedDate=datetime(2023, 1, 1), SubmittedDate=datetime(2023, 1, 1), DifficultyName=f"{name}{half}"))
                made += 1
        if made:
            link = OUT / "data" / folder / "audio.ogg"
            if not link.exists():
                os.symlink(audio, link)
            set_id += 1
    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "metadata.parquet")
    n_train = df.loc[~df["HoldOut"], "BeatmapSetId"].nunique()
    print("mapsets", set_id, "train", n_train, "held out", set_id - n_train, "beatmaps", len(df))
    print("note counts before filtering", {"tap": totals[TAP], "drag": totals[DRAG], "hold": totals[HOLD], "flick": totals[FLICK]})
    print("skipped", skipped)


if __name__ == "__main__":
    main()
