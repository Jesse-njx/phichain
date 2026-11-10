"""Fit Phigros level to 4K osu!mania star rating on charts of level 14 to 18.

    ../../../artifacts/external/Mapperatorinator/.venv/bin/python fit_mania_star.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import rosu_pp_py as rosu

import convert as C
import convert_mania as M

WS = Path(__file__).resolve().parents[3]
RAW = WS / "main/research/arrangement-training"
CORPUS = WS / "main/research/overnight-study/corpus"
OUT = WS / "artifacts/phigros-finetune/star-conversion"
LOW, HIGH = 14.0, 18.0


def rate(chart, level, song, name):
    notes, offset = C.notes_of(chart)
    bpm = Counter(float(l["bpm"]) for l in chart["judgeLineList"]).most_common(1)[0][0]
    text = M.osu_text(notes, bpm, offset, song, name, 1, 1)
    return dict(song=song, chart=name, level=level, stars=rosu.Difficulty().calculate(rosu.Beatmap(content=text)).stars)


def rows():
    out = []
    for m in json.loads((RAW / "manifest.json").read_text()):
        if m.get("format_version") == 3 and LOW <= float(m["constant"]) <= HIGH:
            out.append(rate(json.loads((RAW / m["local_path"]).read_text()), float(m["constant"]), m["song_id"], "IN"))
    for line in (CORPUS / "difficulty.tsv").read_text().strip().splitlines():
        p = line.split("\t")
        at = CORPUS / f"chart/{p[0]}.0/AT.json"
        if len(p) >= 5 and at.exists() and LOW <= float(p[4]) <= HIGH:
            out.append(rate(json.loads(at.read_text()), float(p[4]), p[0], "AT"))
    return out


def cv(x, y, deg, seed=7):
    idx = np.random.default_rng(seed).permutation(len(x))
    err = np.zeros(len(x))
    for k in range(5):
        test = idx[k::5]
        train = np.setdiff1d(idx, test)
        err[test] = np.polyval(np.polyfit(x[train], y[train], deg), x[test]) - y[test]
    return float(np.mean(np.abs(err)))


def main():
    r = rows()
    (OUT / "charts-mania4k-14-18.json").write_text(json.dumps(r, ensure_ascii=False))
    L = np.array([x["level"] for x in r])
    S = np.array([x["stars"] for x in r])
    print("charts", len(r), "IN", sum(x["chart"] == "IN" for x in r), "AT", sum(x["chart"] == "AT" for x in r), "range", L.min(), L.max())
    for deg in (1, 2, 3):
        p = np.polyfit(L, S, deg)
        print(f"deg{deg} cvMAE {cv(L, S, deg):.4f} coef {[round(float(c), 6) for c in p]} " + str({v: round(float(np.polyval(p, v)), 2) for v in (14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18)}))
    for lo in (14, 15, 16, 17):
        m = (L >= lo) & (L < lo + 1)
        print(lo, int(m.sum()), "p10/50/90", np.percentile(S[m], [10, 50, 90]).round(2).tolist())


if __name__ == "__main__":
    main()
