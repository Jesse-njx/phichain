"""Every signal we have, as a number on every note of one chart.

Per note (pure configuration):
- finger_<style>: the simulated player's finger (L0/R0 index, L1/R1 middle, L2/R2 ring; None = no finger free).
- cost_<style>: the simulated player's cost for this note's group (movement, re-press, crossing, shape, misses).
- feel_<style>: hand-pattern surprisal (nats) of the four groups ending at this note's group, given the rhythm;
  high = a hand pattern official charts rarely use at this rhythm.
- surprise: masked-generator surprise (nats), -log p(x | all other notes in the window); high = a placement
  official charts would rarely make. Averaged over the windows that contain the note; None outside windows.
- window_p_style: lowest judge-v3 style p of the windows containing the note.
- *_best: the lower of the two- and four-finger values (a player picks the style that suits them).
- rare_*: share of official notes at least this extreme; the common scale for every number.

python3 note_scores.py CHART.json --constant 15.5 --out notes.json
"""
import argparse
import json
import pathlib

import numpy as np

import feel as F
from build_dataset import pure_notes, segments, windows_of
from player import groups_of, play

ROOT = pathlib.Path(__file__).resolve().parent


def note_scores(path, constant=15.0, counts=None, models=None):
    import torch
    import combined as C
    from judge_model import batch
    source = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    notes = pure_notes(source)
    rows = [dict(t=round(n["time"], 4), type=n["type"], x=round(n["x"], 4), dur=round(n["duration"], 4)) for n in notes]
    tokens = [[n["time"], n["type"], n["x"], n["duration"]] for n in notes]
    groups = groups_of(tokens)
    index, k = [], 0  # note indices per group
    for g in groups:
        index.append(list(range(k, k + len(g)))); k += len(g)
    counts = counts or F.fit_counts(F.load_fingering())
    for style in F.STYLES:
        _, rec = play(tokens, style)
        for gi, r in enumerate(rec):
            total = sum(r["cost"].values())
            for idx, _, finger in r["assign"]:
                for j in idx:
                    rows[index[gi][j]][f"finger_{style}"] = finger
            for j in index[gi]:
                rows[j][f"cost_{style}"] = round(total, 3)
        seq = F.sequence(tokens, rec)
        for si, kinds, gaps, pat, shape in F.patterns(seq):
            v = round(counts[style].surprisal(kinds, gaps, pat, shape), 2)
            for j in index[seq[si][3]]:
                rows[j][f"feel_{style}"] = v
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    G, J = models or C.load_models(device)
    params = json.loads((ROOT / "runs/combined/params.json").read_text())
    style_ref = C.Reference(params["style_reference"])
    position = {id(n): i for i, n in enumerate(notes)}
    acc = [[] for _ in notes]; pst = [[] for _ in notes]
    rng = np.random.default_rng(0)
    for w in windows_of(notes, segments(notes)):
        t0 = w[0]["time"]
        win = dict(id="", bpm=source["judgeLineList"][0]["bpm"], difficulty=constant,
                   notes=[dict(id=str(i), time=n["time"] - t0, type=n["type"], duration=n["duration"],
                               x=min(1.0, max(0.0, n["x"]))) for i, n in enumerate(w)])
        f, k_, _, target, _, valid = batch([win], rng, device, mode="full")
        feat = C.features(G, J, f, k_, target.clamp(min=0), valid)[0]
        ps = float(style_ref.p(C.signals(feat)[0]))
        for n, s in zip(w, feat["notes"][:, 0]):
            acc[position[id(n)]].append(float(s)); pst[position[id(n)]].append(ps)
    for r, a, p in zip(rows, acc, pst):
        r["surprise"] = round(float(np.mean(a)), 2) if a else None
        r["window_p_style"] = round(min(p), 3) if p else None
    return rows


REFERENCE = ROOT / "runs/feel/note_reference.json"


def _chart_costs(item):
    path, constant = item
    notes = pure_notes(json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig")))
    tokens = [[n["time"], n["type"], n["x"], n["duration"]] for n in notes]
    out = {}
    for style in F.STYLES:
        _, rec = play(tokens, style)
        out[style] = [round(sum(r["cost"].values()), 3) for r in rec for _ in range(r["notes"])]
    out["best"] = [min(a, b) for a, b in zip(out["two"], out["four"])]
    return constant, out


def official_charts():
    man = json.loads((ROOT / "manifest.json").read_text())
    root = lambda c: (ROOT.parent / "arrangement-training/raw") if c["level"] == "IN" else ROOT / "raw"
    return [(c, str(root(c) / c["source_path"])) for c in man]


def build_reference():
    """Official note distributions for the rarity scale.

    feel and surprise: validation-split charts (not used for the feel counts or the generator's
    training). cost: every official chart, with its constant, since the player is not trained."""
    import multiprocessing
    charts = official_charts()
    split = json.loads((ROOT / "processed/splits.json").read_text())
    with multiprocessing.Pool() as pool:
        costs = pool.map(_chart_costs, [(p, c["constant"]) for c, p in charts])
    counts = F.fit_counts(F.load_fingering())
    ref = dict(cost=[dict(constant=c, **v) for c, v in costs], feel={s: [] for s in (*F.STYLES, "best")}, surprise=[])
    val_rows = []
    for c, path in charts:
        if split[c["song_id"]] != "validation":
            continue
        rows = note_scores(path, c["constant"], counts)
        val_rows.append((rows, c["constant"]))
        for r in rows:
            for s in F.STYLES:
                if r.get(f"feel_{s}") is not None:
                    ref["feel"][s].append(r[f"feel_{s}"])
            if r.get("feel_two") is not None and r.get("feel_four") is not None:
                ref["feel"]["best"].append(min(r["feel_two"], r["feel_four"]))
            if r["surprise"] is not None:
                ref["surprise"].append(r["surprise"])
    # fault scale: the distribution of min(feel rarity, placement rarity) on the same official notes
    ref["fault_min"] = []
    for rows, constant in val_rows:
        add_rarity(rows, constant, ref, fault=False)
        ref["fault_min"] += [m for m in (_fault_min(r)[0] for r in rows) if m is not None]
    REFERENCE.write_text(json.dumps(ref) + "\n")
    return ref


def _fault_min(r):
    """The more unusual of feel (best style) and placement; feel is missing on drag-only groups."""
    cands = [(v, k) for v, k in ((r.get("rare_feel_best"), "feel"), (r.get("rare_surprise"), "placement")) if v is not None]
    return min(cands) if cands else (None, None)


def add_rarity(rows, constant, ref=None, fault=True):
    """rare_* = share of official notes at least this extreme (0.03 = only 3% of official notes).
    Cost is compared with charts within 0.6 of this constant (widened until 5 charts).

    fault = one number for "unlike official charts": the more unusual of feel (best style) and
    placement, re-calibrated on official notes so that fault < 0.05 holds for about 5% of them
    (the minimum of two rarities alone would flag about twice as many). fault_reason says which
    signal drove it. Cost stays separate: it is difficulty, not a fault."""
    ref = ref or json.loads(REFERENCE.read_text())
    def share(values):
        v = np.sort(np.asarray(values, float))
        return lambda x: None if x is None else round(float((len(v) - np.searchsorted(v, x, side="left") + 1) / (len(v) + 1)), 4)
    band = .6
    while True:
        near = [c for c in ref["cost"] if abs(c["constant"] - constant) <= band]
        if len(near) >= 5:
            break
        band += .3
    cost = {s: share([x for c in near for x in c[s]]) for s in ("two", "four", "best")}
    feel = {s: share(ref["feel"][s]) for s in ("two", "four", "best")}
    sur = share(ref["surprise"])
    for r in rows:
        r["cost_best"] = min(r["cost_two"], r["cost_four"])
        f2, f4 = r.get("feel_two"), r.get("feel_four")
        r["feel_best"] = None if f2 is None or f4 is None else min(f2, f4)
        for s in ("two", "four", "best"):
            r[f"rare_cost_{s}"] = cost[s](r[f"cost_{s}"])
            r[f"rare_feel_{s}"] = feel[s](r.get(f"feel_{s}"))
        r["rare_surprise"] = sur(r["surprise"])
    if fault:
        low = np.sort(np.asarray(ref["fault_min"], float))  # low = unusual: share of official notes at or below
        fm = lambda x: round(float((np.searchsorted(low, x, side="right") + 1) / (len(low) + 1)), 4)
        for r in rows:
            m, reason = _fault_min(r)
            r["fault"], r["fault_reason"] = (fm(m), reason) if m is not None else (None, None)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chart", help="official-v3 chart, or 'reference' to rebuild the official note distributions")
    ap.add_argument("--constant", type=float, default=15.0); ap.add_argument("--out")
    a = ap.parse_args()
    if a.chart == "reference":
        build_reference(); raise SystemExit
    out = json.dumps(add_rarity(note_scores(a.chart, a.constant), a.constant), ensure_ascii=False)
    if a.out:
        pathlib.Path(a.out).write_text(out + "\n")
    else:
        print(out)
