"""Phrase Rhythm Record command line.

    python prr.py build --audio song.mp3 --sar song-analysis-record.json --out charts/<song>/prr
    python prr.py build --audio song.ogg --grid '{"bpm": 151, "offset_seconds": 0.137}' --out ...
    python prr.py apply-user --out charts/<song>/prr          # re-apply prr-user.json

Options: --auditions writes click-track files per reading per section;
--reference-chart adds an official-heads row to every sheet (calibration aid,
never an input to the readings); --prior points at corpus-prior.json.
Run with main/research/music-flow-study/.venv/bin/python.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np

import prr_audio
import prr_build
import prr_render

HERE = Path(__file__).resolve().parent
CALIBRATION = HERE.parents[2] / "artifacts/phrase-rhythm-calibration"
DEFAULT_PRIOR = CALIBRATION / "corpus-prior.json"
DEFAULT_LATENCY = CALIBRATION / "layer-latency.json"


def load_latency(path=None):
    p = Path(path) if path else DEFAULT_LATENCY
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text())
    return {k: v["median_ms"] / 1000.0 for k, v in d["layers"].items()}, str(p)


# ---------------------------------------------------------------- official charts

def chart_heads(path: Path, offset_sign: float = 1.0):
    """Official Phigros (formatVersion 3) note heads.

    Times are 1/32 beat of the note's own line BPM; audio seconds =
    units * 1.875 / bpm + offset_sign * offset.
    Returns a list of dicts with seconds, type (1 tap, 2 drag, 3 hold, 4 flick),
    hold_s, line bpm and units."""
    d = json.loads(Path(path).read_text())
    off = float(d.get("offset", 0.0))
    out = []
    for li, line in enumerate(d["judgeLineList"]):
        bpm = float(line["bpm"])
        for side in ("notesAbove", "notesBelow"):
            for n in line.get(side, []):
                out.append(
                    dict(
                        seconds=n["time"] * 1.875 / bpm + offset_sign * off,
                        type=int(n["type"]),
                        hold_s=float(n.get("holdTime", 0)) * 1.875 / bpm,
                        bpm=bpm,
                        units=n["time"],
                        line=li,
                    )
                )
    out.sort(key=lambda h: h["seconds"])
    return out, d


def reference_rows(record, heads):
    """Per phrase, per bar strings of official heads on the phrase's slot set."""
    rows = {}
    for pr in record["phrases"]:
        if pr.get("free_rhythm"):
            continue
        spb = pr["MG6_slot_set"]["slots_per_bar"]
        tol = pr["MG6_slot_set"]["tolerance_ms"] / 1000.0
        bars = [b for b in record["MF4_bars"] if b["bar"] in pr["bars"]]
        chars = [["."] * spb for _ in bars]
        for bi, b in enumerate(bars):
            a, z = b["seconds"]
            for h in heads:
                if a - tol <= h["seconds"] < z - tol:
                    pos = (h["seconds"] - a) / (z - a) * spb
                    i = int(round(pos))
                    if i < spb and abs(pos - i) * (z - a) / spb <= max(tol, 0.012):
                        chars[bi][i] = "H" if h["type"] == 3 else ("d" if h["type"] == 2 else ("f" if h["type"] == 4 else "x"))
                    else:
                        chars[bi][min(spb - 1, i)] = "?"
        rows[pr["id"]] = ["".join(c) for c in chars]
    return rows


# ---------------------------------------------------------------- user input (rules 17, 18)

def _events_from_pattern(pr, bi, pattern, record, status, evidence):
    spb = pr["MG6_slot_set"]["slots_per_bar"]
    bar = next(b for b in record["MF4_bars"] if b["bar"] == pr["bars"][bi])
    a, z = bar["seconds"]
    evs = []
    for i, ch in enumerate(pattern[:spb]):
        if ch in "Xx":
            t = a + (z - a) * i / spb
            evs.append(dict(slot=f"b{bi + 1}.{i}", seconds=round(t, 4), beat=None, layers=["user"], accents=["user"] if ch == "X" else [], articulation="strike", keep_through=4, status=status, evidence=evidence))
    return evs


def quantize_taps(pr, record, taps):
    """Offset-fit taps (±60 ms) to the phrase's slots; returns per-bar patterns."""
    spb = pr["MG6_slot_set"]["slots_per_bar"]
    bars = [b for b in record["MF4_bars"] if b["bar"] in pr["bars"]]
    slot_t = np.array([b["seconds"][0] + (b["seconds"][1] - b["seconds"][0]) * i / spb for b in bars for i in range(spb)])
    taps = np.asarray(taps, dtype=float)
    best = min(np.arange(-0.06, 0.0605, 0.002), key=lambda s: np.abs(slot_t[np.abs(slot_t[:, None] - (taps + s)[None, :]).argmin(axis=0)] - (taps + s)).sum())
    idx = np.abs(slot_t[:, None] - (taps + best)[None, :]).argmin(axis=0)
    chars = ["."] * len(slot_t)
    for k in idx:
        chars[k] = "x"
    return {str(bi + 1): "".join(chars[bi * spb : (bi + 1) * spb]) for bi in range(len(bars))}, float(best)


def apply_user(record, user):
    phrases = {p["id"]: p for p in record["phrases"]}
    log = []
    for r in user.get("rhythms", []):
        pr = phrases[r["phrase"]]
        if "taps_seconds" in r:
            bars, shift = quantize_taps(pr, record, r["taps_seconds"])
            note = f"taps offset-fitted by {shift * 1000:+.0f} ms"
        else:
            bars, note = r["bars"], "written"
        events = []
        for b, pat in sorted(bars.items(), key=lambda kv: int(kv[0])):
            events += _events_from_pattern(pr, int(b) - 1, pat, record, "user-confirmed", [f"user:{r['phrase']}"])
        pr["MH0_readings"] = [x for x in pr["MH0_readings"] if x["id"] != "R-user"]
        pr["MH0_readings"].append(dict(id="R-user", phrase=pr["id"], follows=["user"], events=events, status="user-confirmed", evidence=[note], user_bars=bars, note=r.get("note")))
        pr["chosen_reading"] = prr_build.claim("R-user", source="user", status="user-confirmed", evidence=[note])
        log.append(f"R-user {pr['id']} ({note})")
        # propagate (XS5): bars elsewhere with the same measured lead cell
        lead = pr["lead"]["value"][0]
        for b, pat in bars.items():
            bi = int(b) - 1
            cell = pr["MR1_layer_lines"][lead]["bars"][bi]["cell"]
            if cell.endswith("-"):
                continue
            for other in record["phrases"]:
                if other is pr or other.get("free_rhythm") or other["MG6_slot_set"]["slots_per_bar"] != pr["MG6_slot_set"]["slots_per_bar"]:
                    continue
                cur = next((x for x in other["MH0_readings"] if x["id"] == "R-user"), None)
                if cur and cur["status"] == "user-confirmed":
                    continue
                olead = other["lead"]["value"][0]
                for obi, row in enumerate(other["MR1_layer_lines"][olead]["bars"]):
                    if row["cell"] != cell:
                        continue
                    if cur is None:
                        cur = dict(id="R-user", phrase=other["id"], follows=["user"], events=[], status="propagated", evidence=[], user_bars={})
                        other["MH0_readings"].append(cur)
                    cur["events"] = [e for e in cur["events"] if not e["slot"].startswith(f"b{obi + 1}.")]
                    cur["events"] += _events_from_pattern(other, obi, pat, record, "propagated", [f"user:{pr['id']} bar {b} via {lead} cell {cell}"])
                    cur["events"].sort(key=lambda e: e["seconds"])
                    cur["user_bars"][str(obi + 1)] = pat
                    cur["evidence"].append(f"{pr['id']} bar {b} cell {cell}")
                    log.append(f"  propagated to {other['id']} bar {obi + 1} (cell {cell})")
    for c in user.get("choices", []):
        pr = phrases[c["phrase"]]
        pr["chosen_reading"] = prr_build.claim(c["reading"], source="user", status="user-confirmed", evidence=[c.get("note", "")])
        log.append(f"choice {pr['id']} = {c['reading']}")
        if c.get("apply_to_group"):
            for other in record["phrases"]:
                rec = other.get("recurrence") or {}
                src = (pr.get("recurrence") or {}).get("same_as", pr["id"])
                if other is not pr and (rec.get("same_as") == src or other["id"] == src):
                    if (other.get("chosen_reading") or {}).get("status") != "user-confirmed":
                        other["chosen_reading"] = prr_build.claim(c["reading"], source="user", status="propagated", evidence=[f"choice on {pr['id']} via recurrence group"])
                        log.append(f"  propagated choice to {other['id']}")
    record["MH5_user_log"] = log
    return record


# ---------------------------------------------------------------- driver

def build(args):
    audio = Path(args.audio).resolve()
    out = Path(args.out).resolve()
    work = Path(args.work).resolve() if args.work else out / "work"
    ev = prr_audio.extract(audio, work)
    if args.sar:
        sar = json.loads(Path(args.sar).read_text())
        grid = prr_build.grid_from_sar(sar, ev["duration"], str(args.sar))
        song = sar.get("song", audio.stem)
    else:
        cfg = json.loads(args.grid) if args.grid.strip().startswith("{") else json.loads(Path(args.grid).read_text())
        grid = prr_build.grid_from_config(cfg, ev["duration"])
        song = cfg.get("song", audio.stem)
    prior_path = Path(args.prior) if args.prior else DEFAULT_PRIOR
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else None
    latency, lat_src = load_latency(args.latency)
    b = prr_build.Builder(ev, grid, prior, phrase_bars=args.phrase_bars, latency=latency, latency_source=lat_src, fit_phase={"auto": "auto", "on": True, "off": False}[args.fit_phase])
    record = b.build(song, ev["audio_sha256"], str(args.sar or ""))
    record["assembled"] = dt.date.today().isoformat()
    record["corpus_prior"] = str(prior_path) if prior else None
    user_path = out / "prr-user.json"
    if user_path.exists():
        apply_user(record, json.loads(user_path.read_text()))
    refs = None
    if args.reference_chart:
        heads, _ = chart_heads(Path(args.reference_chart), args.offset_sign)
        refs = reference_rows(record, heads)
        record["reference_chart"] = str(args.reference_chart)
    out.mkdir(parents=True, exist_ok=True)
    (out / "phrase-rhythm-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1))
    prr_render.write_sheets(record, out / "sheets", refs)
    if args.auditions:
        prr_render.write_auditions(record, audio, out / "auditions", args.sections)
    n = len(record["phrases"])
    print(f"PRR: {n} phrases, {len(record['MF4_bars'])} bars -> {out / 'phrase-rhythm-record.json'}")
    return record


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--audio", required=True)
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--sar")
    g.add_argument("--grid", help="JSON string or path: bpm, offset_seconds, meter, sections")
    b.add_argument("--out", required=True)
    b.add_argument("--work")
    b.add_argument("--prior")
    b.add_argument("--phrase-bars", type=int, default=None)
    b.add_argument("--auditions", action="store_true")
    b.add_argument("--sections", nargs="*")
    b.add_argument("--reference-chart")
    b.add_argument("--offset-sign", type=float, default=1.0)
    b.add_argument("--latency", help="layer-latency.json (default: calibration output)")
    b.add_argument("--fit-phase", choices=["auto", "on", "off"], default="auto", help="apply the measured grid phase error (auto: when the drum layers agree)")
    u = sub.add_parser("apply-user")
    u.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "build":
        build(args)
    else:
        out = Path(args.out)
        rec = json.loads((out / "phrase-rhythm-record.json").read_text())
        apply_user(rec, json.loads((out / "prr-user.json").read_text()))
        (out / "phrase-rhythm-record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        prr_render.write_sheets(rec, out / "sheets")
        print("\n".join(rec["MH5_user_log"]))


if __name__ == "__main__":
    main()
