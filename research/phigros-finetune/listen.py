"""Render whatever generated maps exist so far into a listening page.

Each track is mixed into its own WAV, so the browser only ever plays one file.
Generated notes are shifted by their median lag against the reference for that
song: the official chart where there is one, otherwise the stock run.

    python listen.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import score as S

WS = S.WS
EV = WS / "artifacts/phigros-finetune/eval"
MANIA = WS / "artifacts/phigros-finetune/eval-mania"
OUT = WS / "artifacts/phigros-finetune/listen-mania"
MUS = WS / "main/research/overnight-study/corpus/music"
SR = 22050
OVERRIDE = WS / "main/research/music-flow-study/override-emotion/music.mp3"
VOTE_RUNS = ["l15.5-s1", "l15.5-s2", "l15.5-s3", "l16.5-s1", "l16.5-s2"]


def has(p):
    return bool(glob.glob(str(p / "*.osu")))


def click():
    i = np.arange(int(0.012 * SR))
    return np.sin(2 * np.pi * 2000 * i / SR) * np.exp(-i / (0.004 * SR))


def lag(gen, ref):
    p = S.pair(gen, ref, 0.06)
    return float(np.median([gen[i] - ref[j] for i, j in p])) if p else 0.0


def vote(runs, need, tol=S.TOL):
    """Time points that at least `need` different runs agree on, at their median time."""
    ev = sorted((float(x), r) for r, t in enumerate(runs) for x in t)
    out, cur = [], []
    for x, r in ev + [(float("inf"), -1)]:
        if cur and x - cur[0][0] > tol:
            if len({b for _, b in cur}) >= need:
                out.append(float(np.median([a for a, _ in cur])))
            cur = []
        cur.append((x, r))
    return np.array(out)


def songs():
    for song in S.SONGS:
        if not has(MANIA / "ft" / song):
            continue
        ref, kinds, _ = S.official(S.CORPUS / f"{song}.0/IN.json")
        ref = ref[[bool(k - {2}) for k in kinds]]
        tracks = {}
        for path, label in ((MANIA / "ft" / song, "Mania fine-tuned"), (MANIA / "stock" / song, "Mania stock"), (EV / "ft" / song, "Standard fine-tuned")):
            if has(path):
                g = S.generated(path)
                tracks[label] = g - lag(g, ref)
        tracks["Official (no drags)"] = ref
        yield song.split(".")[0], song.split(".")[0], MUS / f"{song}.ogg", tracks
    first = MANIA / "override-ft/l15.5-s1"
    if has(first):
        ref = S.generated(WS / "artifacts/mapperatorinator-test/override")
        tracks = {}
        for path, label in ((first, "Mania fine-tuned"), (MANIA / "override-stock/l15.5-s1", "Mania stock"), (EV / "override-ft/d6.0-s1", "Standard fine-tuned")):
            if has(path):
                g = S.generated(path)
                tracks[label] = g - lag(g, ref)
        tracks["Standard stock"] = ref
        runs = [MANIA / "override-ft" / r for r in VOTE_RUNS]
        if all(has(r) for r in runs):
            al = [g - lag(g, ref) for g in map(S.generated, runs)]
            voted = vote(al, 3)
            (MANIA / "override-vote.json").write_text(json.dumps(dict(runs=VOTE_RUNS, need=3, t=[round(float(x), 3) for x in voted])))
            tracks = {"Mania fine-tuned vote (3 of 5)": voted, **tracks}
            print("agreement", [[round(len(S.pair(a, b)) / len(a), 2) for b in al] for a in al], "vote 2/3/4/5", [len(vote(al, n)) for n in (2, 3, 4, 5)])
        yield "Override", "Override", OVERRIDE, tracks


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data, c = [], click()
    for title, key, audio, tracks in songs():
        y, _ = librosa.load(str(audio), sr=SR, mono=True)
        sf.write(OUT / f"{key}-music.wav", 0.6 * y, SR, subtype="PCM_16")
        row = dict(title=title, duration=round(len(y) / SR, 2), music=f"{key}-music.wav", tracks=[])
        for i, (label, t) in enumerate(tracks.items()):
            m = np.zeros_like(y)
            for x in t:
                k = int(x * SR)
                if 0 <= k and k + len(c) < len(m):
                    m[k : k + len(c)] += c
            f = f"{key}-{i}.wav"
            sf.write(OUT / f, np.clip(0.6 * y + 0.6 * m, -1, 1), SR, subtype="PCM_16")
            row["tracks"].append(dict(label=label, file=f, t=[round(float(x), 3) for x in t]))
            print(title, label, len(t))
        data.append(row)
    (OUT / "data.js").write_text("window.SONGS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")


if __name__ == "__main__":
    main()
