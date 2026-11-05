"""A compact conditional masked Transformer for fixed-rhythm x arrangement."""
import math
import numpy as np
import torch
from torch import nn

MODEL_CONFIG = dict(bins=128, max_notes=128, features=18, width=192, heads=6,
                    layers=4, feedforward=768, dropout=0.1)


def encode_window(window, mirror=False, shuffle_simultaneous=False, rng=None):
    notes = [dict(n) for n in window['notes']]
    if shuffle_simultaneous:
        start = 0
        while start < len(notes):
            end = start+1
            while end < len(notes) and abs(notes[end]['time']-notes[start]['time']) < 1e-5:
                end += 1
            group = notes[start:end]; rng.shuffle(group); notes[start:end] = group
            start = end
    t = np.array([n['time'] for n in notes], dtype=np.float32)
    relative = t-t[0]
    previous = np.r_[0., np.diff(t)]
    following = np.r_[np.diff(t), 0.]
    duration = np.array([n['duration'] for n in notes], dtype=np.float32)
    beat = relative*window['bpm']/60
    chord = np.array([sum(abs(other['time']-n['time']) < 1e-5 for other in notes) for n in notes])
    columns = [relative/12, np.log1p(previous*8)/4, np.log1p(following*8)/4,
               np.log1p(duration*8)/4, np.full(len(notes), min(window['bpm']/300, 4)),
               np.full(len(notes), window['difficulty']/20), chord/8, beat/32]
    for period in (.25, .5, 1, 4, 16):
        columns.extend([np.sin(2*np.pi*beat/period), np.cos(2*np.pi*beat/period)])
    features = np.stack(columns, axis=1).astype(np.float32)
    kinds = np.array([n['type'] for n in notes], dtype=np.int64)
    positions = np.array([n['x'] for n in notes])
    if mirror:
        positions = 1-positions
    target = np.rint(positions*127).astype(np.int64)
    assert target.min() >= 0 and target.max() < 128
    return features, kinds, target


def batch(windows, rng, device, mode='mixed', augment=False):
    size, length = len(windows), max(len(w['notes']) for w in windows)
    f = np.zeros((size, length, MODEL_CONFIG['features']), dtype=np.float32)
    k = np.zeros((size, length), dtype=np.int64)
    x = np.full((size, length), 129, dtype=np.int64)
    target = np.full((size, length), -100, dtype=np.int64)
    mask = np.zeros((size, length), dtype=bool)
    valid = np.zeros((size, length), dtype=bool)
    for i, window in enumerate(windows):
        features, kinds, labels = encode_window(window, mirror=augment and rng.random()<.5,
                                               shuffle_simultaneous=augment, rng=rng)
        n = len(labels); f[i,:n] = features; k[i,:n] = kinds; x[i,:n] = labels
        target[i,:n] = labels; valid[i,:n] = True
        choice = rng.random()
        if mode == 'full' or (mode == 'mixed' and choice < .25):
            mask[i,:n] = True
        elif mode == 'partial' or choice < .75:
            rate = .5 if mode == 'partial' else rng.uniform(.15, .95)
            mask[i,:n] = rng.random(n)<rate
        else:
            count = max(1, int(n*rng.uniform(.25, .9)))
            start = int(rng.integers(n-count+1)); mask[i,start:start+count] = True
        if not mask[i,:n].any():
            mask[i,int(rng.integers(n))] = True
    x[mask] = 128
    return tuple(torch.from_numpy(v).to(device) for v in (f, k, x, target, mask, valid))


class ArrangementTransformer(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = dict(config or MODEL_CONFIG)
        c = self.config
        self.numeric = nn.Linear(c['features'], c['width'])
        self.kind = nn.Embedding(5, c['width'])
        self.position = nn.Embedding(c['bins']+2, c['width'])
        self.order = nn.Embedding(c['max_notes'], c['width'])
        layer = nn.TransformerEncoderLayer(c['width'], c['heads'], c['feedforward'], c['dropout'],
                                           activation='gelu', batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, c['layers'], enable_nested_tensor=False)
        self.norm = nn.LayerNorm(c['width'])
        self.head = nn.Linear(c['width'], c['bins'])
        self.apply(self._init)
        # MultiheadAttention stores its projection matrix directly rather than as Linear.
        for module in self.modules():
            if isinstance(module, nn.MultiheadAttention):
                nn.init.xavier_uniform_(module.in_proj_weight)

    @staticmethod
    def _init(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, std=.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(self, f, k, x, valid):
        order = torch.arange(x.shape[1], device=x.device)
        h = self.numeric(f)+self.kind(k)+self.position(x)+self.order(order)[None,:,:]
        h = self.encoder(h, src_key_padding_mask=~valid)
        return self.head(self.norm(h))


@torch.no_grad()
def generate(model, window, device, seed=0, steps=12, temperature=.9, locked=None):
    model.eval()
    rng = np.random.default_rng(seed)
    f, k, x, _, _, valid = batch([window], rng, device, mode='full')
    labels = np.full(len(window['notes']), 128, dtype=np.int64)
    locked = locked or {}
    for index, value in locked.items():
        labels[int(index)] = int(round(value*127))
    free = labels == 128
    initial_count = int(free.sum())
    for step in range(steps):
        if not free.any():
            break
        x[0,:len(labels)] = torch.from_numpy(labels).to(device)
        probabilities = torch.softmax(model(f,k,x,valid)[0]/temperature, dim=-1).cpu().numpy()
        indices = np.flatnonzero(free)
        sampled = []
        for i in indices:
            p = probabilities[i].astype(np.float64)
            sampled.append(rng.choice(128, p=p/p.sum()))
        sampled = np.array(sampled)
        confidence = probabilities[indices, sampled]
        remaining = int(initial_count*math.cos((step+1)/steps*math.pi/2))
        keep = max(1, len(indices)-remaining)
        selected = np.argsort(-confidence)[:keep]
        labels[indices[selected]] = sampled[selected]
        free[indices[selected]] = False
    assert not (labels == 128).any()
    return labels/127
