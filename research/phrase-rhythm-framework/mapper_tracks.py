"""Merge several Mapperatorinator maps into one main track.

Each model run is one guess at the note set. A note is kept when a majority of
the runs place it, which drops notes a single run invented and restores notes a
single run skipped. Every kept note is on the main track; the secondary track
stays empty until there is evidence for a separate line.

    python mapper_tracks.py
"""
from __future__ import annotations

import glob
import json
from itertools import combinations
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import main_melody as M
import main_track as MT
import three_track as T

OUT = T.WS / "artifacts/mapper-three-track"
AGREE_TOL = 0.035
VOTES = 3
TRACKS = "ms"
SR = 22050
SONGS = [
    dict(title="Override", key="override", record="charts/override/override-prr-2026-11-08",
         work="charts/override/override-prr-2026-11-08/work", maps=["artifacts/mapperatorinator-test/override", "artifacts/mapperatorinator-test/override-consensus/*"]),
]


def map_notes(folder: Path):
    """Object start times from the .osu file, in seconds; slider ends are not notes."""
    osu = next(folder.glob("*.osu")).read_text().split("[HitObjects]")[1].strip().splitlines()
    return np.array(sorted(int(line.split(",")[2]) for line in osu)) / 1000


def near(t, b, tol):
    if len(b) == 0:
        return np.zeros(len(t), bool)
    i = np.searchsorted(b, t).clip(1, len(b) - 1)
    return np.minimum(abs(t - b[i - 1]), abs(t - b[i])) <= tol


def align(t, work, fps, z, fl, notes):
    """Remove the constant offset between osu time and this audio decode."""
    gate = np.ones(len(z["rms_vocals"]) + 10, bool)
    ats = [M.merged(M.attacks(fl["vocals"], fps, gate), notes["vocals"]),
           M.merged(M.attacks(fl["other"], fps, gate), notes["other"]),
           M.attacks(fl["bass"], fps, gate), M.attacks(z["env_drums"], fps, gate)]
    dev = []
    for b in ats:
        b = np.sort(b)
        i = np.searchsorted(b, t).clip(1, len(b) - 1)
        l, r = t - b[i - 1], t - b[i]
        dev.append(np.where(abs(l) <= abs(r), l, r))
    dev = np.array(dev)
    best = dev[abs(dev).argmin(0), np.arange(len(t))]
    return float(np.median(best[abs(best) < 0.05]))


def consensus(folders, work):
    """One timeline of notes with the number of runs that placed each."""
    notes, z, fps, _ = T.load(work)
    fl = MT.stem_flux(work)
    maps = []
    for f in folders:
        t = map_notes(f)
        maps.append(t - align(t, work, fps, z, fl, notes))
    pool = np.sort(np.concatenate(maps))
    groups = [[pool[0]]]
    for x in pool[1:]:
        if x - groups[-1][0] <= AGREE_TOL:
            groups[-1].append(x)
        else:
            groups.append([x])
    t = np.array([float(np.median(g)) for g in groups])
    votes = sum(near(t, m, AGREE_TOL).astype(int) for m in maps)
    return t[votes >= VOTES], votes[votes >= VOTES], len(maps)


def click(kind):
    n = int(0.012 * SR)
    i = np.arange(n)
    if kind == "m":
        return np.sin(2 * np.pi * 2000 * i / SR) * np.exp(-i / (0.004 * SR))
    return 0.8 * np.sign(np.sin(2 * np.pi * 800 * i / SR)) * np.exp(-i / (0.005 * SR))


def ticks(y, t, track):
    out = {}
    for k in TRACKS:
        m = np.zeros_like(y)
        c = click(k)
        for x in t[track == k]:
            i = int(x * SR)
            if i + len(c) < len(m):
                m[i : i + len(c)] += c
        out[k] = m
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.wav"):
        old.unlink()
    data = []
    for s in SONGS:
        rec = json.loads((T.WS / s["record"] / "phrase-rhythm-record.json").read_text())
        folders = [Path(p) for m in s["maps"] for p in sorted(glob.glob(str(T.WS / m)))]
        t, votes, runs = consensus(folders, T.WS / s["work"])
        dur = T.load(T.WS / s["work"])[3]
        track = np.full(len(t), "m")
        y, _ = librosa.load(str(rec["audio"]), sr=SR, mono=True)
        lanes = ticks(y, t, track)
        sf.write(OUT / f"{s['key']}-original.wav", y, SR, subtype="PCM_16")
        used = [k for k in TRACKS if (track == k).any()]
        for r in range(1, len(used) + 1):
            for combo in combinations(used, r):
                mix = 0.6 * y + 0.6 * sum(lanes[k] for k in combo)
                sf.write(OUT / f"{s['key']}-{''.join(combo)}.wav", np.clip(mix, -1, 1), SR, subtype="PCM_16")
        data.append(dict(title=s["title"], key=s["key"], duration=round(dur, 2), runs=runs,
                         ev=[[round(float(a), 3), str(b), int(v)] for a, b, v in zip(t, track, votes)]))
        print(s["title"], "runs", runs, "notes", len(t), "per s", round(len(t) / dur, 2), {k: int((track == k).sum()) for k in TRACKS})
        g = t[track == "m"]
        print("longest main gaps", [(round(float(g[i]), 1), round(float(g[i + 1] - g[i]), 2)) for i in np.argsort(np.diff(g))[-5:]])
    (OUT / "data.js").write_text("window.TRACKS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")


if __name__ == "__main__":
    main()
