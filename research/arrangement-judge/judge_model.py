"""Judge: detect which notes' x positions were replaced by a masked generator (ELECTRA-style).

Positives are official windows. Negatives are made on the fly: a masked generator
(the masked-v1 architecture, retrained on this dataset's split) refills a random
subset of x positions. Timing, type and hold duration are never changed.
"""
import gzip
import json
import math
import pathlib
import sys

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "arrangement-training"))
from masked_model import ArrangementTransformer, MODEL_CONFIG, batch, generate  # noqa: E402,F401

JUDGE_CONFIG = dict(features=18, width=256, heads=8, layers=6, feedforward=1024, dropout=0.1,
                    bins=128, max_notes=128)
# A sampled x within this many bins of the original counts as unchanged (and is reset to it).
TOLERANCE_BINS = 2


def load_windows():
    """Windows in the dict layout masked_model.batch expects; x clamped to the screen."""
    rows = json.load(gzip.open(ROOT / "processed/windows.json.gz", "rt"))
    out = {"train": [], "validation": [], "test": []}
    for w in rows:
        notes = [dict(id=str(i), time=t, type=k, x=min(1.0, max(0.0, x)), duration=d)
                 for i, (t, k, x, d) in enumerate(w["tokens"])]
        out[w["split"]].append(dict(id=w["id"], song_id=w["song_id"], chart_id=w["chart_id"], level=w["level"],
                                    bpm=w["bpm"], difficulty=w["constant"] or 15.0, notes=notes))
    return out


class Judge(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = c = dict(config or JUDGE_CONFIG)
        self.numeric = nn.Linear(c["features"] + 1, c["width"])
        self.kind = nn.Embedding(5, c["width"])
        self.position = nn.Embedding(c["bins"], c["width"])
        self.order = nn.Embedding(c["max_notes"], c["width"])
        layer = nn.TransformerEncoderLayer(c["width"], c["heads"], c["feedforward"], c["dropout"],
                                           activation="gelu", batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, c["layers"], enable_nested_tensor=False)
        self.norm = nn.LayerNorm(c["width"])
        self.note_head = nn.Linear(c["width"], 1)
        self.window_head = nn.Linear(c["width"], 1)

    def forward(self, f, k, bins, valid):
        order = torch.arange(bins.shape[1], device=bins.device)
        numeric = torch.cat([f, (bins.float() / (self.config["bins"] - 1)).unsqueeze(-1)], -1)
        h = self.numeric(numeric) + self.kind(k) + self.position(bins.clamp(0, self.config["bins"] - 1)) + self.order(order)[None]
        h = self.norm(self.encoder(h, src_key_padding_mask=~valid))
        pooled = (h * valid.unsqueeze(-1)).sum(1) / valid.sum(1, keepdim=True)
        # note logit: "this x was replaced"; window logit: "this window is official"
        return self.note_head(h).squeeze(-1), self.window_head(pooled).squeeze(-1)


def real_batch(windows, rng, device, augment):
    """Features, types, true x bins and validity; mirror/permutation augmentation on request."""
    f, k, _, target, _, valid = batch(windows, rng, device, mode="full", augment=augment)
    return f, k, target.clamp(min=0), valid


@torch.no_grad()
def corrupt(generator, f, k, x, valid, rng, clean_fraction=0.3, rate_range=(0.1, 0.6), temperature=1.0, rates=None):
    """Refill a random subset of x with one generator pass. Returns new x and replaced labels."""
    size, length = x.shape
    mask = np.zeros((size, length), dtype=bool)
    lengths = valid.sum(1).cpu().numpy()
    for i, n in enumerate(lengths):
        if rates is None and rng.random() < clean_fraction:
            continue
        rate = rates[i] if rates is not None else rng.uniform(*rate_range)
        if rate <= 0:
            continue
        if rates is None and rng.random() < 0.5:
            count = max(1, int(round(n * rate)))
            start = int(rng.integers(n - count + 1)); mask[i, start:start + count] = True
        else:
            mask[i, :n] = rng.random(n) < rate
            if not mask[i, :n].any():
                mask[i, int(rng.integers(n))] = True
    mask = torch.from_numpy(mask).to(x.device) & valid
    shown = x.masked_fill(mask, 128)
    logits = generator(f, k, shown, valid) / temperature
    sampled = torch.distributions.Categorical(logits=logits).sample()
    replaced = mask & ((sampled - x).abs() >= TOLERANCE_BINS)
    return torch.where(replaced, sampled, x), replaced


def auroc(scores, labels):
    scores, labels = np.asarray(scores, float), np.asarray(labels, bool)
    pos, neg = labels.sum(), (~labels).sum()
    if not pos or not neg:
        return float("nan")
    order = scores.argsort(); ranks = np.empty(len(scores)); ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks for ties
    _, inverse, counts = np.unique(scores, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, ranks); ranks = (sums / counts)[inverse]
    return float((ranks[labels].sum() - pos * (pos + 1) / 2) / (pos * neg))
