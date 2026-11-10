"""Rhythm sheets (XR3) and auditions (XR4) for a PRR."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from prr_build import LAYERS

ROW_LAYERS = ["kick", "snare", "hat", "vocals", "other", "bass"]


def reading_strings(pr, reading, level=0):
    """Per-bar strings for a reading at a thinning level."""
    spb = pr["MG6_slot_set"]["slots_per_bar"]
    nb = len(pr["bars"])
    chars = [["."] * spb for _ in range(nb)]
    for e in reading["events"]:
        if e["keep_through"] < level:
            continue
        b, i = e["slot"][1:].split(".")
        chars[int(b) - 1][int(i)] = "X" if e.get("accents") else "x"
    return ["".join(c) for c in chars]


def phrase_sheet(pr, reference=None) -> str:
    if pr.get("free_rhythm"):
        lines = [f"{pr['id']}  FREE RHYTHM  {pr['seconds'][0]:.2f}-{pr['seconds'][1]:.2f} s  section {pr['section']}"]
        for l, evs in pr["raw_events"].items():
            ts = [e if isinstance(e, float) else e["seconds"] for e in evs]
            lines.append(f"  {l:7s} {len(ts)} events: " + " ".join(f"{t:.2f}" for t in ts[:24]) + (" ..." if len(ts) > 24 else ""))
        return "\n".join(lines) + "\n"
    ss = pr["MG6_slot_set"]
    head = (
        f"{pr['id']}  section {pr['section']} ({pr['function'][:40]})  bars {pr['bars'][0]}-{pr['bars'][-1]}  "
        f"beats {pr['beats'][0]:g}-{pr['beats'][1]:g}  {pr['seconds'][0]:.2f}-{pr['seconds'][1]:.2f} s  energy {pr['energy_tercile']}\n"
        f"  slots {'+'.join(ss['subdivisions'])} beat ({ss['slots_per_bar']}/bar, tol {ss['tolerance_ms']} ms), explained {ss['explained_share']:.0%}"
        + (f"  FLAG: {ss['flag']}" if ss["flag"] else "")
        + (f"  swing {pr['MG7_swing'].get('swing_ratio')}" if pr["MG7_swing"].get("consistent") else "")
        + f"\n  lead {'/'.join(pr['lead']['value'])} ({pr['lead']['status']})  default {pr.get('default_reading')}"
        + (f"  recurrence: same as {pr['recurrence']['same_as']} ({pr['recurrence']['group']})" if pr.get("recurrence") else "")
        + "\n"
    )
    out = [head]
    anchors_by_bar = {}
    for a in pr["MH3_anchors"]:
        anchors_by_bar.setdefault(int(a["slot"][1:].split(".")[0]), []).append(f"{a['slot']} {'+'.join(a['kinds'])}")
    readings = pr["MH0_readings"]
    for bi, bar in enumerate(pr["bars"]):
        cells = " ".join(pr["MR1_layer_lines"][l]["bars"][bi]["cell"] for l in ROW_LAYERS)
        out.append(f" bar {bi + 1} (#{bar})  cells {cells}" + (f"   anchors: {', '.join(anchors_by_bar[bi + 1])}" if bi + 1 in anchors_by_bar else ""))
        for l in ROW_LAYERS:
            row = pr["MR1_layer_lines"][l]["bars"][bi]
            extra = ""
            if row.get("pitches"):
                extra = "  " + " ".join(row["pitches"][:12])
            if row.get("present") is False:
                extra += "  (absent)"
            if row.get("fill"):
                extra += "  FILL"
            if row.get("status") == "contradicted":
                extra += "  OFF-GRID>3"
            out.append(f"   {l:7s} {row['string']}  {row['cell']:6s}{extra}")
        if reference is not None:
            out.append(f"   {'chart':7s} {reference[bi]}  (official heads)")
        for r in readings:
            out.append(f"   {r['id']:13s} {reading_strings(pr, r)[bi]}")
    out.append("")
    for r in readings:
        d = r["density"]
        cr = r.get("corpus_range")
        ladder = " ".join(f"T{x['level']}:{x['hits_per_s']}" for x in r["thinning_ladder"])
        out.append(
            f"  {r['id']:13s} {d['hits']:3d} hits {d['hits_per_s_mean']:5.2f}/s peak {d['hits_per_s_peak']:g}  sustains {d['sustains']}  chords {d['chord_fraction']:.0%}"
            + (f"  corpus {cr['key']} {cr['hits_per_s_p25_p75'][0]}-{cr['hits_per_s_p25_p75'][1]}" + (f" {cr['flag']}" if cr["flag"] else "") if cr else "")
            + f"   thinning {ladder}"
            + (f"   REST: {r['rest']}" if r.get("rest") else "")
        )
    if pr["MR6_sustains"]:
        out.append("  sustains: " + ", ".join(f"{s['layer']} {s['slot']} {s['pitch']} {s['length_beats']:g}b ({s['release']})" for s in pr["MR6_sustains"][:12]))
    if pr["MR5_gestures"]:
        out.append("  gestures: " + ", ".join(f"{g['layer']} {g['kind']} {g['span'][0]}..{g['span'][1]} x{g['members']}" for g in pr["MR5_gestures"][:10]))
    if pr["MR4_off_grid"]:
        out.append(f"  off-grid onsets: {len(pr['MR4_off_grid'])}  unexplained mix onsets: {len(pr['unexplained_mix_onsets'])}")
    return "\n".join(out) + "\n"


def write_sheets(record, out_dir: Path, references=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = [f"# Rhythm sheets: {record['song']}\n\nGrid {record['grid']['bpm']} BPM, beat 0 = {record['grid']['offset_seconds']} s. "
             "Rows: layer lines (X accent, x attack, ~ sustain, . rest), then readings at thinning level 0. "
             "Cells: kick K, snare S, hat H, vocals V, other O, bass B; `-` is a rest bar.\n"]
    for pr in record["phrases"]:
        ref = references.get(pr["id"]) if references else None
        txt = phrase_sheet(pr, ref)
        (out_dir / f"{pr['id']}.txt").write_text(txt)
        parts.append("```\n" + txt + "```\n")
    (out_dir / "sheets.md").write_text("\n".join(parts))


# ---------------------------------------------------------------- auditions

CLICK = {
    "vocals": (1568.0, 0.035, "tone"),
    "other": (1175.0, 0.035, "tone"),
    "bass": (196.0, 0.06, "tone"),
    "kick": (90.0, 0.06, "thump"),
    "snare": (0.0, 0.05, "noise"),
    "hat": (0.0, 0.02, "hiss"),
}


def click(kind, sr, accent=True, length_s=None):
    f, d, typ = CLICK[kind]
    n = int(sr * d)
    t = np.arange(n) / sr
    envl = np.exp(-t / (d / 4))
    rng = np.random.default_rng(1)
    if typ == "tone":
        y = np.sin(2 * np.pi * f * t) * envl
    elif typ == "thump":
        y = np.sin(2 * np.pi * (f + 80 * np.exp(-t * 60)) * t) * envl
    elif typ == "noise":
        y = rng.standard_normal(n) * envl * 0.6
    else:
        y = np.diff(rng.standard_normal(n + 1)) * envl * 0.3
    y = y * (1.0 if accent else 0.55)
    if length_s and typ == "tone" and length_s > d:
        m = int(sr * length_s)
        tt = np.arange(m) / sr
        sus = 0.18 * np.sin(2 * np.pi * f * tt) * np.minimum(1, (m - np.arange(m)) / (0.01 * sr))
        sus[:n] += y
        y = sus
    return y.astype(np.float32)


def write_auditions(record, audio_path: Path, out_dir: Path, sections=None):
    """One file per reading per section: clicks (one timbre per layer, the
    reading's first followed layer for a multi-layer event) over the original
    audio at -6 dB."""
    import librosa

    out_dir.mkdir(parents=True, exist_ok=True)
    sr = 22050
    y, _ = librosa.load(str(audio_path), sr=sr, mono=True)
    by_sec = {}
    for pr in record["phrases"]:
        if pr.get("free_rhythm"):
            continue
        by_sec.setdefault(pr["section"], []).append(pr)
    # long sections (a grid-only song is one section) are cut into 8-phrase parts
    parts = {}
    for sid, prs in by_sec.items():
        if len(prs) <= 8:
            parts[sid] = prs
        else:
            for i in range(0, len(prs), 8):
                parts[f"{sid}-{prs[i]['id']}"] = prs[i : i + 8]
    by_sec = parts
    ext = "ogg" if "OGG" in sf.available_formats() else "wav"
    written = []
    for sid, prs in by_sec.items():
        if sections and sid.split("-P")[0] not in sections:
            continue
        a, z = prs[0]["seconds"][0], prs[-1]["seconds"][1]
        a0 = max(0.0, a - 1.0)
        seg = y[int(a0 * sr) : int(z * sr) + sr // 2].copy() * 0.5
        rids = [r["id"] for r in prs[0]["MH0_readings"]]
        for rid in rids:
            mixc = np.zeros_like(seg)
            for pr in prs:
                r = next((x for x in pr["MH0_readings"] if x["id"] == rid), None)
                if not r:
                    continue
                for e in r["events"]:
                    layer = e["layers"][0]
                    length = None
                    if e["articulation"] == "sustain":
                        length = e["length_beats"] * 60.0 / record["grid"]["bpm"]
                    c = click(layer, sr, bool(e.get("accents")), length)
                    i = int((e["seconds"] - a0) * sr)
                    if 0 <= i < len(mixc):
                        j = min(len(mixc), i + len(c))
                        mixc[i:j] += c[: j - i] * 0.5
            out = np.clip(seg + mixc, -1, 1)
            name = out_dir / f"{sid}__{rid.replace('[', '_').replace(']', '')}.{ext}"
            sf.write(name, out, sr)
            written.append(str(name))
    return written
