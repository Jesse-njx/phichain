"""Retrain the masked-v1 architecture on this dataset's song split, as the negative generator.

python3 train_generator.py --steps 3000 --run generator
"""
import argparse
import json
import math
import time

import numpy as np
import torch
import torch.nn.functional as F

from judge_model import ROOT, MODEL_CONFIG, ArrangementTransformer, batch, load_windows


@torch.no_grad()
def evaluate(model, windows, device, mode):
    model.eval(); rng = np.random.default_rng(123456); loss = count = hits = 0
    for s in range(0, len(windows), 32):
        f, k, x, target, mask, valid = batch(windows[s:s + 32], rng, device, mode=mode)
        logits = model(f, k, x, valid); sel = mask & valid
        loss += float(F.cross_entropy(logits[sel], target[sel], reduction="sum")); count += int(sel.sum())
        hits += int((logits.argmax(-1)[sel] == target[sel]).sum())
    return dict(cross_entropy=loss / count, exact_bin_accuracy=hits / count, masked_notes=count)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3000); ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--eval-every", type=int, default=200); ap.add_argument("--run", default="generator")
    args = ap.parse_args()
    folder = ROOT / "runs" / args.run; folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / "best.pt").exists(), "Use a new run name"
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(20261106); rng = np.random.default_rng(20261106)
    splits = load_windows()
    model = ArrangementTransformer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=.01)
    config = dict(model=MODEL_CONFIG, parameters=sum(p.numel() for p in model.parameters()), device=str(device),
                  training=vars(args), windows={k: len(v) for k, v in splits.items()}, torch=torch.__version__)
    (folder / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    best, history, started, losses = float("inf"), [], time.monotonic(), []
    for step in range(1, args.steps + 1):
        model.train()
        chosen = [splits["train"][int(i)] for i in rng.integers(len(splits["train"]), size=args.batch_size)]
        f, k, x, target, mask, valid = batch(chosen, rng, device, augment=True)
        rate = 3e-4 * min(1, step / 100) * (.15 + .85 * .5 * (1 + math.cos(math.pi * step / args.steps)))
        for g in opt.param_groups:
            g["lr"] = rate
        loss = F.cross_entropy(model(f, k, x, valid)[mask & valid], target[mask & valid], label_smoothing=.02)
        opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
        losses.append(float(loss))
        if step % args.eval_every == 0 or step == args.steps:
            full, partial = evaluate(model, splits["validation"], device, "full"), evaluate(model, splits["validation"], device, "partial")
            score = .5 * (full["cross_entropy"] + partial["cross_entropy"])
            history.append(dict(step=step, train_loss=float(np.mean(losses[-args.eval_every:])), validation_full=full,
                                validation_partial=partial, seconds=time.monotonic() - started))
            if score < best - 1e-4:
                best = score; torch.save(dict(model=model.state_dict(), step=step, config=config), folder / "best.pt")
            (folder / "history.json").write_text(json.dumps(history, indent=2) + "\n")
            print(json.dumps(history[-1]), flush=True)
    ck = torch.load(folder / "best.pt", map_location="cpu", weights_only=False); model.load_state_dict(ck["model"])
    result = dict(best_step=ck["step"], seconds=time.monotonic() - started,
                  test_full=evaluate(model, splits["test"], device, "full"),
                  test_partial=evaluate(model, splits["test"], device, "partial"))
    (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("RESULT", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
