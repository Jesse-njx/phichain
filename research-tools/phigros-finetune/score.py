"""Score generated osu maps against official Phigros charts on held-out songs.

A chord counts as one time point, because a generated map has a single timeline.
Notes are paired one to one within the tolerance, closest pairs first. Recall is
measured on non-drag points; precision is shown against non-drag points and
against all heads, because a generated note on a drag is still on something the
charter marked. The control shifts the generated notes by one sixteenth.

    python score.py [eval_dir] [chart_name]
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

WS = Path(__file__).resolve().parents[3]
CORPUS = WS / "main/research/overnight-study/corpus/chart"
TOL = 0.035
MERGE = 0.01
SONGS = ["Rrharil.TeamGrimoire", "BoundedQuietude.FiniteLimitvsSiLiS", "Incyde.YbeLL"]


def official(path):
    """Time points as (seconds, set of note types), and the main line BPM."""
    d = json.loads(Path(path).read_text())
    off = float(d.get("offset", 0.0))
    rows, count = [], {}
    for line in d["judgeLineList"]:
        bpm = float(line["bpm"])
        for side in ("notesAbove", "notesBelow"):
            for n in line.get(side, []):
                rows.append((n["time"] * 1.875 / bpm + off, int(n["type"])))
                count[bpm] = count.get(bpm, 0) + 1
    rows.sort()
    pts = []
    for t, k in rows:
        if pts and t - pts[-1][0] < MERGE:
            pts[-1][1].add(k)
        else:
            pts.append((t, {k}))
    return np.array([p[0] for p in pts]), [p[1] for p in pts], max(count, key=count.get)


def generated(folder):
    txt = Path(glob.glob(str(Path(folder) / "*.osu"))[0]).read_text().split("[HitObjects]")[1].strip().splitlines()
    t = np.array(sorted(int(l.split(",")[2]) for l in txt)) / 1000
    return t[np.concatenate([[True], np.diff(t) >= MERGE])]


def pair(a, b, tol=TOL):
    """One-to-one pairs, closest first. Returns index pairs into a and b."""
    cand = []
    for i, x in enumerate(a):
        lo, hi = np.searchsorted(b, [x - tol, x + tol])
        cand += [(abs(x - b[j]), i, j) for j in range(lo, min(hi + 1, len(b))) if abs(x - b[j]) <= tol]
    cand.sort()
    ua, ub, out = set(), set(), []
    for _, i, j in cand:
        if i not in ua and j not in ub:
            ua.add(i), ub.add(j), out.append((i, j))
    return out


def score(gen, ref, kinds):
    nd = np.array([bool(k - {2}) for k in kinds])
    rnd = ref[nd]
    p = pair(gen, rnd)
    hit = np.zeros(len(rnd), bool)
    hit[[j for _, j in p]] = True
    types = [k for k, keep in zip(kinds, nd) if keep]
    rec = {n: float(hit[[c in k for k in types]].mean()) if any(c in k for k in types) else float("nan") for n, c in (("tap", 1), ("hold", 3), ("flick", 4))}
    prec, r = len(p) / max(1, len(gen)), hit.mean()
    return dict(notes=len(gen), official=len(rnd), precision=prec, precision_any=len(pair(gen, ref)) / max(1, len(gen)), recall=float(r), f1=2 * prec * r / max(1e-9, prec + r), **rec)


def main():
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else WS / "artifacts/phigros-finetune/eval"
    chart = sys.argv[2] if len(sys.argv) > 2 else "IN"
    all_rows = {}
    for song in SONGS:
        ref, kinds, bpm = official(CORPUS / f"{song}.0/{chart}.json")
        for model in ("stock", "ft"):
            f = base / model / song
            if not glob.glob(str(f / "*.osu")):
                continue
            gen = generated(f)
            nd = np.array([bool(k - {2}) for k in kinds])
            d = np.array([gen[i] - ref[nd][j] for i, j in pair(gen, ref[nd], 0.06)])
            lag = float(np.median(d)) if len(d) else 0.0
            s = score(gen - lag, ref, kinds)
            s["lag_ms"] = round(lag * 1000, 1)
            s["shifted_precision"] = score(gen - lag + 60 / bpm / 4, ref, kinds)["precision"]
            all_rows.setdefault(model, []).append(s)
            print(f"{song[:18]:18s} {model:5s} " + " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in s.items()))
    for model, rows in all_rows.items():
        print("MEAN", model, " ".join(f"{k}={np.mean([r[k] for r in rows]):.3f}" for k in ("precision", "precision_any", "recall", "f1", "tap", "hold", "flick", "shifted_precision")))
    (base / f"scores-{chart}.json").write_text(json.dumps(all_rows, indent=1))


if __name__ == "__main__":
    main()
