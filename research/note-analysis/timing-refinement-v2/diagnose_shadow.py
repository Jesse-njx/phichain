"""Post-test exploratory diagnosis; never changes the frozen benchmark or events."""
import json
import run
from audit import flux_pipeline

np=run.np


def main():
    rows=json.loads((run.HERE/'protocol.json').read_text())['rows']
    ev=json.loads((run.HERE/'events.json').read_text())['fresh_test']['parabolic']
    times={r['id']:np.array(r['times']) for r in ev}
    output=dict(scope='Post-test exploratory analysis prompted by user: Shadow is quiet. Any tuned shift below is oracle diagnostic only, not applied or validated.',songs=[])
    for row in rows:
        if row['split']!='fresh_test':continue
        y=run.decode(row);ref=run.pilot.references(row);pred=times[row['id']]
        rms=run.librosa.feature.rms(y=y,frame_length=1024,hop_length=220)[0]
        db=20*np.log10(np.maximum(rms,1e-9))
        energy=db[np.clip(np.rint(ref/run.pilot.STEP).astype(int),0,len(db)-1)]
        ci,ri=run.anchors(ref,pred,.035)
        error=(pred[ci]-ref[ri])*1000
        item=dict(id=row['id'],title=row['title'],rms_dbfs_percentiles=np.percentile(db,[10,50,90]).tolist(),
            peak_dbfs=float(20*np.log10(max(abs(y).max(),1e-9))),
            fixed_near_pairs=len(ci),signed_error_ms_percentiles=np.percentile(error,[10,50,90]).tolist(),
            coverage={str(ms):run.pilot.matched(ref,pred,ms/1000)/len(ref) for ms in [10,20,35]},
            loudness_quartiles=[])
        order=np.argsort(energy,kind='stable')
        for ids in np.array_split(order,4):
            rr=np.sort(ref[ids]); mask=np.isin(ri,ids)
            item['loudness_quartiles'].append(dict(heads=len(rr),median_rms_dbfs=float(np.median(energy[ids])),
                coverage_10ms=run.pilot.matched(rr,pred,.01)/len(rr),
                signed_error_median_ms=float(np.median(error[mask])) if mask.any() else None))
        if row['id'].startswith('Shadow.'):
            scan=[dict(shift_ms=ms,coverage_10ms=run.pilot.matched(ref,pred+ms/1000,.01)/len(ref)) for ms in range(-30,31)]
            item['oracle_shift_scan']=scan
            item['oracle_best_shift']=max(scan,key=lambda r:(r['coverage_10ms'],-abs(r['shift_ms'])))
            item['windows']=[]
            for start in np.arange(0,len(y)/run.SR,15):
                mask=(ref[ri]>=start)&(ref[ri]<start+15)
                if mask.any(): item['windows'].append(dict(start_seconds=float(start),pairs=int(mask.sum()),signed_error_median_ms=float(np.median(error[mask]))))
            boosted=flux_pipeline(y*4,0)
            item['gain4_no_clipping']=dict(coverage_10ms=run.pilot.matched(ref,boosted,.01)/len(ref),
                candidates=len(boosted),original_candidates=len(pred),
                unchanged_within_1ms=run.pilot.matched(pred,boosted,.001)/len(pred))
        output['songs'].append(item)
    run.save('shadow-diagnostic.json',output)
    for r in output['songs']:
        print(r['title'],'RMS p10/50/90',r['rms_dbfs_percentiles'],'signed error p10/50/90',r['signed_error_ms_percentiles'])
        if r['id'].startswith('Shadow.'):
            print(json.dumps({k:r[k] for k in ['loudness_quartiles','windows','oracle_best_shift','gain4_no_clipping']},indent=2))


if __name__=='__main__': main()
