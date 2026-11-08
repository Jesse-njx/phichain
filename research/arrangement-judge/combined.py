"""Combined judge: generator surprise (local) + discriminative judge v3 (window style).

Per note: surprise = -log p(x | all other notes) under the masked generator. This is the
per-note feedback. Per window, two signals are compared with official validation windows:
style (v3 "official" logit) and local (max note surprise). Combined p = min(p_style, p_local):
a window is flagged when either looks unusual. Only official windows set the references.

python3 combined.py fit                       # references from validation, evaluate on test
python3 combined.py score CHART.json --constant 15.5 --out report.json
"""
import argparse
import collections
import json
import pathlib
import sys

import numpy as np
import torch

import train_judge as T
from judge_model import ROOT, ArrangementTransformer, Judge, auroc, load_windows



def load_models(device, generator=ROOT / "runs/generator/best.pt", judge=ROOT / "runs/judge-v3/best.pt"):
    g = torch.load(generator, map_location="cpu", weights_only=False)
    G = ArrangementTransformer(g["config"]["model"]).to(device); G.load_state_dict(g["model"]); G.eval()
    j = torch.load(judge, map_location="cpu", weights_only=False)
    J = Judge(j["config"]["model"]).to(device); J.load_state_dict(j["model"]); J.eval()
    return G, J


@torch.no_grad()
def features(G, J, f, k, x, valid):
    """Per-row note features and window features for an assembled batch."""
    note_logit, window_logit = J(f, k, x, valid)
    rows = []
    for i in range(x.shape[0]):
        n = int(valid[i].sum())
        xs = x[i:i + 1].repeat(n, 1); idx = torch.arange(n, device=x.device); xs[idx, idx] = 128
        logp = torch.log_softmax(G(f[i:i + 1].repeat(n, 1, 1), k[i:i + 1].repeat(n, 1), xs, valid[i:i + 1].repeat(n, 1)), -1)
        s = (-logp[idx, idx, x[i, :n]]).cpu().numpy()
        jn = note_logit[i, :n].cpu().numpy()
        top = np.sort(s)[::-1]
        rows.append(dict(notes=np.stack([s, jn], 1),
                         window=np.array([float(window_logit[i]), s.mean(), top[0], top[:3].mean(), jn.max()])))
    return rows


def collect(G, J, items, device, seed):
    rng = np.random.default_rng(seed); out = []
    for s in range(0, len(items), 32):
        chunk = items[s:s + 32]
        f, k, x, replaced, valid = T.assemble(G, chunk, rng, device, augment=False)
        for (w, mode, cand), feat, i in zip(chunk, features(G, J, f, k, x, valid), range(len(chunk))):
            n = int(valid[i].sum())
            out.append(dict(id=w["id"], mode=mode, lock=(cand or {}).get("lock"), count=(cand or {}).get("count"),
                            setting=(cand or {}).get("setting"), replaced=replaced[i, :n].cpu().numpy().astype(int), **feat))
    return out


class Reference:
    """Empirical distribution of a window signal on official validation windows.

    p(value) = share of official windows that look at least this unofficial. A window is
    flagged when either signal is unusual: combined p = min(p_style, p_local).
    """
    def __init__(self, values):
        self.values = np.sort(np.asarray(values, float))

    def p(self, value):  # value: higher = more official
        return (np.searchsorted(self.values, value, side="right") + 1) / (len(self.values) + 1)


def signals(r):
    # style: judge v3 window logit (higher = official); local: negative max note surprise.
    return r["window"][0], -r["window"][2]


def items_for(windows, pool):
    items = T.eval_items(windows, pool)
    items += [(w, "pool", c) for w, p in zip(windows, pool) for c in p.get("heldout", [])]
    return items


def evaluate(rows, style_ref, local_ref):
    clean = [r for r in rows if r["mode"] == "clean"]
    def wscore(r, which):
        style, local = signals(r)
        return {"combined": min(style_ref.p(style), local_ref.p(local)), "judge_v3": r["window"][0],
                "surprise_max": -r["window"][2], "surprise_mean": -r["window"][1]}[which]
    groups = collections.OrderedDict()
    for lock in (0.0, 0.3, 0.6, 0.9):
        groups[f"pool_lock_{lock}"] = [r for r in rows if r["mode"] == "pool" and r["lock"] == lock and r["setting"] is None]
    groups["pool_heldout_settings"] = [r for r in rows if r["setting"]]
    for c in (1, 2, 3):
        groups[f"sparse_{c}"] = [r for r in rows if r["mode"] == "sparse" and r["count"] == c]
    groups["onepass"] = [r for r in rows if r["mode"] == "onepass"]
    out = {}
    for name, neg in groups.items():
        neg = [r for r in neg if r["replaced"].any()]
        entry = {}
        for which in ("combined", "judge_v3", "surprise_max", "surprise_mean"):
            entry[f"window_auroc_{which}"] = auroc([wscore(r, which) for r in clean + neg], [1] * len(clean) + [0] * len(neg))
        lab = np.concatenate([r["replaced"] for r in neg])
        entry["note_auroc_surprise"] = auroc(np.concatenate([r["notes"][:, 0] for r in neg]), lab)
        entry["note_auroc_judge_v3"] = auroc(np.concatenate([r["notes"][:, 1] for r in neg]), lab)
        if name == "sparse_1":
            entry["top1_surprise"] = float(np.mean([int(np.argmax(r["notes"][:, 0])) == int(np.argmax(r["replaced"])) for r in neg]))
        entry["windows"] = len(neg)
        out[name] = entry
    return out


def fit():
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    G, J = load_models(device)
    splits = load_windows(); T.MARGINAL = T.type_marginal(splits["train"])
    val = collect(G, J, items_for(splits["validation"], T.load_pool(ROOT / "runs/pool", "validation")), device, seed=11)
    official = [signals(r) for r in val if r["mode"] == "clean"]
    style_ref, local_ref = Reference([o[0] for o in official]), Reference([o[1] for o in official])
    test = collect(G, J, items_for(splits["test"], T.load_pool(ROOT / "runs/pool", "test")), device, seed=12)
    folder = ROOT / "runs/combined"; folder.mkdir(parents=True, exist_ok=True)
    params = dict(style_reference=style_ref.values.tolist(), local_reference=local_ref.values.tolist(),
                  reference="official validation windows (12 songs); only clean windows are used, no negatives",
                  window_p="min(p_style, p_local); low = unlike official", note_feedback="generator surprise, nats")
    (folder / "params.json").write_text(json.dumps(params, indent=2) + "\n")
    result = dict(test_windows=len(splits["test"]), validation_rows=len(val), test=evaluate(test, style_ref, local_ref))
    (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=1))


@torch.no_grad()
def score_chart(path, constant=15.0, top=5):
    """Score an official-v3 chart: flatten, window, and report windows and suspicious notes."""
    import copy
    from build_dataset import pure_notes, segments, windows_of
    from judge_model import batch
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    G, J = load_models(device)
    params = json.loads((ROOT / "runs/combined/params.json").read_text())
    style_ref, local_ref = Reference(params["style_reference"]), Reference(params["local_reference"])
    source = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
    notes = pure_notes(source)
    windows = windows_of(notes, segments(notes))
    rng = np.random.default_rng(0); report = []
    for w in windows:
        t0 = w[0]["time"]
        win = dict(id="", bpm=source["judgeLineList"][0]["bpm"], difficulty=constant,
                   notes=[dict(id=str(i), time=n["time"] - t0, type=n["type"], duration=n["duration"],
                               x=min(1.0, max(0.0, n["x"]))) for i, n in enumerate(w)])
        f, k, _, target, _, valid = batch([win], rng, device, mode="full")
        feat = features(G, J, f, k, target.clamp(min=0), valid)[0]
        style, local = signals(feat)
        ps, pl = float(style_ref.p(style)), float(local_ref.p(local))
        order = np.argsort(-feat["notes"][:, 0])[:top]
        report.append(dict(start_s=round(t0, 3), end_s=round(w[-1]["time"], 3), notes=len(w),
                           p_combined=min(ps, pl), p_style=ps, p_local=pl,
                           suspicious_notes=[dict(time_s=round(w[i]["time"], 3), type=w[i]["type"], x=round(w[i]["x"], 4),
                                                  surprise=round(float(feat["notes"][i, 0]), 2)) for i in order]))
    covered = sum(len(w) for w in windows)
    return dict(chart=str(path), notes=len(notes), windows=len(report), notes_in_windows_with_overlap=covered,
                meaning="p_* = share of official validation windows at least this unusual; low = unlike official charts. "
                        "Style catches generator-like arrangements; local catches single misplaced notes. Not a quality verdict.",
                windows_report=report)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["fit", "score"])
    ap.add_argument("chart", nargs="?"); ap.add_argument("--constant", type=float, default=15.0)
    ap.add_argument("--top", type=int, default=5); ap.add_argument("--out")
    args = ap.parse_args()
    if args.command == "fit":
        fit()
    else:
        assert args.chart, "score needs an official-v3 chart JSON"
        result = score_chart(args.chart, args.constant, args.top)
        text = json.dumps(result, ensure_ascii=False, indent=1)
        if args.out:
            pathlib.Path(args.out).write_text(text + "\n")
        print(text)
