"""Measure how Phigros level relates to osu! star rating and note density.

Every chart is converted the way convert.py converts it (no drags, chords on one
timeline stay as separate objects) and rated with rosu-pp, the same library the
Mapperatorinator repository uses. Candidate level-to-star functions are compared
by five-fold cross-validation against the current level / 2 rule.

    ../../../artifacts/external/Mapperatorinator/.venv/bin/python star_conversion.py
"""
from __future__ import annotations

import glob
import json
from collections import Counter
from pathlib import Path

import numpy as np
import rosu_pp_py as rosu

import convert as C

WS = Path(__file__).resolve().parents[3]
RAW = WS / "main/research/arrangement-training"
CORPUS = WS / "main/research/overnight-study/corpus"
OUT = WS / "artifacts/phigros-finetune/star-conversion"
MERGE = 0.01
# rosu-pp star rating when aim and speed are equal to r is 1.15^(1/3) * 0.027 * 5 * r / 0.0675 (checked below).
BALANCED = 1.15 ** (1 / 3) * 0.027 * 5 / 0.0675


def stars(text):
    a = rosu.Difficulty().calculate(rosu.Beatmap(content=text))
    return a.stars, a.aim, a.speed


def density(t):
    t = np.sort(t)
    pts = t[np.concatenate([[True], np.diff(t) >= MERGE])]
    if len(pts) < 8 or pts[-1] <= pts[0]:
        return float("nan"), float("nan")
    span = pts[-1] - pts[0]
    win = np.searchsorted(pts, pts + 5.0) - np.arange(len(pts))
    return (len(pts) - 1) / span, float(win.max()) / 5.0


def measure(chart, level, name, song):
    notes, offset = C.notes_of(chart)
    count = Counter()
    for line in chart["judgeLineList"]:
        count[float(line["bpm"])] += len(line.get("notesAbove", [])) + len(line.get("notesBelow", []))
    bpm = count.most_common(1)[0][0]
    seen, kept = set(), []
    for n in notes:
        key = (round(n["t"], 3), n["x"], n["side"])
        if n["kind"] != C.DRAG and key not in seen:
            seen.add(key)
            kept.append(n)
    if len(kept) < 8:
        return None
    # osu! has one cursor, so a chord is rated as one object; two objects on the same
    # millisecond would otherwise read as an impossible stream.
    single = []
    for n in kept:
        if not single or n["t"] - single[-1]["t"] >= MERGE:
            single.append(n)
    s, a, sp = stars(C.osu_text(single, bpm, offset, song, name, 1, 1))
    d, peak = density(np.array([n["t"] for n in kept]))
    d_all, peak_all = density(np.array([n["t"] for n in notes]))
    return dict(song=song, chart=name, level=level, stars=s, aim=a, speed=sp, density=d, peak=peak, density_with_drags=d_all, peak_with_drags=peak_all)


def corpus_rows():
    rows = []
    for m in json.loads((RAW / "manifest.json").read_text()):
        if m.get("format_version") != 3:
            continue
        r = measure(json.loads((RAW / m["local_path"]).read_text()), float(m["constant"]), "IN", m["song_id"])
        if r:
            rows.append(r)
    for line in (CORPUS / "difficulty.tsv").read_text().strip().splitlines():
        p = line.split("\t")
        at = CORPUS / f"chart/{p[0]}.0/AT.json"
        if len(p) >= 5 and at.exists():
            r = measure(json.loads(at.read_text()), float(p[4]), "AT", p[0])
            if r:
                rows.append(r)
    return rows


def cv(x, y, fit, folds=5, seed=7):
    idx = np.random.default_rng(seed).permutation(len(x))
    err = np.zeros(len(x))
    for k in range(folds):
        test = idx[k::folds]
        train = np.setdiff1d(idx, test)
        err[test] = fit(x[train], y[train])(x[test]) - y[test]
    return float(np.mean(np.abs(err)))


def poly(deg):
    return lambda x, y: np.poly1d(np.polyfit(x, y, deg))


def exp_fit(x, y):
    p = np.polyfit(x, np.log(y), 1)
    return lambda v: np.exp(p[1] + p[0] * v)


def generated():
    rows = []
    roots = {"stock override d6.0 s1": ("artifacts/mapperatorinator-test/override", 6.0)}
    for f in glob.glob(str(WS / "artifacts/mapperatorinator-test/override-consensus/*")):
        roots[f"stock override {Path(f).name}"] = (str(Path(f).relative_to(WS)), float(Path(f).name[1:4]))
    for model in ("stock", "ft"):
        for f in glob.glob(str(WS / f"artifacts/phigros-finetune/eval/{model}/*")):
            roots[f"{model} {Path(f).name[:12]}"] = (str(Path(f).relative_to(WS)), 8.0)
    for f in glob.glob(str(WS / "artifacts/phigros-finetune/eval/override-ft/*")):
        roots[f"ft override {Path(f).name}"] = (str(Path(f).relative_to(WS)), float(Path(f).name[1:4]))
    for name, (rel, want) in roots.items():
        osu = glob.glob(str(WS / rel / "*.osu"))
        if not osu:
            continue
        text = Path(osu[0]).read_text()
        s, a, sp = stars(text)
        t = np.array([int(l.split(",")[2]) for l in text.split("[HitObjects]")[1].strip().splitlines()]) / 1000
        d, peak = density(t)
        rows.append(dict(name=name, requested=want, stars=round(s, 2), aim=round(a, 2), speed=round(sp, 2), density=round(d, 2), peak=round(peak, 2)))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = corpus_rows()
    (OUT / "charts.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0))
    L = np.array([r["level"] for r in rows])
    S = np.array([r["speed"] * BALANCED for r in rows])
    print("raw stars median", round(float(np.median([r["stars"] for r in rows])), 2), "aim", round(float(np.median([r["aim"] for r in rows])), 2), "speed", round(float(np.median([r["speed"] for r in rows])), 2))
    D = np.array([r["density"] for r in rows])
    print("charts", len(rows), "IN", sum(r["chart"] == "IN" for r in rows), "AT", sum(r["chart"] == "AT" for r in rows), "level range", L.min(), L.max())
    print("corr(level,stars)", round(float(np.corrcoef(L, S)[0, 1]), 3), "corr(level,density)", round(float(np.corrcoef(L, D)[0, 1]), 3), "corr(density,stars)", round(float(np.corrcoef(D, S)[0, 1]), 3))
    print("level/2 MAE", round(float(np.mean(np.abs(L / 2 - S))), 3), "bias", round(float(np.mean(L / 2 - S)), 3))
    for name, fit in (("linear", poly(1)), ("quadratic", poly(2)), ("cubic", poly(3)), ("exponential", exp_fit)):
        print(name, "cv MAE stars", round(cv(L, S, fit), 3), "cv MAE density", round(cv(L, D, fit), 3))
    print("quadratic stars", np.polyfit(L, S, 2).round(5).tolist(), "linear stars", np.polyfit(L, S, 1).round(4).tolist())
    print("density ~ level linear", np.polyfit(L, D, 1).round(4).tolist(), "stars ~ density linear", np.polyfit(D, S, 1).round(4).tolist())
    print("cubic star_eq", np.polyfit(L, S, 3).round(6).tolist(), "fitted", {v: round(float(np.polyval(np.polyfit(L, S, 3), v)), 2) for v in (7, 10, 12, 13, 14, 15, 16, 17, 18)}, "quad fitted", {v: round(float(np.polyval(np.polyfit(L, S, 2), v)), 2) for v in (7, 10, 12, 13, 14, 15, 16, 17, 18)})
    print("level  n  stars(p10/50/90) aim speed  density peak | density with drags")
    for lo in range(10, 18):
        m = (L >= lo) & (L < lo + 1)
        if m.sum():
            g = lambda k: np.nanmedian([r[k] for r, keep in zip(rows, m) if keep])
            print(f"{lo:2d}-{lo + 1:2d} {int(m.sum()):3d}  {np.percentile(S[m], 10):.2f}/{np.percentile(S[m], 50):.2f}/{np.percentile(S[m], 90):.2f}  {g('aim'):.2f} {g('speed'):.2f}  {g('density'):.2f} {g('peak'):.2f} | {g('density_with_drags'):.2f}")
    print("generated maps")
    for r in generated():
        print(r)


if __name__ == "__main__":
    main()
