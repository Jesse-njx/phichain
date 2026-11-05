"""Verify frozen-candidate evaluation and audit gain/repeat stability."""
import json
import run

np, torch = run.np, run.torch


def flux_pipeline(y, shift_ms):
    p=run.pilot
    s=np.abs(p.librosa.stft(y,n_fft=p.FFT,hop_length=p.HOP))
    mel=p.librosa.feature.melspectrogram(S=s*s,sr=p.SR,n_fft=p.FFT,n_mels=32)
    log=np.log(np.maximum(mel,1e-8)).T
    flux=np.maximum(np.diff(log,axis=0,prepend=log[:1]),0).mean(1)
    base=p.events(flux,len(y)/p.SR,8)
    ix=np.rint(base/p.STEP).astype(int)
    left,mid,right=flux[np.maximum(0,ix-1)],flux[ix],flux[np.minimum(len(flux)-1,ix+1)]
    den=left-2*mid+right
    fraction=np.divide(.5*(left-right),den,out=np.zeros_like(den),where=abs(den)>1e-9)
    offset=np.clip(fraction,-.5,.5)*p.STEP+shift_ms/1000
    return run.constrain(dict(base=base,duration=len(y)/p.SR),offset)


def main():
    protocol=json.loads((run.HERE/'protocol.json').read_text())
    selection=json.loads((run.HERE/'selection.json').read_text())
    results=json.loads((run.HERE/'results.json').read_text())['partitions']
    events=json.loads((run.HERE/'events.json').read_text())
    assert protocol['script_sha256']==run.pilot.sha(run.Path(run.__file__))
    assert protocol['previous_script_sha256']==run.pilot.sha(run.OLD/'run.py')
    for partition,methods in events.items():
        for name,rows in methods.items():
            for original,after in zip(methods['raw'],rows):
                a,b=np.array(original['times']),np.array(after['times'])
                assert original['id']==after['id'] and len(a)==len(b)
                assert np.all(np.diff(b)>0)
                assert np.max(abs(a-b))<=.0250001
    # The stronger simple method already wins on validation, without fresh labels.
    winner=max(selection,key=lambda k:selection[k]['validation']['macro_coverage']['10'])
    assert winner=='parabolic'
    rng=np.random.default_rng(20261103)
    comparison={}
    for partition in ('regression','fresh_test'):
        base=results[partition]['raw']['songs']; refined=results[partition]['parabolic']['songs']
        comparison[partition]={}
        for tol in ['5','10','20','35']:
            delta=np.array([b['coverage'][tol]-a['coverage'][tol] for a,b in zip(base,refined)])
            sampled=delta[rng.integers(0,len(delta),(10000,len(delta)))].mean(1)
            comparison[partition][tol]=dict(mean_difference_pp=float(100*delta.mean()),
                songs_improved=int(sum(delta>0)),songs=len(delta),
                exploratory_bootstrap_95_interval_pp=(100*np.percentile(sampled,[2.5,97.5])).tolist())
    row=next(r for r in protocol['rows'] if r['split']=='validation')
    song=run.load_song(row)
    y=run.decode(row)
    baseline=flux_pipeline(y,selection['parabolic']['shift_ms'])
    repeat=flux_pipeline(y,selection['parabolic']['shift_ms'])
    assert np.array_equal(baseline,repeat)
    gains={}
    for gain in [.5,2.]:
        pred=flux_pipeline(y*gain,selection['parabolic']['shift_ms'])
        gains[str(gain)]=dict(original_count=len(baseline),transformed_count=len(pred),
            matched_within_1ms=run.pilot.matched(baseline,pred,.001),
            fraction_matched_within_1ms=run.pilot.matched(baseline,pred,.001)/len(baseline))
    seed_repeat={}
    for seed in run.SEEDS:
        net=run.Refiner();net.load_state_dict(torch.load(run.HERE/f'refiner-{seed}.pt',weights_only=True));net.eval()
        first=run.predict(net,song)
        second=run.predict(net,song)
        assert np.array_equal(first,second)
        seed_repeat[str(seed)]=float(np.max(abs(first-second)))
    # Small synthetic identity/midpoint guard check, independent of chart labels.
    dummy=dict(base=np.array([.1,.14,.2]),duration=.3)
    constrained=run.constrain(dummy,np.array([1.,-1.,1.]))
    assert np.all(np.diff(constrained)>0) and len(constrained)==3
    result=dict(checks='Passed: frozen script hashes, identical event IDs/counts, strict event order, 25ms bound, midpoint guard, repeat inference.',
        validation_selected_winner=winner,comparison=comparison,
        stability_song=dict(id=row['id'],scope='One validation song; full flux+interpolation pipeline, no new label use'),
        gain_tests=gains,parabolic_repeat_exact=True,cnn_repeat_max_difference_seconds=seed_repeat,
        limitations=['Only six fresh test songs','Chart-alignment labels, not verified acoustic onset truth',
                    'Gain tested on one song; encoding and chunk/padding invariance not established',
                    'Global event budget depends on audio duration, unsuitable as a final production discovery rule'])
    run.save('audit.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
