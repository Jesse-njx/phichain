"""Small, local, chart-supervised audio alignment experiment; no chart writes.

Run with local/music-flow-study/.venv/bin/python. Scores are rankings, not
calibrated probabilities or complete acoustic event labels.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

os.environ.setdefault('NUMBA_CACHE_DIR', '/private/tmp/phichain-music-numba')
import librosa
import numpy as np
from scipy.signal import find_peaks
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SR, HOP, FFT, CONTEXT = 22050, 220, 1024, 4
STEP = HOP / SR
SEEDS = [17, 29]
BUDGETS = [4, 8, 12]
torch.set_num_threads(4)
torch.use_deterministic_algorithms(True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def inventory():
    latest = json.loads((ROOT/'local/arrangement-training/manifest.json').read_text())
    previous = json.loads((ROOT/'local/overnight-study/corpus/manifest.json').read_text())
    audio = {r['id']: r['music'] for r in previous}
    rows = []
    for row in latest:
        sid = row['song_id']
        if sid not in audio or row['format_version'] != 3:
            continue
        cp = ROOT/'local/arrangement-training'/row['local_path']
        ap = ROOT/audio[sid]['path']
        assert sha(cp) == row['sha256']
        assert sha(ap) == audio[sid]['sha256']
        rows.append(dict(id=sid, title=row['title'], chart=str(cp), audio=str(ap),
                         chart_sha256=sha(cp), audio_sha256=sha(ap)))
    rows.sort(key=lambda r: hashlib.sha256(('timing-pilot-v1:'+r['id']).encode()).hexdigest())
    n = len(rows)
    for i, row in enumerate(rows):
        row['split'] = 'train' if i < int(n*.6) else 'validation' if i < int(n*.8) else 'test'
    assert len({r['audio_sha256'] for r in rows}) == n
    return rows


def references(row):
    chart = json.loads(Path(row['chart']).read_text())
    assert chart['formatVersion'] == 3
    return np.array(sorted({round(n['time']*60/(32*line['bpm'])+chart.get('offset', 0), 6)
                            for line in chart['judgeLineList']
                            for side in ('notesAbove', 'notesBelow') for n in line[side]
                            if n['type'] in (1, 3)}))


def features(row):
    cache = OUT/'features'/f"{row['audio_sha256']}.npz"
    cache.parent.mkdir(exist_ok=True)
    if cache.exists():
        with np.load(cache) as d:
            return d['x'], d['flux'], float(d['duration'])
    y = np.frombuffer(subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error',
        '-i', row['audio'], '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-']), dtype='<f4').copy()
    s = np.abs(librosa.stft(y, n_fft=FFT, hop_length=HOP))
    mel = librosa.feature.melspectrogram(S=s**2, sr=SR, n_fft=FFT, n_mels=32)
    log = np.log(np.maximum(mel, 1e-8)).T
    # Whole-song normalization is permitted for this offline analysis tool.
    level = (log-log.mean(axis=0))/np.maximum(log.std(axis=0), .5)
    delta = np.maximum(np.diff(log, axis=0, prepend=log[:1]), 0)
    flux = delta.mean(axis=1)
    delta = delta/np.maximum(delta.std(axis=0), .1)
    x = np.concatenate([level, delta], axis=1).astype('float32')
    np.savez_compressed(cache, x=x, flux=flux, duration=len(y)/SR)
    return x, flux, len(y)/SR


def context(x, indices):
    idx = np.clip(indices[:, None]+np.arange(-CONTEXT, CONTEXT+1), 0, len(x)-1)
    return x[idx].reshape(len(indices), -1)


def pairs(song):
    ref = song['reference']
    positive, shifted = [], []
    # Local distractors are weak comparisons, NEVER verified acoustic negatives.
    # No examples are sampled from chart rests or other far-unlabelled frames.
    for delta in [-.11, -.09, -.07, -.05, .05, .07, .09, .11]:
        shifted_time = ref + delta
        near = np.searchsorted(ref, shifted_time)
        dist = np.minimum(abs(shifted_time-ref[np.clip(near, 0, len(ref)-1)]),
                          abs(shifted_time-ref[np.clip(near-1, 0, len(ref)-1)]))
        good = (dist > .03) & (shifted_time > .1) & (shifted_time < song['duration']-.1)
        positive.extend(np.rint(ref[good]/STEP).astype(int))
        shifted.extend(np.rint(shifted_time[good]/STEP).astype(int))
    return np.array(positive), np.array(shifted)


def model():
    return nn.Sequential(nn.Linear(64*(2*CONTEXT+1), 64), nn.ReLU(), nn.Linear(64, 1))


def predict(net, song):
    with torch.no_grad():
        return np.concatenate([net(torch.from_numpy(context(song['x'], np.arange(a, min(a+4096, len(song['x'])))))).numpy().ravel()
                               for a in range(0, len(song['x']), 4096)])


def events(scores, duration, budget, shift=0):
    peaks, _ = find_peaks(scores, distance=round(.04/STEP))
    # Fixed events/second cap, independent of test chart counts/density.
    count = min(len(peaks), int(duration*budget))
    keep = peaks[np.argsort(scores[peaks], kind='stable')[-count:]] if count else []
    result = np.sort(np.asarray(keep)*STEP+shift)
    return result[(result >= 0) & (result <= duration)]


def matched(ref, pred, tol):
    i = j = total = 0
    while i < len(ref) and j < len(pred):
        if pred[j] < ref[i]-tol: j += 1
        elif pred[j] > ref[i]+tol: i += 1
        else: total += 1; i += 1; j += 1
    return total


def report(songs, scores, shift):
    result = {}
    for budget in BUDGETS:
        per = []
        for s, score in zip(songs, scores):
            pred = events(score, s['duration'], budget, shift)
            ref = s['reference']
            per.append(dict(id=s['row']['id'], title=s['row']['title'], reference_count=len(ref),
                candidate_count=len(pred), candidates_per_second=len(pred)/s['duration'],
                coverage={str(ms):matched(ref, pred, ms/1000)/len(ref) for ms in [10,20,35,50]}))
        result[str(budget)] = dict(songs=per,
            macro_coverage={str(ms):float(np.mean([p['coverage'][str(ms)] for p in per])) for ms in [10,20,35,50]},
            mean_candidates_per_second=float(np.mean([p['candidates_per_second'] for p in per])))
    return result


def tune_shift(songs, scores):
    # One global validation-only calibration; never optimize test-song offsets.
    return max(np.arange(-.05, .0501, .005), key=lambda shift: (
        np.mean([matched(s['reference'], events(score, s['duration'], 8, shift), .02)/len(s['reference'])
                 for s, score in zip(songs, scores)]), -abs(shift)))


def main():
    started = time.time()
    rows = inventory()
    save('protocol.json', dict(version=1, script_sha256=sha(Path(__file__)), seeds=SEEDS,
        rows=rows, split='SHA256 sorted song IDs, 60/20/20; no test-label tuning',
        supervision='Pairwise ranking: chart Tap/Hold heads versus nearby jittered frames. Uncharted times are not acoustic-negative labels.',
        objective='Chart-head timing coverage at fixed candidate budgets, not full transcription or note selection.',
        sample_rate=SR, hop=HOP, fft=FFT, context_radius_frames=CONTEXT,
        epochs=40, examples_per_epoch=4096, batches=8, learning_rate=.001,
        checkpoint_rule='Final fixed epoch; no test-based selection',
        budgets=BUDGETS, scope='Available local audio is a difficulty-biased convenience sample; song-disjoint, not composer-disjoint.'))
    songs = []
    for i, row in enumerate(rows):
        print('FEATURES', i+1, len(rows), row['title'], row['split'], flush=True)
        x, flux, duration = features(row)
        ref = references(row)
        outside = int(np.sum((ref < 0) | (ref > duration)))
        ref = ref[(ref >= 0) & (ref <= duration)]
        songs.append(dict(row=row, x=x, flux=flux, duration=duration, reference=ref, excluded_outside=outside))
    train = [s for s in songs if s['row']['split']=='train']
    val = [s for s in songs if s['row']['split']=='validation']
    test = [s for s in songs if s['row']['split']=='test']
    for s in train: s['pairs'] = pairs(s)
    save('dataset.json', [dict(**s['row'], duration=s['duration'], unique_tap_hold_heads=len(s['reference']),
                              excluded_outside=s['excluded_outside'], training_pairs=len(s['pairs'][0]) if 'pairs' in s else 0) for s in songs])
    valflux = [s['flux'] for s in val]
    shift = tune_shift(val, valflux)
    results = dict(baseline=dict(shift_seconds=float(shift), test=report(test, [s['flux'] for s in test], shift)), models=[])
    for seed in SEEDS:
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        net = model()
        optimizer = torch.optim.Adam(net.parameters(), lr=.001)
        losses = []
        for epoch in range(40):
            batchloss = []
            for _ in range(8):
                pos, neg = [], []
                for sid in rng.integers(0, len(train), 16):
                    s = train[sid]; a, b = s['pairs']
                    ix = rng.integers(0, len(a), 32)
                    pos.append(context(s['x'], a[ix])); neg.append(context(s['x'], b[ix]))
                p, n = torch.from_numpy(np.concatenate(pos)), torch.from_numpy(np.concatenate(neg))
                loss = torch.nn.functional.softplus(-(net(p)-net(n))).mean()
                optimizer.zero_grad(); loss.backward(); optimizer.step()
                batchloss.append(loss.item())
            losses.append(float(np.mean(batchloss)))
            if epoch % 10 == 9: print('TRAIN', seed, epoch+1, losses[-1], flush=True)
        torch.save(net.state_dict(), OUT/f'model-{seed}.pt')
        vs = [predict(net, s) for s in val]
        delta = tune_shift(val, vs)
        ts = [predict(net, s) for s in test]
        # Repeat inference with different batch partition, on a test clip.
        clip = test[0]
        indices = np.arange(min(400, len(clip['x'])))
        with torch.no_grad():
            repeated = net(torch.from_numpy(context(clip['x'], indices))).numpy().ravel()
        entry = dict(seed=seed, parameters=sum(p.numel() for p in net.parameters()),
            shift_seconds=float(delta), losses=losses,
            inference_repeat_max_score_difference=float(np.max(abs(repeated-ts[0][:len(indices)]))),
            validation=report(val, vs, delta), test=report(test, ts, delta))
        results['models'].append(entry)
        save(f'test-events-{seed}.json', [dict(id=s['row']['id'], events_seconds=events(score, s['duration'], 8, delta).tolist()) for s,score in zip(test, ts)])
        print('RESULT', seed, json.dumps(entry['test']['8']['macro_coverage']), flush=True)
    results['elapsed_seconds'] = time.time()-started
    save('results.json', results)
    print('DONE', results['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
