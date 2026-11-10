"""Calibrate the PRR against official IN charts (research/phrase-rhythm-framework/DESIGN.md section 2, steps 1-5).

Pass 1 measures detector latency per layer against official note heads
(layer-latency.json). Pass 2 builds a PRR per song on the chart's own grid with
those latencies and measures:

1. grid adherence of official heads (1/4 and 1/3 beat slots, +-5 ms);
2. layer coverage: heads that coincide with some MR1 attack, and the share of
   each layer's attacks that are charted;
3. best reading per phrase (F1 of reading slots against head slots, over the
   thinning ladder), tabulated by phrase energy tercile, plus the head-density
   corpus prior (corpus-prior.json);
4. Holds against MR6 sustain candidates;
5. Drag runs against MR5 gestures.

Outputs go to artifacts/phrase-rhythm-calibration/. Run with the
music-flow-study venv after corpus.py has extracted the evidence.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent-tools/phrase-rhythm"))

import corpus
import prr_audio
import prr_build
from prr import chart_heads

OUT = corpus.OUT
LAYERS = prr_build.LAYERS


def norm_bpm(bpm):
    d = 1
    while bpm / d > 300:
        d *= 2
    return bpm / d, d


def load(song):
    work = OUT / "songs" / song["id"] / "work"
    if not (work / "evidence.json").exists():
        return None
    return prr_audio.extract(song["music"], work)


def chart_grid(song, ev):
    heads, d = chart_heads(song["chart"], 1.0)
    bpms = Counter(h["bpm"] for h in heads)
    bpm0 = bpms.most_common(1)[0][0]
    off = float(d.get("offset", 0.0))
    return heads, bpm0, off, bpms


def unique_times(heads, eps=0.004):
    out = []
    for h in heads:
        if not out or h["seconds"] - out[-1]["seconds"] > eps:
            out.append(h)
    return out


# ---------------------------------------------------------------- pass 1: latency

def layer_deviation(builder, heads, layer, window=0.05):
    """Signed deviation (s) of the nearest layer onset to each head."""
    if layer in prr_build.DRUMS:
        t, v, pr = builder.drum_peaks[layer]
        # strong peaks only: >= 20% of the local 2 s maximum
        keep = np.zeros(len(t), bool)
        for i in range(len(t)):
            lo, hi = np.searchsorted(t, t[i] - 1), np.searchsorted(t, t[i] + 1)
            keep[i] = v[i] >= 0.2 * v[lo:hi].max()
        t = t[keep]
    else:
        t = np.array(sorted(n["start"] for n in builder.notes[layer]))
    if len(t) == 0:
        return []
    out = []
    for h in heads:
        i = np.searchsorted(t, h["seconds"])
        c = [t[j] - h["seconds"] for j in (i - 1, i) if 0 <= j < len(t)]
        d = min(c, key=abs)
        if abs(d) <= window:
            out.append(d)
    return out


def pass1(songs):
    per = {}
    for s in songs:
        ev = load(s)
        if ev is None:
            continue
        heads, bpm0, off, _ = chart_grid(s, ev)
        bpm, _ = norm_bpm(bpm0)
        best = None
        for sign in ([1.0, -1.0] if off else [1.0]):
            hs = unique_times([dict(h, seconds=h["seconds"] - off + sign * off) for h in heads])
            b = prr_build.Builder(ev, prr_build.grid_from_config({"bpm": bpm, "offset_seconds": sign * off}, ev["duration"]))
            devs = {l: layer_deviation(b, hs, l) for l in LAYERS}
            score = len(devs["kick"]) + len(devs["snare"])
            if best is None or score > best[0]:
                best = (score, sign, devs)
        _, sign, devs = best
        per[s["id"]] = dict(offset_sign=sign, offset=off, layers={l: dict(median_ms=round(float(np.median(d)) * 1000, 1), n=len(d)) for l, d in devs.items() if len(d) >= 20})
        print("latency", s["id"], {l: v["median_ms"] for l, v in per[s["id"]]["layers"].items()}, flush=True)
    agg = {}
    for l in LAYERS:
        vals = [p["layers"][l]["median_ms"] for p in per.values() if l in p["layers"]]
        if vals:
            agg[l] = dict(median_ms=round(float(np.median(vals)), 1), iqr_ms=[round(float(np.percentile(vals, 25)), 1), round(float(np.percentile(vals, 75)), 1)], songs=len(vals))
    lat = dict(
        method="median over songs of the per-song median signed deviation (layer onset - official head) for onsets within 50 ms of a head; positive = detector late",
        layers=agg,
        per_song=per,
    )
    (OUT / "layer-latency.json").write_text(json.dumps(lat, indent=1, ensure_ascii=False))
    return lat


# ---------------------------------------------------------------- pass 2: metrics

def slot_table(record):
    """phrase id -> (slot times, slot names, tol seconds)."""
    bars = {b["bar"]: b for b in record["MF4_bars"]}
    out = {}
    for pr in record["phrases"]:
        if pr.get("free_rhythm"):
            continue
        subs = [Fraction(x) for x in pr["MG6_slot_set"]["subdivisions"]]
        fr = prr_build.slot_fracs(subs)
        times, names = [], []
        for bi, bn in enumerate(pr["bars"]):
            a, z = bars[bn]["seconds"]
            bpb = round((z - a) / (60.0 / record["grid"]["bpm"]))
            beat = (z - a) / bpb
            i = 0
            for k in range(bpb):
                for f in fr:
                    times.append(a + (k + float(f)) * beat)
                    names.append((bi, i))
                    i += 1
        out[pr["id"]] = (np.array(times), names, pr["MG6_slot_set"]["tolerance_ms"] / 1000.0, pr)
    return out


def locate(table, t):
    for pid, (times, names, tol, pr) in table.items():
        if times[0] - tol <= t < pr["seconds"][1] - tol:
            k = int(np.argmin(np.abs(times - t)))
            return pid, k, abs(times[k] - t) <= max(tol, 0.012)
    return None, None, False


def adherence(heads, fine=False):
    ok = 0
    fails = []
    q = (8, 6) if fine else (4, 3)
    for h in heads:
        beat_s = 60.0 / h["bpm"]
        b = h["units"] / 32.0
        d = min(abs(b - round(b * q[0]) / q[0]), abs(b - round(b * q[1]) / q[1])) * beat_s
        if d <= 0.005:
            ok += 1
        else:
            fails.append(dict(seconds=round(h["seconds"], 4), units=h["units"], bpm=h["bpm"], off_ms=round(d * 1000, 1)))
    return ok / max(1, len(heads)), fails


def f1(E, H):
    if not E and not H:
        return 1.0
    return 2 * len(E & H) / (len(E) + len(H))


def drag_runs(heads, bpm):
    drags = [h for h in heads if h["type"] == 2]
    runs, cur = [], []
    for h in drags:
        if cur and h["seconds"] - cur[-1]["seconds"] <= 15.0 / bpm + 0.01:
            cur.append(h)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = [h]
    if len(cur) >= 3:
        runs.append(cur)
    return [(r[0]["seconds"], r[-1]["seconds"], len(r)) for r in runs]


def pass2(songs, lat):
    latency = {k: v["median_ms"] / 1000.0 for k, v in lat["layers"].items()}
    results = {}
    best_rows = []
    density_rows = defaultdict(list)
    for s in songs:
        ev = load(s)
        if ev is None:
            continue
        heads, bpm0, off, bpms = chart_grid(s, ev)
        sign = lat["per_song"].get(s["id"], {}).get("offset_sign", 1.0)
        heads = [dict(h, seconds=h["seconds"] - off + sign * off) for h in heads]
        heads = [h for h in heads if h["seconds"] < ev["duration"]]
        bpm, div = norm_bpm(bpm0)
        grid = prr_build.grid_from_config({"bpm": bpm, "offset_seconds": sign * off}, ev["duration"])
        b = prr_build.Builder(ev, grid, None, latency=latency, latency_source="layer-latency.json")
        rec = b.build(s["id"], ev["audio_sha256"])
        table = slot_table(rec)
        uh = unique_times(heads)
        # 1. adherence
        adh, adh_fail = adherence(heads)
        adh_fine, _ = adherence(heads, fine=True)
        # 2. coverage
        covered, slot_miss, no_layer = 0, 0, []
        head_slots = defaultdict(set)
        head_kind = {}
        for h in uh:
            pid, k, ok = locate(table, h["seconds"])
            if pid is None:
                continue
            if not ok:
                slot_miss += 1
                no_layer.append(dict(seconds=round(h["seconds"], 3), reason="not on phrase slot set", phrase=pid))
                continue
            times, names, tol, pr = table[pid]
            bi, i = names[k]
            slot = f"b{bi + 1}.{i}"
            head_slots[pid].add(slot)
            head_kind[(pid, slot)] = h["type"]
            hit = [l for l in LAYERS if pr["MR1_layer_lines"][l]["bars"][bi]["string"][i] in "Xx"]
            if hit:
                covered += 1
            else:
                no_layer.append(dict(seconds=round(h["seconds"], 3), reason="no layer attack", phrase=pid, slot=slot))
        located = sum(len(v) for v in head_slots.values()) + slot_miss
        charted = {}
        for l in LAYERS:
            att = ch = 0
            for pid, (times, names, tol, pr) in table.items():
                for bi, row in enumerate(pr["MR1_layer_lines"][l]["bars"]):
                    for i, c in enumerate(row["string"]):
                        if c in "Xx":
                            att += 1
                            ch += f"b{bi + 1}.{i}" in head_slots[pid]
            charted[l] = dict(attacks=att, charted_share=round(ch / att, 3) if att else None)
        # 3. best reading per phrase
        reading_f1 = defaultdict(list)
        for pid, (times, names, tol, pr) in table.items():
            H = head_slots[pid]
            dur = pr["seconds"][1] - pr["seconds"][0]
            density_rows[pr["energy_tercile"]].append(len(H) / dur)
            if not H:
                continue
            cands = []
            for r in pr["MH0_readings"]:
                for lvl in range(5):
                    E = {e["slot"] for e in r["events"] if e["keep_through"] >= lvl}
                    sc = f1(E, H)
                    cands.append((sc, -len(E), r["id"].split("[")[0], lvl))
                    if lvl == 0:
                        reading_f1[r["id"].split("[")[0]].append(sc)
            sc, _, rid, lvl = max(cands)
            best_rows.append(dict(song=s["id"], phrase=pid, tercile=pr["energy_tercile"], reading=rid, level=lvl, f1=round(sc, 3), heads=len(H), heads_per_s=round(len(H) / dur, 2)))
        # 4. holds vs sustains
        holds = [h for h in uh if h["type"] == 3]
        on_cand, on_attack, ratios = 0, 0, []
        for h in holds:
            pid, k, ok = locate(table, h["seconds"])
            if not ok:
                continue
            times, names, tol, pr = table[pid]
            bi, i = names[k]
            slot = f"b{bi + 1}.{i}"
            cands = [x for x in pr["MR6_sustains"] if x["slot"] == slot]
            if cands:
                on_cand += 1
                ratios.append((h["hold_s"]) / max(1e-3, max(c["length_s"] for c in cands)))
            if any(pr["MR1_layer_lines"][l]["bars"][bi]["string"][i] in "Xx" for l in prr_build.PITCHED):
                on_attack += 1
        n_sus = sum(len(pr["MR6_sustains"]) for _, (_, _, _, pr) in table.items())
        # 5. drag runs vs gestures
        runs = drag_runs(heads, bpm0)
        gest = [g for _, (_, _, _, pr) in table.items() for g in pr["MR5_gestures"]]
        matched = 0
        for a, z, n in runs:
            for g in gest:
                ga, gz = g["seconds"]
                inter = min(z, gz) - max(a, ga)
                union = max(z, gz) - min(a, ga)
                if inter > 0 and inter / max(union, 1e-3) >= 0.5:
                    matched += 1
                    break
        pg = [g for g in gest if g["layer"] in ("vocals", "other")]
        pg_charted = 0
        for g in pg:
            pid = next(p for p, v in table.items() if v[3]["seconds"][0] - 0.05 <= g["seconds"][0] < v[3]["seconds"][1])
            members_heads = sum(1 for h in uh if g["seconds"][0] - 0.02 <= h["seconds"] <= g["seconds"][1] + 0.02)
            pg_charted += members_heads >= 0.8 * g["members"]
        results[s["id"]] = dict(
            title=s["title"],
            constant=s["constant"],
            chart_bpm=bpm0,
            grid_bpm=bpm,
            bpm_divisor=div,
            other_bpms={str(k): v for k, v in bpms.items() if k != bpm0},
            offset_sign=sign,
            heads=len(heads),
            unique_head_times=len(uh),
            grid_phase_ms=rec["grid_check"].get("grid_phase_ms"),
            adherence=round(adh, 4),
            adherence_fine=round(adh_fine, 4),
            coverage=round(covered / max(1, located), 4),
            slot_set_miss=round(slot_miss / max(1, located), 4),
            slot_sets=dict(Counter("+".join(p["MG6_slot_set"]["subdivisions"]) for p in rec["phrases"] if not p.get("free_rhythm"))),
            charted_share=charted,
            reading_f1_level0={k: round(float(np.mean(v)), 3) for k, v in reading_f1.items()},
            holds=len(holds),
            holds_on_sustain_candidate=round(on_cand / len(holds), 3) if holds else None,
            holds_on_pitched_attack=round(on_attack / len(holds), 3) if holds else None,
            hold_to_candidate_length_median=round(float(np.median(ratios)), 3) if ratios else None,
            sustain_candidates=n_sus,
            drag_runs=len(runs),
            drag_runs_matching_gesture=round(matched / len(runs), 3) if runs else None,
            pitched_gestures=len(pg),
            pitched_gestures_charted=round(pg_charted / len(pg), 3) if pg else None,
        )
        fail_dir = OUT / "failures"
        fail_dir.mkdir(parents=True, exist_ok=True)
        (fail_dir / f"{s['id']}.json").write_text(json.dumps(dict(no_layer_attack=no_layer, adherence_failures=adh_fail[:200]), indent=1, ensure_ascii=False))
        print("metrics", s["id"], results[s["id"]]["adherence"], results[s["id"]]["coverage"], results[s["id"]]["reading_f1_level0"], flush=True)
    prior = dict(
        method="unique official IN head times per second per phrase (4 bars on the chart grid), by phrase energy tercile within the song",
        head_density_by_energy={
            t: dict(p10=round(float(np.percentile(v, 10)), 2), p25=round(float(np.percentile(v, 25)), 2), p50=round(float(np.percentile(v, 50)), 2), p75=round(float(np.percentile(v, 75)), 2), p90=round(float(np.percentile(v, 90)), 2), phrases=len(v))
            for t, v in density_rows.items()
        },
    )
    by_terc = defaultdict(Counter)
    lvl_terc = defaultdict(Counter)
    f1_terc = defaultdict(list)
    for r in best_rows:
        by_terc[r["tercile"]][r["reading"]] += 1
        lvl_terc[r["tercile"]][r["level"]] += 1
        f1_terc[r["tercile"]].append(r["f1"])
    prior["best_reading_by_energy"] = {t: dict(readings=dict(by_terc[t]), levels={str(k): v for k, v in sorted(lvl_terc[t].items())}, mean_best_f1=round(float(np.mean(f1_terc[t])), 3)) for t in by_terc}
    (OUT / "corpus-prior.json").write_text(json.dumps(prior, indent=1))
    (OUT / "calibration.json").write_text(json.dumps(dict(songs=results, best_reading_rows=best_rows), indent=1, ensure_ascii=False))
    write_table(results, prior, lat)
    return results


def write_table(results, prior, lat):
    rows = sorted(results.items(), key=lambda kv: kv[0].lower())
    L = ["# PRR calibration against official IN charts", ""]
    L.append(f"{len(rows)} songs. Grid = the chart's own BPM (halved above 300) and offset. Generated by `main/research-tools/phrase-rhythm/calibrate.py`.\n")
    L.append("## Layer latency (pass 1)\n")
    L.append("| Layer | Median ms | IQR across songs | Songs |\n| --- | --- | --- | --- |")
    for l, v in lat["layers"].items():
        L.append(f"| {l} | {v['median_ms']:+.1f} | {v['iqr_ms'][0]:+.1f} .. {v['iqr_ms'][1]:+.1f} | {v['songs']} |")
    keys = ["R-lead", "R-lead+kick", "R-drums", "R-dense"]
    L.append("\n## Per song\n")
    L.append("| Song | BPM | Adh. 1/4+1/3 / 1/8+1/6 | Cover | Off-set | " + " | ".join(f"F1 {k[2:]}" for k in keys) + " | Holds on cand. | Drag runs ~ gesture | Grid phase ms |")
    L.append("| --- " * (8 + len(keys)) + "|")
    agg = defaultdict(list)
    for sid, r in rows:
        f = r["reading_f1_level0"]
        cells = [sid[:32], f"{r['grid_bpm']:g}" + ("" if r["bpm_divisor"] == 1 else f" (/{r['bpm_divisor']})"), f"{r['adherence']:.1%} / {r['adherence_fine']:.1%}", f"{r['coverage']:.1%}", f"{r['slot_set_miss']:.1%}"]
        cells += [f"{f.get(k, float('nan')):.2f}" for k in keys]
        cells += [f"{r['holds_on_sustain_candidate']:.0%}" if r["holds_on_sustain_candidate"] is not None else "-", f"{r['drag_runs_matching_gesture']:.0%} of {r['drag_runs']}" if r["drag_runs"] else "-", f"{r['grid_phase_ms']}"]
        L.append("| " + " | ".join(cells) + " |")
        for k in ("adherence", "adherence_fine", "coverage", "slot_set_miss"):
            agg[k].append(r[k])
        for k in keys:
            if k in f:
                agg[k].append(f[k])
        for k in ("holds_on_sustain_candidate", "holds_on_pitched_attack", "hold_to_candidate_length_median", "drag_runs_matching_gesture", "pitched_gestures_charted"):
            if r[k] is not None:
                agg[k].append(r[k])
    L.append("\n## Summary (mean over songs)\n")
    for k, v in agg.items():
        L.append(f"- {k}: {np.mean(v):.3f} (median {np.median(v):.3f}, n={len(v)})")
    L.append("\n## Charted share of each layer's attacks (mean over songs)\n")
    for l in LAYERS:
        v = [r["charted_share"][l]["charted_share"] for _, r in rows if r["charted_share"][l]["charted_share"] is not None]
        L.append(f"- {l}: {np.mean(v):.3f}")
    L.append("\n## Corpus prior: head density by phrase energy tercile (hits/s)\n")
    L.append("| Tercile | p10 | p25 | p50 | p75 | p90 | Phrases |\n| --- | --- | --- | --- | --- | --- | --- |")
    for t in ("low", "mid", "high"):
        v = prior["head_density_by_energy"].get(t)
        if v:
            L.append(f"| {t} | {v['p10']} | {v['p25']} | {v['p50']} | {v['p75']} | {v['p90']} | {v['phrases']} |")
    L.append("\n## Best reading per phrase by energy tercile\n")
    for t in ("low", "mid", "high"):
        v = prior["best_reading_by_energy"].get(t)
        if v:
            L.append(f"- {t}: readings {v['readings']}; thinning levels {v['levels']}; mean best F1 {v['mean_best_f1']}")
    (OUT / "calibration.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    songs = corpus.songs()
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if names:
        songs = [s for s in songs if any(a in s["id"] for a in names)]
    lat = pass1(songs) if not (OUT / "layer-latency.json").exists() or "--relatency" in sys.argv else json.loads((OUT / "layer-latency.json").read_text())
    pass2(songs, lat)
