"""One track: every real attack of whichever stem is in front.

No trained model, no comparison with charts and no grid snapping. Each 2-bar
block names its foreground stem (vocals when they are present and prominent,
otherwise the instrument stem), and the track is that stem's own attacks at
their detected times. Ticks are mixed into a rendered WAV so the check does
not depend on browser audio scheduling.

    python main_melody.py
"""
from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import maximum_filter1d
from scipy.signal import find_peaks

import main_track
import prr_audio
import three_track as T

OUT = T.WS / "artifacts/main-melody-check"
MERGE = 0.05
LOCAL_PROM = 0.15
GAP_BEATS = 0.45  # a stretch this empty is filled from the next stem down
SONGS = [
    ("Override", "charts/override/override-prr-2026-11-08", "charts/override/override-prr-2026-11-08/work"),
    ("NightTheater", "charts/other/nighttheater/prr", "charts/other/nighttheater/prr/work"),
    ("Rrharil", "charts/other/rrharil-prr-2026-11-08", "artifacts/phrase-rhythm-calibration/songs/Rrharil.TeamGrimoire/work"),
]


def attacks(flux, fps, gate):
    """Flux peaks judged against the surrounding few seconds, so a quiet passage
    is not silenced by the loudest part of the song."""
    flux = flux.astype(np.float64)
    local = maximum_filter1d(flux, int(4 * fps))
    pk, pr = find_peaks(flux, distance=max(1, int(0.06 * fps)), prominence=1e-9)
    pk = pk[pr["prominences"] >= LOCAL_PROM * local[pk]]
    pk = pk[flux[pk] >= 0.02 * float(np.percentile(flux, 99))]
    return pk[gate[np.minimum(pk, len(gate) - 1)]] / fps


def merged(flux_t, notes):
    """Flux attacks plus decoded note starts, one event per attack."""
    t = np.sort(np.concatenate([flux_t, [n["t"] for n in notes]]))
    out = []
    for x in t:
        if not out or x - out[-1] >= MERGE:
            out.append(float(x))
    return np.array(out)


def main_line(work: Path, bars):
    notes, z, fps, dur = T.load(work)
    fl = main_track.stem_flux(work)
    rv, ro = z["rms_vocals"].astype(float), z["rms_other"].astype(float)
    n = min(len(rv), len(ro))
    active = rv > 0.15 * np.percentile(rv[rv > rv.max() * 0.02], 90)
    front = (rv[:n] / (rv[:n] + ro[:n] + 1e-9)) >= 0.3
    vocal = active[:n] & front
    lead = np.zeros(n, bool)
    blocks = [(bars[k][0], bars[min(k + 1, len(bars) - 1)][1]) for k in range(0, len(bars), 2)]
    src = []
    for a, b in blocks:
        i, j = int(a * fps), min(n, int(b * fps))
        if j > i and vocal[i:j].mean() >= 0.3:
            lead[i:j] = True
        src.append([round(a, 3), "v" if j > i and vocal[i:j].mean() >= 0.3 else "o"])
    ov = ro > 0.1 * np.percentile(ro[ro > ro.max() * 0.02], 90)
    sounding = lambda r: r > 0.03 * np.percentile(r[r > r.max() * 0.02], 90)
    rb, rd = z["rms_bass"].astype(float), z["rms_drums"].astype(float)
    tv = merged(attacks(fl["vocals"], fps, active), notes["vocals"])
    to = merged(attacks(fl["other"], fps, sounding(ro)), notes["other"])
    tb = merged(attacks(fl["bass"], fps, sounding(rb)), notes["bass"])
    td = attacks(z["env_drums"], fps, sounding(rd))
    idx = lambda t: np.minimum((t * fps).astype(int), n - 1)
    beat = (bars[0][1] - bars[0][0]) / 4
    # the foreground stem of each block first, then every other stem fills what is still empty
    ev = list(zip(tv[lead[idx(tv)]], "v" * len(tv))) + list(zip(to[~lead[idx(to)]], "o" * len(to)))
    ev = [(float(a), b) for a, b in ev]
    have = np.sort([a for a, _ in ev])
    for ts, k in ((tv, "v"), (to, "o"), (tb, "b"), (td, "d")):
        add = []
        for x in ts:
            i = np.searchsorted(have, x)
            left = have[i - 1] if i > 0 else -1e9
            right = have[i] if i < len(have) else 1e9
            prev = add[-1] if add else -1e9
            if min(x - left, right - x, x - prev) >= GAP_BEATS * beat:
                add.append(float(x))
        ev += [(x, k) for x in add]
        have = np.sort(np.concatenate([have, add]))
    ev.sort()
    t = np.array([a for a, _ in ev])
    kinds = np.array([b for _, b in ev])
    return t, kinds, src, dur


def render(audio, ticks, path):
    sr = 22050
    y, _ = librosa.load(str(audio), sr=sr, mono=True)
    m = np.zeros_like(y)
    n = int(0.012 * sr)
    click = np.sin(2 * np.pi * 2000 * np.arange(n) / sr) * np.exp(-np.arange(n) / (0.004 * sr))
    for t in ticks:
        i = int(t * sr)
        if i + n < len(m):
            m[i : i + n] += click
    sf.write(path, np.clip(0.6 * y + 0.6 * m, -1, 1), sr, subtype="PCM_16")
    return y


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = []
    for title, rel, w in SONGS:
        rec = json.loads((T.WS / rel / "phrase-rhythm-record.json").read_text())
        bars = [tuple(b["seconds"]) for b in rec["MF4_bars"]]
        t, k, src, dur = main_line(T.WS / w, bars)
        f = f"{title}.wav"
        render(rec["audio"], t, OUT / f)
        sf.write(OUT / f"{title}-original.wav", librosa.load(str(rec["audio"]), sr=22050, mono=True)[0], 22050, subtype="PCM_16")
        data.append(dict(title=title, duration=round(dur, 2), ticked=f, original=f"{title}-original.wav", ev=[[round(float(a), 3), b] for a, b in zip(t, k)]))
        print(title, "events", len(t), "per s", round(len(t) / dur, 2), *[x for c, name in (("v", "vocal"), ("o", "instrument"), ("b", "bass"), ("d", "drums")) for x in (name, int((k == c).sum()))])
    (OUT / "data.js").write_text("window.ML = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")


if __name__ == "__main__":
    main()
