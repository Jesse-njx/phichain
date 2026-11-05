"""Train/evaluate on song-disjoint data; checkpoints are local research artifacts."""
import argparse
import collections
import gzip
import hashlib
import json
import math
import pathlib
import platform
import time
import numpy as np
import torch
import torch.nn.functional as F
from masked_model import ArrangementTransformer, MODEL_CONFIG, batch, generate

ROOT = pathlib.Path(__file__).resolve().parent


def write_json(path, obj):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def evaluate(model, windows, device, mode, baseline=None):
    model.eval(); rng = np.random.default_rng(123456)
    total_loss = hits = count = base_loss = 0
    with torch.no_grad():
        for start in range(0, len(windows), 32):
            f,k,x,target,mask,valid = batch(windows[start:start+32],rng,device,mode=mode)
            logits = model(f,k,x,valid)
            selected = mask & valid
            loss = F.cross_entropy(logits[selected], target[selected], reduction='sum')
            total_loss += float(loss.cpu()); count += int(selected.sum().cpu())
            hits += int((logits.argmax(-1)[selected] == target[selected]).sum().cpu())
            if baseline is not None:
                kinds = k[selected].cpu().numpy(); labels = target[selected].cpu().numpy()
                base_loss += float(-np.log(baseline[kinds, labels]).sum())
    return dict(cross_entropy=total_loss/count, exact_bin_accuracy=hits/count,
                masked_notes=count, type_frequency_baseline_cross_entropy=base_loss/count if baseline is not None else None)


def sample_audit(model, windows, device, folder):
    # Generated data is separate from originals and never written to the live editor.
    examples = []
    for index, window in enumerate(windows[:12]):
        candidates = []
        for candidate in range(3):
            positions = generate(model, window, device, seed=1000+index*3+candidate)
            out = [dict(n, x=float(px)) for n,px in zip(window['notes'], positions)]
            collisions = 0
            for i,n in enumerate(out):
                for other in out[i+1:]:
                    if other['time']-n['time'] > 1e-5:
                        break
                    if n['type'] == other['type'] == 1 and abs(n['x']-other['x']) < 2/128:
                        collisions += 1
            candidates.append(dict(notes=out, simultaneous_tap_collisions=collisions))
        examples.append(dict(id=window['id'], song_id=window['song_id'],
                             reference=window['notes'], candidates=candidates))
    write_json(folder/'heldout-generations.json', examples)
    return dict(windows=len(examples), candidates=sum(len(x['candidates']) for x in examples),
                candidates_with_tap_collisions=sum(c['simultaneous_tap_collisions']>0 for x in examples for c in x['candidates']),
                caveat='Unfiltered samples; collision count is only one failure screen. Human quality and two-finger comfort remain unverified.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=3000)
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--eval-every', type=int, default=200)
    parser.add_argument('--patience', type=int, default=7)
    parser.add_argument('--run', default='masked-v1')
    args = parser.parse_args()
    folder = ROOT/'runs'/args.run; folder.mkdir(parents=True,exist_ok=True)
    assert not (folder/'best.pt').exists(), 'Use a new run name to preserve existing checkpoints'
    assert torch.backends.mps.is_available(), 'GPU unavailable; refusing silent CPU training'
    torch.set_num_threads(4); torch.manual_seed(20261102)
    device = torch.device('mps'); rng = np.random.default_rng(20261102)
    with gzip.open(ROOT/'processed/windows.json.gz','rt') as source:
        windows = json.load(source)
    splits = {s:[w for w in windows if w['split']==s] for s in ('train','validation','test')}
    for s in splits:
        assert splits[s], 'Empty split: '+s
    ids = {s:{w['song_id'] for w in ws} for s,ws in splits.items()}
    assert not (ids['train']&ids['validation'] or ids['train']&ids['test'] or ids['validation']&ids['test'])
    counts = np.ones((5,128), dtype=np.float64)
    # Avoid over-counting overlapping windows in the baseline.
    unique = {}
    for window in splits['train']:
        for n in window['notes']:
            unique[(window['song_id'],n['id'])] = n
    for n in unique.values():
        label = int(round(n['x']*127)); counts[n['type'],label] += .5; counts[n['type'],127-label] += .5
    baseline = counts/counts.sum(axis=1,keepdims=True)
    model = ArrangementTransformer().to(device)
    parameter_count = sum(p.numel() for p in model.parameters())
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=.01, foreach=False)
    configuration = dict(model=MODEL_CONFIG, parameters=parameter_count, torch=torch.__version__, numpy=np.__version__,
                         platform=platform.platform(), device=str(device), training=vars(args), learning_rate=3e-4,
                         seed=20261102, splits={s:len(ws) for s,ws in splits.items()},
                         dataset_sha256=hashlib.sha256((ROOT/'processed/windows.json.gz').read_bytes()).hexdigest(),
                         source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('preprocess.py','masked_model.py','train.py')})
    write_json(folder/'config.json',configuration)
    print(json.dumps(configuration),flush=True)
    initial = evaluate(model,splits['validation'],device,'full',baseline)
    write_json(folder/'initial-validation.json',initial)
    started = time.monotonic(); best = float('inf'); bad = 0; losses=[]; history=[]
    for step in range(1,args.steps+1):
        model.train()
        selected = [splits['train'][int(i)] for i in rng.integers(len(splits['train']),size=args.batch_size)]
        f,k,x,target,mask,valid = batch(selected,rng,device,augment=True)
        warmup = min(1, step/100)
        rate = 3e-4*warmup*(.15+.85*.5*(1+math.cos(math.pi*step/args.steps)))
        for group in optimizer.param_groups:
            group['lr'] = rate
        optimizer.zero_grad(set_to_none=True)
        logits = model(f,k,x,valid)
        loss = F.cross_entropy(logits[mask&valid],target[mask&valid],label_smoothing=.02)
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite training loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); optimizer.step()
        losses.append(float(loss.detach().cpu()))
        if step%25 == 0:
            elapsed = time.monotonic()-started
            status = dict(status='training', step=step, max_steps=args.steps, elapsed_seconds=elapsed,
                          average_seconds_per_step=elapsed/step, estimated_remaining_seconds=elapsed/step*(args.steps-step),
                          mean_recent_loss=float(np.mean(losses[-25:])))
            write_json(folder/'status.json',status)
            print(json.dumps(status),flush=True)
        if step%args.eval_every==0 or step==args.steps:
            full = evaluate(model,splits['validation'],device,'full',baseline)
            partial = evaluate(model,splits['validation'],device,'partial',baseline)
            score = .5*(full['cross_entropy']+partial['cross_entropy'])
            entry = dict(step=step,training_loss=float(np.mean(losses[-args.eval_every:])),validation_full=full,validation_partial=partial,selection_score=score)
            history.append(entry); write_json(folder/'history.json',history)
            torch.save(dict(model=model.state_dict(),optimizer=optimizer.state_dict(),step=step,config=configuration),folder/'latest.pt')
            if score < best-1e-4:
                best=score; bad=0
                torch.save(dict(model=model.state_dict(),step=step,config=configuration),folder/'best.pt')
            else:
                bad+=1
            print('VALIDATION '+json.dumps(entry),flush=True)
            if bad>=args.patience:
                print('Early stopping on validation only',flush=True); break
    checkpoint = torch.load(folder/'best.pt',map_location='cpu',weights_only=False)
    model.load_state_dict(checkpoint['model']); model.to(device)
    result = dict(status='complete',steps_completed=step,best_step=checkpoint['step'],
                  training_and_validation_seconds=time.monotonic()-started,
                  initial_validation_full=initial,
                  test_full=evaluate(model,splits['test'],device,'full',baseline),
                  test_partial=evaluate(model,splits['test'],device,'partial',baseline),
                  samples=sample_audit(model,splits['test'],device,folder),
                  conclusion='Research baseline trained. Statistical evaluation does not establish enjoyable or reliably two-finger-playable arrangements.')
    write_json(folder/'result.json',result); write_json(folder/'status.json',result)
    print('COMPLETE '+json.dumps(result),flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
