"""Three-track rhythm output: beat, main melody, secondary.

A rhythm game chart answers to at most three things in the music: a steady
beat (drums and effects, normally repeating per bar), the main melody (the
part that matters most) and an occasional secondary line. This module reduces
the cached PRR evidence to exactly those three tracks and prefers leaving a
note out over emitting one that is not in the song.

Run with the music-flow-study venv:
    python three_track.py eval                # corpus precision versus official heads
    python three_track.py viewer              # writes artifacts/three-track-viewer/data.js
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
from scipy.signal import find_peaks

import corpus
import prr_audio
from prr import chart_heads

WS = Path(__file__).resolve().parents[3]
CAL = WS / "artifacts/phrase-rhythm-calibration"
VIEW = WS / "artifacts/three-track-viewer"

P = dict(
    # a melody note must be a clear attack, long enough to hear, and on the grid
    min_dur=0.09,
    min_dur_beats=0.2,
    onset_entry=0.70,
    onset_rearticulation=0.82,
    min_activation=0.45,
    max_snap_s=0.028,
    pitch=(55, 96),
    rms_rel=0.25,          # relative to the stem's p90 RMS while sounding
    jump=12,               # semitones; a weak note this far from both neighbours is dropped
    vocal_bar_share=0.22,  # voiced share of a bar for vocals to be the candidate lead
    block_bars=4,          # the lead source is decided per block, never per note
    repeat_support=True,
    weak_onset=0.45,
    # secondary is deliberately sparse
    sec_onset=0.8,
    sec_min_dur=0.2,
    sec_gap_beats=0.5,
    # beat track
    beat_hit_share=0.7,
    beat_max_slots=8,
)


def load(work: Path):
    ev = json.loads((work / "evidence.json").read_text())
    z = np.load(work / "evidence.npz")
    notes = {}
    n_max = max((n["end_frame"] for s in ("vocals", "other", "bass") for n in json.loads((work / f"path-{s}.json").read_text())["notes"]), default=0)
    ft = prr_audio.frame_times(n_max + 2)
    fps = float(ev["env_fps"])
    for s in ("vocals", "other", "bass"):
        rms = z[f"rms_{s}"]
        ref = float(np.percentile(rms[rms > rms.max() * 0.02], 90)) if (rms > rms.max() * 0.02).any() else 1.0
        out = []
        for n in json.loads((work / f"path-{s}.json").read_text())["notes"]:
            t, e = float(ft[n["start_frame"]]), float(ft[n["end_frame"]])
            i = min(len(rms) - 1, int(t * fps))
            j = min(len(rms), max(i + 1, int(min(e, t + 0.08) * fps)))
            out.append(dict(t=t, end=e, pitch=n["pitch"], act=n["activation"], onset=n["onset"],
                            rearticulation=n["kind"] == "rearticulation", rms=float(rms[i:j].max()) / ref, stem=s))
        notes[s] = out
    return notes, z, fps, float(ev["duration"])


def grid(bpm, offset, duration, bars=None):
    beat = 60.0 / bpm
    if bars is None:
        a = offset - np.ceil(offset / (4 * beat)) * 4 * beat
        bars = [(float(x), float(x + 4 * beat)) for x in np.arange(a, duration, 4 * beat)]
    return beat, [tuple(b) for b in bars]


def snap(t, bars, beat):
    """Nearest slot of 1/4 or 1/3 beat. Returns (seconds, deviation, bar, slot key)."""
    i = np.searchsorted([b[0] for b in bars], t + 0.05) - 1
    if i < 0 or t > bars[i][1] + 0.05:
        return None
    a = bars[i][0]
    x = (t - a) / beat
    q4, q3 = round(x * 4) / 4, round(x * 3) / 3
    q = q4 if abs(x - q4) <= abs(x - q3) + 0.01 else q3
    return a + q * beat, abs(x - q) * beat, int(i), round(q, 4)


def passes(n, beat):
    return (n["end"] - n["t"] >= min(P["min_dur"], P["min_dur_beats"] * beat) and n["act"] >= P["min_activation"]
            and n["onset"] >= (P["onset_rearticulation"] if n["rearticulation"] else P["onset_entry"])
            and P["pitch"][0] <= n["pitch"] <= P["pitch"][1] and n["rms"] >= P["rms_rel"])


def lead_by_block(notes, bars):
    """Vocals lead a block when voiced notes fill enough of its bars."""
    nb = len(bars)
    voiced = np.zeros(nb)
    for n in notes["vocals"]:
        if not (P["pitch"][0] <= n["pitch"] <= P["pitch"][1] and n["act"] >= P["min_activation"]):
            continue
        i = np.searchsorted([b[0] for b in bars], n["t"]) - 1
        if 0 <= i < nb:
            voiced[i] += n["end"] - n["t"]
    share = voiced / np.array([z - a for a, z in bars])
    lead = []
    for k in range(0, nb, P["block_bars"]):
        lead += [("vocals" if share[k : k + P["block_bars"]].mean() >= P["vocal_bar_share"] else "other")] * len(share[k : k + P["block_bars"]])
    return lead


def snapped(ns, bars, beat, max_dev):
    out = []
    for n in ns:
        s = snap(n["t"], bars, beat)
        if s is None or s[1] > max_dev:
            continue
        out.append({**n, "st": s[0], "bar": s[2], "q": s[3]})
    return out


def dedupe(ns, gap):
    """Keep the strongest note when two are closer than gap seconds."""
    out = []
    for n in sorted(ns, key=lambda x: -(x["onset"] + x["act"])):
        if all(abs(n["st"] - m["st"]) >= gap for m in out):
            out.append(n)
    return sorted(out, key=lambda x: x["st"])


def repeat_supported(notes, bars, beat, lead, strong):
    """Weak attacks earn their place when a strong note with the same pitch sits
    at the same slot 4 or 8 bars away: repetition is the evidence."""
    have = {(n["bar"], n["q"], n["pitch"]) for n in strong}
    used = {(n["bar"], n["q"]) for n in strong}
    out = []
    for s in ("vocals", "other"):
        weak = [x for x in notes[s] if x["end"] - x["t"] >= min(P["min_dur"], P["min_dur_beats"] * beat) and x["act"] >= P["min_activation"] and x["onset"] >= P["weak_onset"]
                and P["pitch"][0] <= x["pitch"] <= P["pitch"][1] and x["rms"] >= P["rms_rel"]]
        for n in snapped(weak, bars, beat, P["max_snap_s"]):
            if lead[n["bar"]] != s or (n["bar"], n["q"]) in used:
                continue
            if any((n["bar"] + d, n["q"], n["pitch"]) in have for d in (-8, -4, 4, 8)):
                out.append(n)
    return out


def melody(notes, bars, beat):
    lead = lead_by_block(notes, bars)
    cand = []
    for s in ("vocals", "other"):
        for n in snapped([x for x in notes[s] if passes(x, beat)], bars, beat, P["max_snap_s"]):
            if lead[n["bar"]] == s:
                cand.append(n)
    if P["repeat_support"]:
        cand += repeat_supported(notes, bars, beat, lead, cand)
    cand = dedupe(cand, 0.24 * beat)
    keep = []
    for i, n in enumerate(cand):
        near = [m for m in cand[max(0, i - 1) : i + 2] if m is not n and abs(m["st"] - n["st"]) <= 2 * beat]
        if near and all(abs(m["pitch"] - n["pitch"]) >= P["jump"] for m in near) and n["onset"] < 0.85:
            continue
        keep.append(n)
    return keep, lead


def secondary(notes, bars, beat, mel, lead):
    cand = []
    for s in ("vocals", "other", "bass"):
        ok = [x for x in notes[s] if x["end"] - x["t"] >= P["sec_min_dur"] and x["onset"] >= P["sec_onset"] and x["act"] >= 0.5 and x["rms"] >= P["rms_rel"]]
        cand += [n for n in snapped(ok, bars, beat, P["max_snap_s"]) if lead[n["bar"]] != s]
    tm = np.array([m["st"] for m in mel]) if mel else np.array([1e9])
    cand = [n for n in cand if np.abs(tm - n["st"]).min() > 0.24 * beat]
    return dedupe(cand, P["sec_gap_beats"] * beat)


def beat_track(z, fps, bars, beat):
    """One 16-slot pattern per 4-bar block, from the strong drum onsets, repeated
    across the block's bars that actually have drums. Nothing is emitted in a
    bar without drums; a pattern too busy to be a pulse falls back to quarters."""
    e = z["env_drums"]
    pk, _ = find_peaks(e, distance=max(1, int(0.04 * fps)))
    t, v = pk / fps, e[pk]
    out = []
    for k in range(0, len(bars), 4):
        blk = bars[k : k + 4]
        q = (t >= blk[0][0] - 0.03) & (t < blk[-1][1] - 0.03)
        if q.sum() < 4:
            continue
        strong = v[q] >= 0.35 * np.percentile(v[q], 95)
        tb, hits = t[q][strong], np.zeros((len(blk), 16), bool)
        for x in tb:
            i = np.searchsorted([b[0] for b in blk], x + 0.03) - 1
            if i < 0:
                continue
            a, z_ = blk[i]
            s = (x - a) / (z_ - a) * 16
            if abs(s - round(s)) * (z_ - a) / 16 <= 0.03 and round(s) < 16:
                hits[i, int(round(s))] = True
        played = hits.sum(1) >= 2
        if played.sum() < 2:
            continue
        pat = hits[played].mean(0) >= P["beat_hit_share"]
        if pat.sum() == 0 or pat.sum() > P["beat_max_slots"]:
            pat = np.zeros(16, bool)
            pat[::4] = True
        for i, (a, z_) in enumerate(blk):
            if played[i]:
                out += [dict(st=a + s / 16 * (z_ - a), bar=k + i, q=s / 4, accent=bool(s % 8 == 0)) for s in np.flatnonzero(pat)]
    return out


def build(work, bpm, offset, bars=None):
    notes, z, fps, dur = load(work)
    b, bs = grid(bpm, offset, dur, bars)
    mel, lead = melody(notes, bs, b)
    sec = secondary(notes, bs, b, mel, lead)
    return dict(beat=b, bars=bs, duration=dur, melody=mel, secondary=sec, drums=beat_track(z, fps, bs, b), lead=lead, notes=notes)


# ---------------------------------------------------------------- evaluation

def hit(t, H, tol=0.025):
    if len(t) == 0:
        return np.zeros(0, bool)
    i = np.searchsorted(H, t).clip(1, len(H) - 1)
    return np.minimum(np.abs(t - H[i - 1]), np.abs(t - H[i])) <= tol


def prec(t, H, beat):
    """(precision, chance precision of the same notes moved by whole sixteenths)."""
    return float(hit(t, H).mean()), float(np.mean([hit(t + k * beat / 4, H).mean() for k in (-3, -2, -1, 1, 2, 3)]))


def corpus_rows():
    cal = json.loads((CAL / "calibration.json").read_text())["songs"]
    for s in corpus.songs():
        if s["id"] in cal:
            yield s, cal[s["id"]], CAL / "songs" / s["id"] / "work"


def evaluate(quiet=False):
    rows = []
    for s, c, work in corpus_rows():
        if c.get("other_bpms"):
            continue
        heads, d = chart_heads(s["chart"])
        H = np.unique(np.round([h["seconds"] for h in heads], 3))
        sign = c.get("offset_sign", 1)
        r = build(work, c["grid_bpm"], sign * float(d.get("offset", 0.0)))
        span = H[-1] - H[0]
        old = []
        for st in ("vocals", "other"):
            old += [n["st"] for n in snapped([x for x in r["notes"][st] if P["pitch"][0] - 7 <= x["pitch"]], r["bars"], r["beat"], 0.06) if r["lead"][n["bar"]] == st]
        row = dict(id=s["id"], heads=len(H) / span)
        for name, t in (("old", old), ("melody", [n["st"] for n in r["melody"]]), ("secondary", [n["st"] for n in r["secondary"]]), ("beat", [n["st"] for n in r["drums"]])):
            t = np.array(sorted(t))
            if len(t) < 8:
                continue
            p, c0 = prec(t, H, r["beat"])
            row[name] = (p, c0, len(t) / span)
        tm = np.array(sorted(n["st"] for n in r["melody"]))
        row["recall"] = float(hit(H, tm).mean()) if len(tm) else 0.0
        rows.append(row)
    print(f"{'track':10s} {'precision':>9s} {'chance':>7s} {'lift':>6s} {'notes/s':>8s} songs")
    summary = {}
    for name in ("old", "melody", "secondary", "beat"):
        v = np.array([r[name] for r in rows if name in r])
        summary[name] = v.mean(0).round(3).tolist()
        print(f"{name:10s} {v[:, 0].mean():9.3f} {v[:, 1].mean():7.3f} {(v[:, 0] - v[:, 1]).mean():+6.3f} {v[:, 2].mean():8.2f} {len(v)}")
    print(f"heads/s {np.mean([r['heads'] for r in rows]):.2f}  share of official heads on a melody note {np.mean([r['recall'] for r in rows]):.3f}")
    rows.sort(key=lambda r: r.get("melody", (0, 0, 0))[0] - r.get("melody", (0, 0, 0))[1])
    for r in rows[:5] + rows[-5:]:
        print(f"  {r['id'][:34]:34s} " + " ".join(f"{k} {r[k][0]:.2f}/{r[k][1]:.2f}" for k in ("melody", "beat") if k in r))
    return rows


# ---------------------------------------------------------------- viewer data

PILOTS = [
    ("Override", "charts/override/override-prr-2026-11-08", None),
    ("NightTheater", "charts/other/nighttheater/prr", None),
    ("Rrharil", "charts/other/rrharil-prr-2026-11-08", "Rrharil.TeamGrimoire"),
]
# corpus songs the official charts rate best and worst, so both can be heard
CORPUS_PICKS = ["Igallta.SeURa", "GOODRAGE.EBIMAYO", "ExoplanetaryMirage.かめりあ"]


def song_json(title, audio, r):
    return dict(
        title=title, audio=quote(os.path.relpath(audio, VIEW)), duration=round(r["duration"], 2), beat=round(r["beat"], 5),
        bars=[round(a, 3) for a, _ in r["bars"]],
        lead=[[round(r["bars"][i][0], 3), r["lead"][i][0]] for i in range(len(r["bars"])) if i == 0 or r["lead"][i] != r["lead"][i - 1]],
        melody=[[round(n["st"], 3), n["pitch"], round(n["end"] - n["t"], 3), n["stem"][0]] for n in r["melody"]],
        secondary=[[round(n["st"], 3), n["pitch"], round(n["end"] - n["t"], 3), n["stem"][0]] for n in r["secondary"]],
        drums=[[round(n["st"], 3), int(n["accent"])] for n in r["drums"]],
    )


def write_viewer():
    VIEW.mkdir(parents=True, exist_ok=True)
    songs = []
    for title, rel, cached in PILOTS:
        d = WS / rel
        rec = json.loads((d / "phrase-rhythm-record.json").read_text())
        gp = rec["layer_phase_alignment"].get("grid_phase", {})
        shift = gp.get("shift_ms", 0.0) / 1000 if gp.get("applied") else 0.0
        bars = [(b["seconds"][0] + shift, b["seconds"][1] + shift) for b in rec["MF4_bars"]]
        work = d / "work" if (d / "work/path-other.json").exists() else CAL / "songs" / cached / "work"
        r = build(work, rec["grid"]["bpm"], rec["grid"]["offset_seconds"] + shift, bars)
        songs.append(song_json(title, Path(rec["audio"]), r))
    by = {s["id"]: (s, c, w) for s, c, w in corpus_rows()}
    for sid in CORPUS_PICKS:
        s, c, work = by[sid]
        _, d = chart_heads(s["chart"])
        r = build(work, c["grid_bpm"], c.get("offset_sign", 1) * float(d.get("offset", 0.0)))
        songs.append(song_json(s["title"], s["music"], r))
    (VIEW / "data.js").write_text("window.TT = " + json.dumps(songs, ensure_ascii=False, separators=(",", ":")) + ";\n")
    for x in songs:
        print(x["title"], "melody", len(x["melody"]), "secondary", len(x["secondary"]), "drums", len(x["drums"]))


if __name__ == "__main__":
    {"eval": evaluate, "viewer": write_viewer}[sys.argv[1]]()
