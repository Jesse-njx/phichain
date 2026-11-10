"""Export pilot PRRs and calibration results to artifacts/prr-viewer/data.js.

The viewer (artifacts/prr-viewer/index.html) is a local page: it plays the
original audio from disk and synthesizes clicks for any layer or reading in
sync, so phrases can be checked by ear. Run with any python3.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
WS = HERE.parents[2]
OUT = WS / "artifacts/prr-viewer"
CAL = WS / "artifacts/phrase-rhythm-calibration"

PILOTS = [
    dict(key="override", title="Override (吉田夜世 feat. 重音テト)", prr=WS / "charts/override/override-prr-2026-11-08",
         note="SAR grid; beat zero corrected by the PRR phase check. Vocal-led."),
    dict(key="nighttheater", title="NightTheater (わかどり)", prr=WS / "charts/other/nighttheater/prr",
         note="SAR grid; instrumental with a short vocal middle. Snare/hat sit ~45 ms off the sixteenths: listen to whether the grid or the detection is wrong."),
    dict(key="rrharil", title="Rrharil (Team Grimoire)", prr=WS / "charts/other/rrharil-prr-2026-11-08",
         chart=WS / "main/research/overnight-study/corpus/chart/Rrharil.TeamGrimoire.0/IN.json",
         note="Grid from the official IN chart; the official note heads are a playable 'chart' layer."),
]

LAYERS = ["kick", "snare", "hat", "bass", "other", "vocals"]


def fracs(subs):
    fr = set()
    for d in subs:
        d = Fraction(d)
        k = 0
        while k * d < 1:
            fr.add(k * d)
            k += 1
    return [float(x) for x in sorted(fr)]


def export(p):
    rec = json.loads((p["prr"] / "phrase-rhythm-record.json").read_text())
    audio = Path(rec["audio"])
    rel = os.path.relpath(audio, OUT)
    bars = {b["bar"]: b for b in rec["MF4_bars"]}
    gp = rec["layer_phase_alignment"].get("grid_phase", {})
    phrases = []
    for pr in rec["phrases"]:
        if pr.get("free_rhythm"):
            continue
        ss = pr["MG6_slot_set"]
        ph = dict(
            id=pr["id"], section=pr["section"], function=pr["function"][:60], energy=pr["energy_tercile"],
            t=pr["seconds"], bars=[bars[b]["seconds"] for b in pr["bars"]], barNo=pr["bars"],
            fr=fracs(ss["subdivisions"]), subs="+".join(ss["subdivisions"]), spb=ss["slots_per_bar"],
            explained=ss["explained_share"], tolMs=ss["tolerance_ms"], lead=pr["lead"]["value"],
            leadStatus=pr["lead"]["status"], def_=pr.get("default_reading"),
            same=(pr.get("recurrence") or {}).get("same_as"),
            lines={l: dict(s=[r["string"] for r in pr["MR1_layer_lines"][l]["bars"]],
                           c=[r["cell"] for r in pr["MR1_layer_lines"][l]["bars"]],
                           p=[r.get("pitches", []) for r in pr["MR1_layer_lines"][l]["bars"]],
                           fill=[bool(r.get("fill")) for r in pr["MR1_layer_lines"][l]["bars"]])
                   for l in LAYERS},
            anchors=[[a["seconds"], "+".join(a["kinds"]), a["slot"]] for a in pr["MH3_anchors"]],
            readings={},
            sustains=[[s["layer"], s["slot"], s["pitch"], s["length_beats"], s["release"]] for s in pr["MR6_sustains"]],
            gestures=[[g["layer"], g["kind"], g["span"][0], g["span"][1], g["members"]] for g in pr["MR5_gestures"]],
            offGrid=len(pr["MR4_off_grid"]),
        )
        for r in pr["MH0_readings"]:
            ph["readings"][r["id"]] = dict(
                ev=[[e["seconds"], e["slot"], e["keep_through"], 1 if e.get("accents") else 0,
                     e.get("length_beats", 0) if e.get("articulation") == "sustain" else 0, e["layers"][0],
                     "+".join(e.get("anchor", []))] for e in r["events"]],
                d=r.get("density"), cr=(r.get("corpus_range") or {}),
                ladder=[x["hits_per_s"] for x in r.get("thinning_ladder", [])],
                rest=r.get("rest"),
            )
        phrases.append(ph)
    heads = []
    if p.get("chart"):
        import sys

        sys.path.insert(0, str(HERE))
        from prr import chart_heads

        hs, _ = chart_heads(p["chart"])
        heads = [[round(h["seconds"], 4), h["type"], round(h["hold_s"], 3)] for h in hs]
    return dict(
        key=p["key"], title=p["title"], note=p["note"], audio=quote(rel), bpm=rec["grid"]["bpm"],
        offset=rec["grid"]["offset_seconds"], grid=rec["grid_check"], stemLag=rec.get("stem_lag_ms"),
        clickOffsetMs=gp.get("shift_ms", 0.0) if gp.get("applied") else 0.0,
        phrases=phrases, heads=heads,
        latency={k: v.get("latency_ms") for k, v in rec["layer_phase_alignment"].items() if isinstance(v, dict) and "latency_ms" in v},
    )


def calibration():
    c = json.loads((CAL / "calibration.json").read_text())
    lat = json.loads((CAL / "layer-latency.json").read_text())["layers"]
    prior = json.loads((CAL / "corpus-prior.json").read_text())
    songs = []
    for sid, r in sorted(c["songs"].items(), key=lambda kv: -kv[1]["coverage"]):
        songs.append(dict(id=sid, title=r["title"], bpm=r["grid_bpm"], adh=r["adherence"], adhFine=r["adherence_fine"],
                          cov=r["coverage"], miss=r["slot_set_miss"], f1=r["reading_f1_level0"],
                          holds=r["holds_on_sustain_candidate"], drags=r["drag_runs_matching_gesture"],
                          charted={k: v["charted_share"] for k, v in r["charted_share"].items()}))
    return dict(songs=songs, latency=lat, prior=prior)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = dict(songs=[export(p) for p in PILOTS], calibration=calibration())
    (OUT / "data.js").write_text("window.PRR_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(OUT / "data.js", round((OUT / "data.js").stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
