"""Train the judge on official windows vs generator negatives, then evaluate on test songs.

v3 negatives per window: 40% clean official, 30% a precomputed iterative generation
(make_pool.py; temperatures 0.7/0.9/1.1, lock 0-90%), 30% sparse random replacement of 1-3
notes. One-pass refill (v2) is kept for evaluation only.
Augmentation is a whole-window mirror applied identically to every kind; the order of
simultaneous notes is never shuffled, so it cannot become a shortcut.

python3 train_judge.py --pool runs/pool --steps 10000 --run judge-v3
"""
import argparse
import collections
import copy
import gzip
import json
import math
import pathlib
import time

import numpy as np
import torch
import torch.nn.functional as F

from judge_model import (JUDGE_CONFIG, ROOT, TOLERANCE_BINS, ArrangementTransformer, Judge, auroc, batch, corrupt,
                         load_windows)

MODES = ("clean", "onepass", "pool", "sparse")
MODE_P = (0.4, 0.0, 0.3, 0.3)
# Sparse mode: 1-3 notes get a random x bin drawn from the train-set marginal for their note
# type (official-looking values, not chart-specific), at least TOLERANCE_BINS from the original.
MARGINAL = None


def type_marginal(windows):
    counts = np.ones((5, 128))
    for w in windows:
        for n in w["notes"]:
            b = int(round(n["x"] * 127)); counts[n["type"], b] += .5; counts[n["type"], 127 - b] += .5
    return counts / counts.sum(1, keepdims=True)


def sparse_replace(w, rng, count=None):
    n = len(w["notes"]); count = count or int(rng.integers(1, 4))
    lab = [0] * n
    for i in rng.choice(n, size=min(count, n), replace=False):
        note = w["notes"][int(i)]; old = int(round(note["x"] * 127))
        while True:
            b = int(rng.choice(128, p=MARGINAL[note["type"]]))
            if abs(b - old) >= TOLERANCE_BINS:
                break
        note["x"] = b / 127; lab[int(i)] = 1
    return lab


def load_pool(folder, split):
    return json.load(gzip.open(pathlib.Path(folder) / f"{split}.json.gz", "rt"))


def assemble(generator, items, rng, device, augment):
    """items: (window, mode, pool_candidate or None). Returns features, judged x, labels, valid."""
    prepared, labels, rates, mirrors = [], [], [], []
    for window, mode, cand in items:
        w = copy.deepcopy(window)
        lab = [0] * len(w["notes"])
        if mode == "pool":
            for n, b in zip(w["notes"], cand["bins"]):
                n["x"] = b / 127
            lab = cand["replaced"]
        elif mode == "sparse":
            lab = sparse_replace(w, rng, (cand or {}).get("count"))
        mirror = augment and rng.random() < .5
        if mirror:
            for n in w["notes"]:
                n["x"] = 1 - n["x"]
        prepared.append(w); labels.append(lab)
        rates.append(rng.uniform(.1, .6) if mode == "onepass" else 0.0)
    f, k, _, target, _, valid = batch(prepared, rng, device, mode="full", augment=False)
    x = target.clamp(min=0)
    pool_lab = torch.zeros_like(valid)
    for i, lab in enumerate(labels):
        pool_lab[i, :len(lab)] = torch.tensor(lab, dtype=torch.bool, device=device)
    bad, replaced = corrupt(generator, f, k, x, valid, rng, rates=rates)
    return f, k, bad, replaced | pool_lab, valid


def sample_items(windows, pool, rng, size):
    items = []
    for i in rng.integers(len(windows), size=size):
        mode = MODES[int(rng.choice(len(MODES), p=MODE_P))]
        cand = pool[i]["candidates"][int(rng.integers(len(pool[i]["candidates"])))] if mode == "pool" else None
        items.append((windows[i], mode, cand))
    return items


@torch.no_grad()
def run(judge, generator, items, device, seed):
    judge.eval(); rng = np.random.default_rng(seed); out = []
    for s in range(0, len(items), 32):
        chunk = items[s:s + 32]
        f, k, x, replaced, valid = assemble(generator, chunk, rng, device, augment=False)
        note, window = judge(f, k, x, valid)
        note, window = torch.sigmoid(note), torch.sigmoid(window)
        for i, (w, mode, cand) in enumerate(chunk):
            n = int(valid[i].sum())
            out.append(dict(id=w["id"], mode=mode, setting=(cand or {}).get("setting"), lock=(cand or {}).get("lock"),
                            count=(cand or {}).get("count"), window=float(window[i]), note_scores=note[i, :n].cpu().tolist(),
                            replaced=replaced[i, :n].cpu().int().tolist()))
    return out


def metrics(rows):
    clean = [r for r in rows if r["mode"] == "clean"]
    def win_auc(neg):
        neg = [r for r in neg if any(r["replaced"])]
        return auroc([r["window"] for r in clean + neg], [1] * len(clean) + [0] * len(neg))
    notes = [(s, l) for r in rows for s, l in zip(r["note_scores"], r["replaced"])]
    return dict(note_auroc=auroc([s for s, _ in notes], [l for _, l in notes]),
                window_auroc_vs_pool=win_auc([r for r in rows if r["mode"] == "pool"]),
                window_auroc_vs_onepass=win_auc([r for r in rows if r["mode"] == "onepass"]),
                window_auroc_vs_sparse=win_auc([r for r in rows if r["mode"] == "sparse"]),
                sparse_note_auroc=auroc([s for r in rows if r["mode"] == "sparse" for s in r["note_scores"]],
                                        [l for r in rows if r["mode"] == "sparse" for l in r["replaced"]]),
                single_note_top1=float(np.mean([int(np.argmax(r["note_scores"])) == r["replaced"].index(1)
                                                for r in rows if r["mode"] == "sparse" and sum(r["replaced"]) == 1] or [np.nan])),
                mean_window_official=float(np.mean([r["window"] for r in clean])))


def eval_items(windows, pool, rates=None):
    items = [(w, "clean", None) for w in windows]
    items += [(w, "pool", c) for w, p in zip(windows, pool) for c in p["candidates"]]
    items += [(w, "onepass", None) for w in windows]
    items += [(w, "sparse", dict(count=c)) for w in windows for c in (1, 2, 3)]
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", default=str(ROOT / "runs/generator/best.pt"))
    ap.add_argument("--pool", default=str(ROOT / "runs/pool"))
    ap.add_argument("--steps", type=int, default=10000); ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--eval-every", type=int, default=500); ap.add_argument("--run", default="judge-v3")
    args = ap.parse_args()
    folder = ROOT / "runs" / args.run; folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "best.pt").exists(), "Use a new run name"
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(20261106); rng = np.random.default_rng(20261106)
    splits = load_windows()
    global MARGINAL
    MARGINAL = type_marginal(splits["train"])
    pools = {s: load_pool(args.pool, s) for s in splits}
    for s in splits:
        assert [p["id"] for p in pools[s]] == [w["id"] for w in splits[s]], "Pool does not match windows: " + s
    gck = torch.load(args.generator, map_location="cpu", weights_only=False)
    generator = ArrangementTransformer(gck["config"]["model"]).to(device); generator.load_state_dict(gck["model"]); generator.eval()
    judge = Judge().to(device)
    opt = torch.optim.AdamW(judge.parameters(), lr=2e-4, weight_decay=.01)
    config = dict(model=JUDGE_CONFIG, parameters=sum(p.numel() for p in judge.parameters()), generator=args.generator,
                  generator_step=gck["step"], pool=args.pool, training=vars(args), device=str(device), torch=torch.__version__,
                  windows={k: len(v) for k, v in splits.items()}, modes=dict(zip(MODES, MODE_P)),
                  augmentation="whole-window mirror only")
    (folder / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    val_items = eval_items(splits["validation"], pools["validation"])
    best, history, started, losses = -1, [], time.monotonic(), []
    for step in range(1, args.steps + 1):
        judge.train()
        items = sample_items(splits["train"], pools["train"], rng, args.batch_size)
        f, k, x, replaced, valid = assemble(generator, items, rng, device, augment=True)
        note, window = judge(f, k, x, valid)
        loss = (F.binary_cross_entropy_with_logits(note[valid], replaced[valid].float())
                + F.binary_cross_entropy_with_logits(window, (~replaced.any(1)).float()))
        rate = 2e-4 * min(1, step / 300) * (.05 + .95 * .5 * (1 + math.cos(math.pi * step / args.steps)))
        for g in opt.param_groups:
            g["lr"] = rate
        opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(judge.parameters(), 1.0); opt.step()
        losses.append(float(loss))
        if step % args.eval_every == 0 or step == args.steps:
            v = metrics(run(judge, generator, val_items, device, seed=777))
            score = v["note_auroc"] + v["window_auroc_vs_pool"] + v["window_auroc_vs_sparse"]
            history.append(dict(step=step, train_loss=float(np.mean(losses[-args.eval_every:])), validation=v,
                                seconds=time.monotonic() - started))
            if score > best:
                best = score; torch.save(dict(model=judge.state_dict(), step=step, config=config), folder / "best.pt")
            (folder / "history.json").write_text(json.dumps(history, indent=2) + "\n")
            print(json.dumps(history[-1]), flush=True)
    train_seconds = time.monotonic() - started
    ck = torch.load(folder / "best.pt", map_location="cpu", weights_only=False); judge.load_state_dict(ck["model"])
    test, tpool = splits["test"], pools["test"]
    rows = run(judge, generator, eval_items(test, tpool), device, seed=999)
    clean = [r for r in rows if r["mode"] == "clean"]
    def auc_vs(neg):
        return auroc([r["window"] for r in clean + neg], [1] * len(clean) + [0] * len(neg))
    pool_rows = [r for r in rows if r["mode"] == "pool"]
    held = run(judge, generator, [(w, "pool", c) for w, p in zip(test, tpool) for c in p["heldout"]], device, seed=1001)
    by_setting = collections.defaultdict(list)
    for r in held:
        by_setting[r["setting"]].append(r)
    mirrored = []
    for w in test:
        m = copy.deepcopy(w)
        for n in m["notes"]:
            n["x"] = 1 - n["x"]
        mirrored.append((m, "clean", None))
    mir = run(judge, generator, mirrored, device, seed=1002)
    result = dict(best_step=ck["step"], train_seconds=train_seconds, test_windows=len(test),
                  test_songs=len({w["song_id"] for w in test}),
                  overall=metrics(rows),
                  sparse_window_auroc_by_count={str(c): auc_vs([r for r in rows if r["mode"] == "sparse" and r["count"] == c])
                                                for c in (1, 2, 3)},
                  window_auroc_by_lock={str(l): auc_vs([r for r in pool_rows if r["lock"] == l])
                                        for l in sorted({r["lock"] for r in pool_rows})},
                  heldout_settings={s: dict(window_auroc=auc_vs(v), mean_window=float(np.mean([r["window"] for r in v])))
                                    for s, v in sorted(by_setting.items())},
                  mean_window=dict(official=float(np.mean([r["window"] for r in clean])),
                                   pool=float(np.mean([r["window"] for r in pool_rows])),
                                   onepass=float(np.mean([r["window"] for r in rows if r["mode"] == "onepass"])),
                                   sparse=float(np.mean([r["window"] for r in rows if r["mode"] == "sparse"]))),
                  mean_abs_mirror_gap=float(np.mean([abs(a["window"] - b["window"]) for a, b in zip(clean, mir)])))
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    with gzip.open(folder / "test-scores.json.gz", "wt") as f:
        json.dump(dict(rows=rows, heldout=held), f)
    print("RESULT", json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
