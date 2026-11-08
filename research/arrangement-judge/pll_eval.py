"""Score windows with the masked generator's pseudo-likelihood: mask each note in turn and
take -log p(official-or-candidate x | all other notes). No negatives are needed to train it.

python3 pll_eval.py --generator runs/generator/best.pt --pool runs/pool --out runs/pll/result.json
"""
import argparse, collections, copy, json, pathlib

import numpy as np
import torch

import train_judge as T
from judge_model import ROOT, ArrangementTransformer, auroc, batch, load_windows


@torch.no_grad()
def surprise(G, window, device):
    rng = np.random.default_rng(0)
    f, k, _, target, _, valid = batch([window], rng, device, mode="full")
    x = target.clamp(min=0); n = int(valid.sum())
    xs = x.repeat(n, 1); idx = torch.arange(n, device=device); xs[idx, idx] = 128
    logp = torch.log_softmax(G(f.repeat(n, 1, 1), k.repeat(n, 1), xs, valid.repeat(n, 1)), -1)[idx, idx, x[0, :n]]
    return (-logp).cpu().numpy()


def with_bins(w, bins):
    w = copy.deepcopy(w)
    for n, b in zip(w["notes"], bins):
        n["x"] = b / 127
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", default=str(ROOT / "runs/generator/best.pt"))
    ap.add_argument("--pool", default=str(ROOT / "runs/pool"))
    ap.add_argument("--out", default=str(ROOT / "runs/pll/result.json"))
    args = ap.parse_args()
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    ck = torch.load(args.generator, map_location="cpu", weights_only=False)
    G = ArrangementTransformer(ck["config"]["model"]).to(device); G.load_state_dict(ck["model"]); G.eval()
    splits = load_windows(); T.MARGINAL = T.type_marginal(splits["train"])
    test, pool = splits["test"], T.load_pool(args.pool, "test")
    official = [surprise(G, w, device) for w in test]
    off_mean = [float(s.mean()) for s in official]
    def win_auc(neg):  # higher mean surprise = less official
        return auroc([-v for v in off_mean + neg], [1] * len(off_mean) + [0] * len(neg))
    res = dict(generator=args.generator, generator_step=ck["step"], test_windows=len(test),
               mean_surprise_official=float(np.mean(off_mean)))
    by_lock = collections.defaultdict(list)
    for w, p in zip(test, pool):
        for c in p["candidates"]:
            if any(c["replaced"]):
                by_lock[c["lock"]].append(float(surprise(G, with_bins(w, c["bins"]), device).mean()))
    res["window_auroc_by_lock"] = {str(l): win_auc(v) for l, v in sorted(by_lock.items())}
    held = collections.defaultdict(list)
    for w, p in zip(test, pool):
        for c in p["heldout"]:
            held[c["setting"]].append(float(surprise(G, with_bins(w, c["bins"]), device).mean()))
    res["heldout_settings_window_auroc"] = {s: win_auc(v) for s, v in sorted(held.items())}
    rng = np.random.default_rng(3); sparse = {}
    for count in (1, 2, 3):
        scores, labels, top1, wins = [], [], [], []
        for w in test:
            w2 = copy.deepcopy(w); lab = T.sparse_replace(w2, rng, count)
            s = surprise(G, w2, device); scores += s.tolist(); labels += lab; wins.append(float(s.mean()))
            if count == 1:
                top1.append(int(np.argmax(s)) == lab.index(1))
        sparse[str(count)] = dict(note_auroc=auroc(scores, labels), window_auroc=win_auc(wins),
                                  **({"top1": float(np.mean(top1)), "chance_top1": float(np.mean([1 / len(w["notes"]) for w in test]))} if count == 1 else {}))
    res["sparse_random"] = sparse
    mir = [float(surprise(G, with_bins(w, [127 - round(n["x"] * 127) for n in w["notes"]]), device).mean()) for w in test]
    res["mean_abs_mirror_gap_nats"] = float(np.mean(np.abs(np.array(mir) - np.array(off_mean))))
    out = pathlib.Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
