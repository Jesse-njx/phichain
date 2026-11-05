"""Extract source-time rhythm evidence, preserving visual timing separately."""
from pathlib import Path
import collections, csv, hashlib, json, re
R = Path(__file__).resolve().parent
text = (R/'eternal.aff').read_text()
rows, timings, arcs = [], [], []
noinput = False
unknown = []
for line, raw in enumerate(text.splitlines(), 1):
    s = raw.strip()
    if s.startswith('timinggroup('):
        noinput = 'noinput' in s
        continue
    if s == '};':
        noinput = False
        continue
    if s.startswith('timing('):
        a = s[7:s.index(')')].split(',')
        timings.append({'time_ms':int(a[0]), 'bpm_parameter':float(a[1]), 'beats_parameter':float(a[2]), 'noinput':noinput, 'source_line':line})
        continue
    def add(t, kind, end='', detail=''):
        rows.append({'time_ms':int(t), 'time_seconds':int(t)/1000, 'kind':kind, 'end_ms':end, 'noinput':noinput, 'source_line':line, 'detail':detail})
    m = re.fullmatch(r'\((\d+),(\d+)\);',s)
    if m:
        add(m[1],'floor_tap',detail='lane '+m[2])
    elif s.startswith('hold('):
        t,e,lane = map(int,re.findall(r'\d+',s))
        add(t,'hold_start',e,'lane '+str(lane))
    elif s.startswith('arc('):
        a = s[4:s.index(')')].split(',')
        t,e = int(a[0]),int(a[1])
        if a[9] == 'true':
            add(t,'trace_segment',e,'visual carrier')
        else:
            arcs.append((t,e,float(a[2]),float(a[3]),float(a[5]),float(a[6]),a[7],noinput,line))
        for tap in re.findall(r'arctap\((\d+)\)',s):
            add(tap,'sky_tap',detail='parent arc '+str(t))
    elif not (s in ('','-') or s.startswith('AudioOffset:')):
        unknown.append([line,s])
assert not unknown, unknown
for t,e,x,xe,y,ye,c,ni,line in arcs:
    connected = any(abs(pe-t)<=1 and abs(pxe-x)<.001 and abs(pye-y)<.001 and pc==c and pni==ni and pt<t for pt,pe,px,pxe,py,pye,pc,pni,pl in arcs)
    rows.append({'time_ms':t,'time_seconds':t/1000,'kind':'arc_continuation' if connected else 'arc_start','end_ms':e,'noinput':ni,'source_line':line,'detail':'color '+c})
rows.sort(key=lambda r:(r['time_ms'],r['source_line'],r['kind']))
for filename, data in [('eternal-events.csv',rows),('timing-events.csv',timings)]:
    with (R/filename).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
playable = [r for r in rows if not r['noinput'] and r['kind'] != 'trace_segment']
attacks = [r for r in playable if r['kind'] != 'arc_continuation']
discrete = [r for r in attacks if r['kind'] != 'arc_start']
times = sorted(set(r['time_ms'] for r in attacks))
intervals = collections.Counter(b-a for a,b in zip(times,times[1:]))
sections=[]
# Timing-evidence boundaries; not asserted as musical phrase labels.
bounds=[0,4687,15937,59062,75937,83321,110264,131826,132767,133701,168000]
for a,b in zip(bounds,bounds[1:]):
    subset=[r for r in attacks if a<=r['time_ms']<b]
    sections.append({'start_seconds':a/1000,'end_seconds':b/1000,'attack_counts':dict(collections.Counter(r['kind'] for r in subset)),'unique_attack_times':len(set(r['time_ms'] for r in subset))})
metrics={'source_audio_offset_ms':int(re.search(r'AudioOffset:(-?\d+)',text)[1]),'event_counts_excluding_noinput':dict(collections.Counter(r['kind'] for r in playable)),'discrete_attacks':len(discrete),'unique_attack_times_including_arc_chain_starts':len(times),'first_attack_ms':times[0],'last_playable_end_ms':max(int(r['end_ms'] or r['time_ms']) for r in playable),'frequent_attack_intervals_ms':intervals.most_common(20),'timing_evidence_sections':sections,'limitations':['Source times have not yet been aligned with the local MP3.','AFF timing parameters govern scroll speed as well as musical tempo; zero/extreme values are visual effects.','Arc chains are inferred from matching same-color endpoints within 1 ms; not verified game combo ticks.','Object and attack counts are not combo counts; sustained scoring ticks are omitted.','No-input group objects are excluded from playable counts.','Full numerical chart inspection is not full synchronized listening or gameplay review.']}
(R/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
songs=json.loads((R.parent/'override-arcaea/songlist.json').read_text())['songs']
metadata=next(s for s in songs if s['id']=='xterfusion')
(R/'song-metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
revision='4c26fcc30b741feeef373f375a900db1d60d76ee'
source={'repository':'https://github.com/HarumiEna/Arcaea-AFF','revision':revision,'downloaded':'2026-11-01','difficulty':'Eternal','ratingClass':4,'files':[{'file':'eternal.aff','url':f'https://raw.githubusercontent.com/HarumiEna/Arcaea-AFF/{revision}/songs/xterfusion/xterfusion_4.aff','sha256':hashlib.sha256((R/'eternal.aff').read_bytes()).hexdigest()}],'metadata_source':f'https://raw.githubusercontent.com/HarumiEna/Arcaea-AFF/{revision}/songlist/songlist','authenticity':'Community mirror; not byte-checked against an installed official game.'}
(R/'source.json').write_text(json.dumps(source,indent=2)+'\n')
print(json.dumps(metrics,indent=2))
