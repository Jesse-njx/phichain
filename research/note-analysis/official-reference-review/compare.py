"""Read-only official reference audit; no editor, chart writes, or HTML reports."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/Users/jesse/Projects/PhiChain/phichain')
OUT = Path(__file__).parent
os.environ.setdefault('NUMBA_CACHE_DIR', '/private/tmp/phichain-music-numba')
sys.path.insert(0, str(ROOT/'tools/music-analysis'))
import analyze
import numpy as np

KIND = {1:'tap', 2:'drag', 3:'hold', 4:'flick'}


def decode_notes(path):
    chart = json.loads(path.read_text())
    rows = []
    for index, line in enumerate(chart['judgeLineList']):
        for side in ['notesAbove', 'notesBelow']:
            for n in line[side]:
                scale = 60 / 32 / line['bpm']
                t = n['time'] * scale + chart.get('offset', 0)
                rows.append({'time':t, 'end': t + n['holdTime'] * scale,
                             'kind':KIND[n['type']], 'line':index, 'source_ticks':n['time'], 'bpm':line['bpm']})
    return chart, sorted(rows, key=lambda r:(r['time'],r['line'],r['kind']))


def unique(values):
    return np.array(sorted(set(round(float(t), 6) for t in values)))


def match(reference, predicted, tolerance):
    # Earliest compatible pairing maximizes ordered one-to-one cardinality.
    i = j = 0
    pairs = []
    while i < len(reference) and j < len(predicted):
        if predicted[j] < reference[i] - tolerance:
            j += 1
        elif predicted[j] > reference[i] + tolerance:
            i += 1
        else:
            pairs.append((i,j)); i += 1; j += 1
    return {'matches':len(pairs), 'reference_count':len(reference), 'predicted_count':len(predicted),
            'reference_covered':len(pairs)/max(1,len(reference)),
            'prediction_matched':len(pairs)/max(1,len(predicted))}


def structure(rows):
    attack = unique(r['time'] for r in rows if r['kind'] in ('tap','hold'))
    all_heads = unique(r['time'] for r in rows)
    ends = [r['end'] for r in rows]
    gaps = sorted(zip(attack[:-1],attack[1:]),key=lambda pair:pair[1]-pair[0],reverse=True)[:8]
    gap_data = []
    for a,b in gaps:
        holds = [r for r in rows if r['kind']=='hold' and r['end']>a+.01 and r['time']<b]
        other = [r for r in rows if a+.00001<r['time']<b-.00001 and r['kind'] in ('drag','flick')]
        gap_data.append({'from':float(a),'to':float(b),'length':float(b-a),
                         'overlapping_holds':len(holds),'intervening_drag_flick':len(other)})
    return {'objects':len(rows),'types':dict(collections.Counter(r['kind'] for r in rows)),
            'unique_all_heads':len(all_heads),'unique_tap_hold_heads':len(attack),
            'simultaneous_object_groups':sum(v>1 for v in collections.Counter(round(r['time'],6) for r in rows).values()),
            'tap_hold_intervals_ms':dict(collections.Counter(round(x*1000,3) for x in np.diff(attack)).most_common(12)),
            'largest_tap_hold_gaps':gap_data,'end_seconds':max(ends)}


def main():
    manifest=json.loads((ROOT/'../research/overnight-study/corpus/manifest.json').read_text())
    wanted=['Verruckt.Raimukun','RetributionCycleofRedemption.ArdolfvsDaily天利','StardustRAY.kanonevsBlackY']
    results=[]
    for song_id in wanted:
        row=next(r for r in manifest if r['id']==song_id and r['difficulty']=='IN')
        chart_path=ROOT/row['chart']['path']; audio_path=ROOT/row['music']['path']
        for path,expected in [(chart_path,row['chart']['sha256']),(audio_path,row['music']['sha256'])]:
            assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
        print('ANALYZING',row['title'],flush=True)
        chart,notes=decode_notes(chart_path)
        slug=next(s for s in ['Verruckt','RetributionCycle','StardustRAY'] if song_id.startswith(s))
        cache=OUT/(slug+'-detector.json')
        if cache.exists():
            detected=json.loads(cache.read_text())
        else:
            y=np.frombuffer(subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(audio_path),'-ac','1','-ar',str(analyze.SR),'-f','f32le','-']),dtype='<f4').copy()
            features=analyze.extract(y,progress=lambda x:print(slug,x,flush=True))
            sections,climax,timeline,curve=analyze.structure(features,len(y)/analyze.SR)
            decisions=analyze.decide(features,sections,curve,len(y)/analyze.SR)
            detected={'source_audio_sha256':row['music']['sha256'],'duration':len(y)/analyze.SR,
                      'analyzer_source_sha256':analyze.digest(ROOT/'tools/music-analysis/analyze.py'),
                      'decisions':decisions,'timeline':timeline}
            cache.write_text(json.dumps(detected,ensure_ascii=False,indent=2))
        assert detected['source_audio_sha256']==row['music']['sha256']
        assert detected['analyzer_source_sha256']==analyze.digest(ROOT/'tools/music-analysis/analyze.py')
        all_candidates=unique(n['time_seconds'] for n in detected['decisions'])
        selected=unique(n['time_seconds'] for n in detected['decisions'] if n['selected'])
        fresh=unique(n['time'] for n in notes if n['kind'] in ('tap','hold'))
        all_heads=unique(n['time'] for n in notes)
        groups={key:unique(n['time'] for n in notes if n['kind']==key) for key in KIND.values()}
        sensitivity={str(ms):{'fresh_vs_selected':match(fresh,selected,ms/1000),
                              'all_heads_vs_selected':match(all_heads,selected,ms/1000),
                              'fresh_vs_candidates':match(fresh,all_candidates,ms/1000),
                              'by_type_selected':{key:match(value,selected,ms/1000) for key,value in groups.items()}}
                     for ms in [20,35,50]}
        # Diagnose possible global delay, report it, but never retime the reference.
        offset_scan=[{'delta_ms':int(delta),'matches':match(fresh,selected+delta/1000,.02)['matches']} for delta in range(-80,81,2)]
        best=max(offset_scan,key=lambda row:(row['matches'],-abs(row['delta_ms'])))
        windows=[]
        for start in np.arange(0,detected['duration'],4):
            end=min(start+4,detected['duration'])
            ref=[n for n in notes if start<=n['time']<end]
            ours=[n for n in detected['decisions'] if n['selected'] and start<=n['time_seconds']<end]
            tail_coverage=sum(max(0,min(end,n['end'])-max(start,n['time'])) for n in notes if n['kind']=='hold')
            windows.append({'from':float(start),'to':float(end),'official_objects':len(ref),
                            'official_types':dict(collections.Counter(n['kind'] for n in ref)),
                            'official_fresh_times':len(unique(n['time'] for n in ref if n['kind'] in ('tap','hold'))),
                            'detector_selected':len(ours),'detector_holds':sum(n['suggested_type']=='hold' for n in ours),
                            'official_hold_contact_seconds':tail_coverage,
                            'mean_acoustic_intensity':float(np.mean([r['intensity'] for r in detected['timeline'] if start<=r['seconds']<end]))})
        examples={}
        ranges={'Verruckt':[(43.55,44.55),(49.4,50.4)],'RetributionCycle':[(11.05,12.85),(132,136)],'StardustRAY':[(80,84),(120,124)]}
        for start,end in ranges[slug]:
            examples[f'{start}-{end}']={'official':[n for n in notes if start<=n['time']<end],
                                     'detector':[n for n in detected['decisions'] if n['selected'] and start<=n['time_seconds']<end]}
        result={'title':row['title'],'difficulty':'IN','source':{k:row[k] for k in ['chart','music']},
                'chart_offset_seconds':chart.get('offset',0),'official':structure(notes),
                'detector':{'candidates':len(all_candidates),'selected':len(selected),
                            'types':dict(collections.Counter(n['suggested_type'] for n in detected['decisions'] if n['selected']))},
                'one_to_one_sensitivity':sensitivity,'timing_diagnostic_best_shift':best,
                'timing_diagnostic_offset_scan':offset_scan,'windows':windows,'examples':examples}
        results.append(result)
        (OUT/(slug+'-comparison.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print('RESULT',json.dumps({k:result[k] for k in ['title','detector','timing_diagnostic_best_shift']},ensure_ascii=False),flush=True)
    path=ROOT/'../research/reference-studies/happy-ending-in/IN.original.json'
    _,notes=decode_notes(path)
    happy={'title':'What do you want more than a Happy ending?','source_path':str(path),
           'sha256':analyze.digest(path),'scope':'Chart timing/type structure only; no matching audio located in this study',
           'structure':structure(notes),'windows':{f'{a}-{b}':[n for n in notes if a<=n['time']<b] for a,b in [(60,70),(80,90)]}}
    (OUT/'happy-ending-structure.json').write_text(json.dumps(happy,ensure_ascii=False,indent=2))
    (OUT/'summary.json').write_text(json.dumps({'scope':'Reference agreement is a diagnostic, not a chart quality score. All times are decoded audio seconds with declared source offset. Only one-to-one unique-time matches count. No model tuning, manual-line recovery, chart edits or user listening validation.',
                    'songs':[{k:r[k] for k in ['title','official','detector','one_to_one_sensitivity','timing_diagnostic_best_shift']} for r in results],
                    'happy_ending':{k:happy[k] for k in ['title','scope','structure']}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
