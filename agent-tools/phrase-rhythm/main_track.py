"""The main track: the line of events a listener follows, whatever makes them.

It is not a pitch line. Each candidate grid slot (1/4 and 1/3 beat) gets per-stem
onset evidence, and a model trained on official charts, the record of what
charters chose to follow, scores the slot. Scores on corpus songs are always
out-of-fold: a song is never scored by a model that saw its chart.

Run with the music-flow-study venv:
    python main_track.py train
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

import prr_audio
from prr import chart_heads
from three_track import CAL, corpus_rows, hit

FRACS = [0.0, 0.25, 1 / 3, 0.5, 2 / 3, 0.75]
BANDS = dict(vocals=(150, 8000), other=(150, 11000), bass=(30, 400))
TOL = 0.025
MODEL = CAL / "main-track-model.pkl"


def stem_flux(work: Path) -> dict:
    cache = work / "flux-stems.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    out = {s: prr_audio.linear_flux(prr_audio.load_mono(work / "aligned" / f"{s}.wav"), *b) for s, b in BANDS.items()}
    np.savez_compressed(cache, **out)
    return out


def norm(e):
    pos = e[e > 0]
    return e / max(float(np.percentile(pos, 99.5)) if len(pos) else 1.0, 1e-9)


def features(work: Path, beat: float, offset: float, t0: float, t1: float, grid_features=True):
    ev = json.loads((work / "evidence.json").read_text())
    fps = float(ev["env_fps"])
    z = np.load(work / "evidence.npz")
    fl = stem_flux(work)
    env = {**fl, "drums": z["env_drums"], "kick": z["env_act_kick"], "snare": z["env_act_snare"], "hat": z["env_act_hat"], "mix": z["env_mix"]}
    kmin, kmax = int(np.floor((t0 - offset) / beat)), int(np.ceil((t1 - offset) / beat))
    ts, fid = [], []
    for k in range(kmin, kmax):
        for j, f in enumerate(FRACS):
            t = offset + (k + f) * beat
            if t0 <= t < t1:
                ts.append(t)
                fid.append(j)
    ts, fid = np.array(ts), np.array(fid)
    idx = lambda x, n: np.clip(np.round(x * fps).astype(int), 0, n - 1)
    w = max(3, int(round(beat * fps)))
    cols, names = [], []
    for name, e in env.items():
        e = norm(e.astype(np.float64))
        peak, base = maximum_filter1d(e, 9), uniform_filter1d(e, 2 * w + 1)
        i = idx(ts, len(e))
        cols += [peak[i], peak[i] / (base[i] + 1e-3)]
        names += [f"{name}_peak", f"{name}_contrast"]
        if name in ("mix", "other", "vocals", "drums"):
            lag = 16 * beat
            cols.append(0.5 * (peak[idx(ts - lag, len(e))] + peak[idx(ts + lag, len(e))]))
            names.append(f"{name}_repeat4bars")
    rms = {s: z[f"rms_{s}"].astype(np.float64) for s in ("vocals", "other", "bass", "drums")}
    total = sum(np.asarray(v)[: min(map(len, rms.values()))] for v in rms.values()) + 1e-9
    for s, r in rms.items():
        i = idx(ts, len(total))
        cols += [r[i] / max(float(np.percentile(r, 95)), 1e-9), r[i] / total[i]]
        names += [f"{s}_level", f"{s}_share"]
    from prr_audio import frame_times

    for s in ("vocals", "other", "bass"):
        b = np.load(work / f"bp-{s}.npz")
        ft = frame_times(len(b["onset"]))
        i = np.clip(np.searchsorted(ft, ts), 1, len(ft) - 2)
        on, no = b["onset"].max(1), b["note"].max(1)
        cols += [np.max([on[i - 1], on[i], on[i + 1]], axis=0), no[i]]
        names += [f"{s}_bp_onset", f"{s}_bp_note"]
    if grid_features:
        cols.append(fid.astype(float))
        names.append("slot_type")
    X = np.column_stack(cols)
    # the gate: something in the audio must actually start here
    peaks = np.column_stack([X[:, names.index(f"{n}_peak")] for n in ("vocals", "other", "bass", "drums", "mix")])
    contrast = np.column_stack([X[:, names.index(f"{n}_contrast")] for n in ("vocals", "other", "bass", "drums", "mix")])
    gate = ((peaks >= 0.12) & (contrast >= 1.5)).any(axis=1)
    return ts, X, names, gate, fid


def nms(ts, p, gap):
    keep, used = [], np.zeros(0)
    for i in np.argsort(-p):
        if not len(used) or np.abs(used - ts[i]).min() >= gap:
            keep.append(i)
            used = np.append(used, ts[i])
    return np.sort(keep)


def dataset():
    data = []
    for s, c, work in corpus_rows():
        if c.get("other_bpms"):
            continue
        heads, d = chart_heads(s["chart"])
        H = np.unique(np.round([h["seconds"] for h in heads], 3))
        beat, off = 60.0 / c["grid_bpm"], c.get("offset_sign", 1) * float(d.get("offset", 0.0))
        ts, X, names, gate, fid = features(work, beat, off, H[0] - 1, H[-1] + 1)
        y = np.zeros(len(ts), bool)
        i = np.clip(np.searchsorted(ts, H), 1, len(ts) - 1)
        near = np.where(np.abs(H - ts[i - 1]) <= np.abs(H - ts[i]), i - 1, i)
        y[near[np.abs(H - ts[near]) <= TOL]] = True
        data.append(dict(id=s["id"], title=s["title"], beat=beat, ts=ts, X=X, y=y, gate=gate, H=H, span=H[-1] - H[0]))
        print("features", s["id"][:30], len(ts), f"pos {y.mean():.2f} gate {gate.mean():.2f} heads-through-gate {gate[y].mean():.2f}", flush=True)
    return data, names


def fit(X, y):
    return HistGradientBoostingClassifier(max_iter=220, learning_rate=0.07, max_leaf_nodes=31, min_samples_leaf=60, random_state=0).fit(X, y)


def report(data, oof, label):
    print(f"\n{label}\n thr  precision chance  lift  notes/s heads-covered | worst-song precision")
    best = None
    for thr in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        rows = []
        for d, p in zip(data, oof):
            q = (p >= thr) & d["gate"]
            if q.sum() < 8:
                continue
            ts = d["ts"][q]
            ts = ts[nms(ts, p[q], 0.2 * d["beat"])]
            pr, ch = float(hit(ts, d["H"]).mean()), float(np.mean([hit(ts + k * d["beat"] / 4, d["H"]).mean() for k in (-3, -2, -1, 1, 2, 3)]))
            rows.append((pr, ch, len(ts) / d["span"], float(hit(d["H"], ts).mean())))
        if rows:
            v = np.array(rows)
            print(f" {thr:.1f}  {v[:, 0].mean():8.3f} {v[:, 1].mean():6.3f} {(v[:, 0] - v[:, 1]).mean():+6.3f} {v[:, 2].mean():7.2f} {v[:, 3].mean():10.3f}    | {v[:, 0].min():.2f}  ({len(v)} songs)")


def train():
    data, names = dataset()
    groups = np.concatenate([[i] * len(d["ts"]) for i, d in enumerate(data)])
    X, y = np.vstack([d["X"] for d in data]), np.concatenate([d["y"] for d in data])
    grid_col = names.index("slot_type")
    for label, cols in (("audio + slot type", np.arange(X.shape[1])), ("audio only", np.delete(np.arange(X.shape[1]), grid_col))):
        p = np.zeros(len(y))
        for tr, te in GroupKFold(5).split(X, y, groups):
            p[te] = fit(X[tr][:, cols], y[tr]).predict_proba(X[te][:, cols])[:, 1]
        oof = [p[groups == i] for i in range(len(data))]
        report(data, oof, label)
        if label.startswith("audio +"):
            full = fit(X, y)
            MODEL.write_bytes(pickle.dumps(dict(model=full, names=names, oof={d["id"]: (d["ts"], o) for d, o in zip(data, oof)})))


# ---------------------------------------------------------------- viewer data

MAIN_THR = 0.6
SEC_LOW = 0.35
SRC = ("vocals", "other", "drums", "bass")


def tracks(beat, ts, X, names, gate, p):
    """Main = confident followed events; secondary = weaker real attacks that
    stay clear of the main track. Both must pass the onset gate."""
    q = (p >= MAIN_THR) & gate
    mt, mp = ts[q], p[q]
    src = np.column_stack([X[:, names.index(f"{n}_peak")] * X[:, names.index(f"{n}_contrast")] for n in SRC]).argmax(1)[q]
    k = nms(mt, mp, 0.2 * beat)
    mt, mp, src = mt[k], mp[k], src[k]
    q2 = (p >= SEC_LOW) & (p < MAIN_THR) & gate
    st, sp = ts[q2], p[q2]
    if len(mt) and len(st):
        far = np.abs(st[:, None] - mt[None, :]).min(1) > 0.2 * beat
        st, sp = st[far], sp[far]
    k2 = nms(st, sp, 0.5 * beat) if len(st) else []
    return mt, mp, src, st[k2] if len(st) else st


def viewer():
    import os
    from urllib.parse import quote

    import three_track as T

    m = pickle.loads(MODEL.read_bytes())
    songs = []

    def add(title, audio, r, mt, mp, src, st, H=None):
        row = dict(title=title, audio=quote(os.path.relpath(audio, T.VIEW)), duration=round(r["duration"], 2), beat=round(r["beat"], 5),
                   bars=[round(a, 3) for a, _ in r["bars"]],
                   main=[[round(float(t), 3), SRC[int(c)][0], round(float(x), 2)] for t, c, x in zip(mt, src, mp)],
                   secondary=[[round(float(t), 3)] for t in st],
                   drums=[[round(n["st"], 3), int(n["accent"])] for n in r["drums"]])
        row["heldout"] = None if H is None else round(float(hit(np.asarray(mt), H).mean()), 3)
        row["heldoutSec"] = None if H is None or not len(st) else round(float(hit(np.asarray(st), H).mean()), 3)
        songs.append(row)
        print(title, "main", len(mt), "secondary", len(st), "beat", len(row["drums"]), "held-out precision", row["heldout"], "secondary", row["heldoutSec"])

    for title, rel, _ in T.PILOTS[:2]:
        d = T.WS / rel
        rec = json.loads((d / "phrase-rhythm-record.json").read_text())
        gp = rec["layer_phase_alignment"].get("grid_phase", {})
        shift = gp.get("shift_ms", 0.0) / 1000 if gp.get("applied") else 0.0
        bars = [(b["seconds"][0] + shift, b["seconds"][1] + shift) for b in rec["MF4_bars"]]
        off = rec["grid"]["offset_seconds"] + shift
        r = T.build(d / "work", rec["grid"]["bpm"], off, bars)
        ts, X, names, gate, _ = features(d / "work", r["beat"], off, 0.0, r["duration"])
        p = m["model"].predict_proba(X)[:, 1]
        add(title, Path(rec["audio"]), r, *tracks(r["beat"], ts, X, names, gate, p))
    by = {s["id"]: (s, c, w) for s, c, w in corpus_rows()}
    for sid in ["Rrharil.TeamGrimoire"] + T.CORPUS_PICKS:
        s, c, work = by[sid]
        heads, d = chart_heads(s["chart"])
        H = np.unique(np.round([h["seconds"] for h in heads], 3))
        off = c.get("offset_sign", 1) * float(d.get("offset", 0.0))
        r = T.build(work, c["grid_bpm"], off)
        ts, X, names, gate, _ = features(work, r["beat"], off, H[0] - 1, H[-1] + 1)
        add(s["title"], s["music"], r, *tracks(r["beat"], ts, X, names, gate, m["oof"][sid][1]), H=H)
    T.VIEW.mkdir(parents=True, exist_ok=True)
    (T.VIEW / "data.js").write_text("window.TT = " + json.dumps(songs, ensure_ascii=False, separators=(",", ":")) + ";\n")


if __name__ == "__main__":
    {"train": train, "viewer": viewer}[sys.argv[1]]()
