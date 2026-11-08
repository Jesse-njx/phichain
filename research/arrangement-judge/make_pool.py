"""Precompute iterative-generation negatives: the generator's real output procedure.

For each window, VARIANTS candidates with random temperature and lock ratio. Locked notes
keep their official x; a free note counts as replaced if it lands >= TOLERANCE_BINS away.
Held-out settings (temperature 0.5/1.5, 6 or 24 steps) are generated for test only and
never used in training.

python3 make_pool.py --generator runs/generator/best.pt --out runs/pool
"""
import argparse
import gzip
import pathlib
import json
import time

import numpy as np
import torch

from judge_model import ROOT, TOLERANCE_BINS, ArrangementTransformer, generate, load_windows

TRAIN_TEMPERATURES = (0.7, 0.9, 1.1)
LOCK_RATIOS = (0.0, 0.3, 0.6, 0.9)
HELDOUT = (dict(temperature=0.5, steps=12), dict(temperature=1.5, steps=12),
           dict(temperature=0.9, steps=6), dict(temperature=0.9, steps=24))


def candidate(generator, window, device, seed, temperature, steps, lock):
    rng = np.random.default_rng(seed)
    n = len(window["notes"])
    keep = rng.random(n) < lock
    locked = {i: window["notes"][i]["x"] for i in range(n) if keep[i]}
    if len(locked) == n:
        del locked[int(rng.integers(n))]
    x = generate(generator, window, device, seed=seed, steps=steps, temperature=temperature, locked=locked)
    bins = np.rint(np.asarray(x) * 127).astype(int)
    original = np.rint(np.array([m["x"] for m in window["notes"]]) * 127).astype(int)
    replaced = (np.abs(bins - original) >= TOLERANCE_BINS)
    bins = np.where(replaced, bins, original)
    return dict(bins=bins.tolist(), replaced=replaced.astype(int).tolist(), temperature=temperature, steps=steps, lock=lock)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", default=str(ROOT / "runs/generator/best.pt"))
    ap.add_argument("--out", default=str(ROOT / "runs/pool"))
    ap.add_argument("--variants", type=int, default=2)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    ck = torch.load(args.generator, map_location="cpu", weights_only=False)
    generator = ArrangementTransformer(ck["config"]["model"]).to(device); generator.load_state_dict(ck["model"]); generator.eval()
    splits = load_windows(); started = time.monotonic()
    for split, windows in splits.items():
        rows = []
        for i, w in enumerate(windows):
            rng = np.random.default_rng([("train", "validation", "test").index(split), i])
            cands = [candidate(generator, w, device, seed=int(rng.integers(2**31)),
                               temperature=float(rng.choice(TRAIN_TEMPERATURES)), steps=12,
                               lock=float(rng.choice(LOCK_RATIOS))) for _ in range(args.variants)]
            heldout = []
            if split == "test":
                heldout = [dict(candidate(generator, w, device, seed=90000 + i * 10 + j, temperature=h["temperature"],
                                          steps=h["steps"], lock=0.0), setting=f'T{h["temperature"]}-S{h["steps"]}')
                           for j, h in enumerate(HELDOUT)]
            rows.append(dict(id=w["id"], candidates=cands, heldout=heldout))
            if (i + 1) % 200 == 0:
                print(split, i + 1, len(windows), round(time.monotonic() - started), "s", flush=True)
        with gzip.open(out / f"{split}.json.gz", "wt") as f:
            json.dump(rows, f, separators=(",", ":"))
        print("wrote", split, len(rows), flush=True)
    (out / "config.json").write_text(json.dumps(dict(generator=args.generator, generator_step=ck["step"], variants=args.variants,
                                                     train_temperatures=TRAIN_TEMPERATURES, lock_ratios=LOCK_RATIOS,
                                                     heldout_test_settings=HELDOUT, tolerance_bins=TOLERANCE_BINS,
                                                     seconds=time.monotonic() - started), indent=2) + "\n")


if __name__ == "__main__":
    main()
