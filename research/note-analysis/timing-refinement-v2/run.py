"""Frozen-candidate audio timing refinement, separate from event selection."""
import importlib.util
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'timing-pilot'
spec = importlib.util.spec_from_file_location('pilot', OLD/'run.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
np, torch, nn, librosa = pilot.np, pilot.torch, pilot.nn, pilot.librosa
SR, HOP, RADIUS, LIMIT = 22050, 110, 16, .025
STEP = HOP/SR
SEEDS = [17,29]


def save(name, obj):
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))


def rows():
    old = json.loads((OLD/'protocol.json').read_text())['rows']
    for r in old:
        if r['split']=='test': r['split']='regression'
    catalog = {r['song_id']:r for r in json.loads((pilot.ROOT/'local/arrangement-training/manifest.json').read_text())}
    supplemental = json.loads((pilot.ROOT/'local/overnight-study/corpus/supplemental-manifest.json').read_text())
    fresh = []
    for s in supplemental:
        r=catalog[s['id']]
        if r['format_version']!=3: continue
        fresh.append(dict(id=s['id'],title=r['title'],split='fresh_test',
            chart=str(pilot.ROOT/'local/arrangement-training'/r['local_path']),chart_sha256=r['sha256'],
            audio=str(pilot.ROOT/s['music']['path']),audio_sha256=s['music']['sha256']))
    combined=old+fresh
    assert len({r['id'] for r in combined})==len(combined)
    assert len({r['audio_sha256'] for r in combined})==len(combined)
    for r in combined:
        assert pilot.sha(Path(r['chart']))==r['chart_sha256']
        assert pilot.sha(Path(r['audio']))==r['audio_sha256']
    return combined


def decode(row):
    return np.frombuffer(pilot.subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',row['audio'],
        '-ac','1','-ar',str(SR),'-f','f32le','-']),dtype='<f4').copy()


def hi_features(y):
    out=[]
    for fft in (512,1024):
        s=np.abs(librosa.stft(y,n_fft=fft,hop_length=HOP))
        m=librosa.feature.melspectrogram(S=s*s,sr=SR,n_fft=fft,n_mels=32)
        log=np.log(np.maximum(m,1e-8)).T
        delta=np.maximum(np.diff(log,axis=0,prepend=log[:1]),0)
        out.extend([(log-log.mean(0))/np.maximum(log.std(0),.5),delta/np.maximum(delta.std(0),.1)])
    return np.concatenate(out,axis=1).astype('float32')


def load_song(row):
    # Existing v1 feature caches are read-only; new songs use a separate cache.
    cache=OLD/'features'/f"{row['audio_sha256']}.npz"
    if cache.exists():
        with np.load(cache) as d: flux,duration=d['flux'],float(d['duration'])
    else:
        new=HERE/'baseline-cache'; new.mkdir(exist_ok=True)
        pilot.OUT=new
        _,flux,duration=pilot.features(row)
        pilot.OUT=OLD
    cp=HERE/'features-v1'/f"{row['audio_sha256']}.npy"
    cp.parent.mkdir(exist_ok=True)
    if not cp.exists(): np.save(cp,hi_features(decode(row)))
    x=np.load(cp)
    base=pilot.events(flux,duration,8)
    idx=np.rint(base/pilot.STEP).astype(int)
    # Quadratic interpolation of the same peaks, not a new detector.
    left,mid,right=flux[np.maximum(0,idx-1)],flux[idx],flux[np.minimum(len(flux)-1,idx+1)]
    den=left-2*mid+right
    frac=np.divide(.5*(left-right),den,out=np.zeros_like(den),where=abs(den)>1e-9)
    parab=np.clip(frac,-.5,.5)*pilot.STEP
    return dict(row=row,x=x,base=base,parab=parab,duration=duration)


def patches(song, times):
    centers=np.rint(times/STEP).astype(int)
    ix=np.clip(centers[:,None]+np.arange(-RADIUS,RADIUS+1),0,len(song['x'])-1)
    return song['x'][ix].transpose(0,2,1).copy()


def anchors(ref,base,tolerance=.035):
    # Mutual-nearest identity is fixed BEFORE correction; never rematch to make
    # the localization-error metric look better. Coverage separately uses matching.
    i=np.searchsorted(ref,base)
    a,b=np.clip(i-1,0,len(ref)-1),np.clip(i,0,len(ref)-1)
    ri=np.where(abs(base-ref[a])<=abs(base-ref[b]),a,b)
    j=np.searchsorted(base,ref)
    a,b=np.clip(j-1,0,len(base)-1),np.clip(j,0,len(base)-1)
    ci=np.where(abs(ref-base[a])<=abs(ref-base[b]),a,b)
    ids=np.arange(len(base))
    keep=(ci[ri]==ids)&(abs(base-ref[ri])<=tolerance)
    return ids[keep],ri[keep]


class Refiner(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers=nn.Sequential(nn.Conv1d(128,32,5,padding=2),nn.ReLU(),
            nn.Conv1d(32,16,5,padding=2),nn.ReLU(),nn.Flatten(),
            nn.Linear(16*33,32),nn.ReLU(),nn.Linear(32,1),nn.Tanh())
    def forward(self,x): return self.layers(x).squeeze(-1)


def predict(net,song):
    with torch.no_grad():
        return np.concatenate([net(torch.from_numpy(patches(song,song['base'][a:a+512]))).numpy()*LIMIT
                               for a in range(0,len(song['base']),512)])


def constrain(song,offset):
    base=song['base']
    # Preserve identity/count/order; each event stays in its original temporal cell.
    low=np.r_[0,(base[1:]+base[:-1])/2+.0001]
    high=np.r_[(base[1:]+base[:-1])/2-.0001,song['duration']]
    return np.clip(base+np.clip(offset,-LIMIT,LIMIT),low,high)


def evaluate(songs, offsets):
    per=[]
    for s,delta in zip(songs,offsets):
        pred=constrain(s,delta); ref=s['ref']; ci,ri=anchors(ref,s['base'])
        before=abs(s['base'][ci]-ref[ri]); after=abs(pred[ci]-ref[ri])
        per.append(dict(id=s['row']['id'],title=s['row']['title'],references=len(ref),candidates=len(pred),
            coverage={str(ms):pilot.matched(ref,pred,ms/1000)/len(ref) for ms in [5,10,20,35,50]},
            fixed_anchor_count=len(ci),fixed_anchor_median_ms=float(np.median(after)*1000),
            fixed_anchor_p90_ms=float(np.percentile(after,90)*1000),
            lost_previously_within_10ms=int(np.sum((before<=.01)&(after>.01))),
            gained_within_10ms=int(np.sum((before>.01)&(after<=.01))),
            max_adjustment_ms=float(np.max(abs(pred-s['base']))*1000)))
    return dict(songs=per,macro_coverage={str(ms):float(np.mean([r['coverage'][str(ms)] for r in per])) for ms in [5,10,20,35,50]},
        mean_song_anchor_median_ms=float(np.mean([r['fixed_anchor_median_ms'] for r in per])),
        mean_song_anchor_p90_ms=float(np.mean([r['fixed_anchor_p90_ms'] for r in per])))


def select(songs,deltas,alphas):
    base=evaluate(songs,[np.zeros(len(s['base'])) for s in songs])
    choices=[]
    for alpha in alphas:
        for ms in [-10,-7.5,-5,-2.5,0,2.5,5,7.5,10]:
            r=evaluate(songs,[alpha*d+ms/1000 for d in deltas])
            if r['macro_coverage']['35']>=base['macro_coverage']['35']-.005:
                choices.append((r['macro_coverage']['10'],r['macro_coverage']['20'],-abs(ms),-alpha,alpha,ms,r))
    best=max(choices,key=lambda v:v[:4])
    return dict(alpha=best[4],shift_ms=best[5],validation=best[6])


def main():
    start=time.time(); inventory=rows()
    save('protocol.json',dict(rows=inventory,script_sha256=pilot.sha(Path(__file__)),
        previous_script_sha256=pilot.sha(OLD/'run.py'),seeds=SEEDS,epochs=30,batches_per_epoch=8,batch_size=256,
        candidate_detector='Frozen v1 spectral flux at 8/s; same candidate IDs for every method',
        training='Only mutual-nearest chart/candidate pairs within 25 ms; smooth L1 offset regression, 5ms beta',
        features=dict(hop=HOP,ffts=[512,1024],mel_bands=32,patch_radius=RADIUS),
        selection='Final fixed epoch; validation maximize 10ms coverage, 35ms drop <=0.5pp; alpha [0,.25,.5,1], shift -10..10ms/2.5ms',
        fresh_test='Supplemental local audio, excluded from prior pilot; labels only loaded after selection.json is written',
        limits='Chart alignment proxy, incomplete acoustic labels; not an acoustic precision evaluation.'))
    songs=[]
    for i,r in enumerate(inventory):
        print('FEATURES',i+1,len(inventory),r['title'],flush=True)
        s=load_song(r)
        if r['split'] in ('train','validation'): s['ref']=pilot.references(r)
        songs.append(s)
    train=[s for s in songs if s['row']['split']=='train']
    val=[s for s in songs if s['row']['split']=='validation']
    for s in train:
        ci,ri=anchors(s['ref'],s['base'],LIMIT)
        s['train_x']=patches(s,s['base'][ci])
        s['train_y']=((s['ref'][ri]-s['base'][ci])/LIMIT).astype('float32')
    save('training-data.json',[dict(id=s['row']['id'],pairs=len(s['train_y'])) for s in train])
    nets=[]; selection={}
    selection['global_shift']=select(val,[np.zeros(len(s['base'])) for s in val],[0])
    selection['parabolic']=select(val,[s['parab'] for s in val],[1])
    for seed in SEEDS:
        torch.manual_seed(seed); rng=np.random.default_rng(seed)
        net=Refiner(); opt=torch.optim.Adam(net.parameters(),lr=.001)
        losses=[]
        for epoch in range(30):
            batchloss=[]
            for _ in range(8):
                xx,yy=[],[]
                for sid in rng.integers(0,len(train),8):
                    s=train[sid]; ix=rng.integers(0,len(s['train_y']),32)
                    xx.append(s['train_x'][ix]); yy.append(s['train_y'][ix])
                x,y=torch.from_numpy(np.concatenate(xx)),torch.from_numpy(np.concatenate(yy))
                loss=torch.nn.functional.smooth_l1_loss(net(x),y,beta=.2)
                opt.zero_grad(); loss.backward(); opt.step(); batchloss.append(loss.item())
            losses.append(float(np.mean(batchloss)))
            if epoch%10==9: print('TRAIN',seed,epoch+1,losses[-1],flush=True)
        torch.save(net.state_dict(),HERE/f'refiner-{seed}.pt')
        choice=select(val,[predict(net,s) for s in val],[0,.25,.5,1])
        choice.update(losses=losses,parameters=sum(p.numel() for p in net.parameters()))
        selection[f'cnn_{seed}']=choice; nets.append(net)
        print('SELECT',seed,choice['alpha'],choice['shift_ms'],choice['validation']['macro_coverage'],flush=True)
    save('selection.json',selection)
    # No architecture/parameter change is allowed after this evaluation point.
    results={}; event_rows={}
    for split in ['validation','regression','fresh_test']:
        ss=[s for s in songs if s['row']['split']==split]
        for s in ss:
            if 'ref' not in s: s['ref']=pilot.references(s['row'])
        methods=dict(raw=[np.zeros(len(s['base'])) for s in ss],global_shift=[np.zeros(len(s['base'])) for s in ss],parabolic=[s['parab'] for s in ss])
        methods.update({f'cnn_{seed}':[predict(net,s) for s in ss] for seed,net in zip(SEEDS,nets)})
        results[split]={}
        event_rows[split]={}
        for method,ds in methods.items():
            if method!='raw':
                choice=selection[method]; ds=[choice['alpha']*d+choice['shift_ms']/1000 for d in ds]
            results[split][method]=evaluate(ss,ds)
            event_rows[split][method]=[dict(id=s['row']['id'],times=constrain(s,d).tolist()) for s,d in zip(ss,ds)]
        print('EVAL',split,{k:v['macro_coverage'] for k,v in results[split].items()},flush=True)
    save('events.json',event_rows)
    save('results.json',dict(elapsed_seconds=time.time()-start,partitions=results))
    print('DONE',time.time()-start,flush=True)


if __name__=='__main__': main()
