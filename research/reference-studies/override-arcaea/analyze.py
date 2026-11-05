from pathlib import Path
import re,json,csv,collections,bisect,hashlib
R=Path(__file__).resolve().parent
P=Path('/Users/jesse/Projects/PhiChain/phichain')
override=P/'../research/music-flow-study/override-in15/chart.json'
before=hashlib.sha256(override.read_bytes()).hexdigest()
B=60000/204
allrows={};summaries={}
for difficulty in ['future','eternal']:
 text=(R/(difficulty+'.aff')).read_text();rows=[];arcs=[];unparsed=[]
 def add(t,k,line,end=None,detail=''):
  rows.append({'time_ms':int(t),'time_seconds':int(t)/1000,'beat':round(int(t)/B,6),'kind':k,'end_ms':int(end) if end is not None else '', 'source_line':line,'detail':detail})
 for lineno,s in enumerate(text.splitlines(),1):
  if re.fullmatch(r'\(\d+,\d+\);',s):
   t,lane=map(int,re.findall(r'\d+',s));add(t,'floor_tap',lineno,detail='lane '+str(lane))
  elif s.startswith('hold('):
   t,e,lane=map(int,re.findall(r'\d+',s));add(t,'hold_start',lineno,e,'lane '+str(lane))
  elif s.startswith('arc('):
   a=s[s.index('(')+1:s.index(')')].split(',');t,e=int(a[0]),int(a[1]);trace=a[9]=='true';color=a[7]
   if not trace:arcs.append((t,e,float(a[2]),float(a[3]),float(a[5]),float(a[6]),color,lineno))
   else:add(t,'trace_segment',lineno,e,'visual path, not a playable onset')
   for tap in re.findall(r'arctap\((\d+)\)',s):add(tap,'sky_tap',lineno,detail='parent arc at '+str(t))
  elif not(s.startswith(('AudioOffset:','timing(')) or s in ['-','']):unparsed.append([lineno,s])
 assert not unparsed,unparsed
 for t,e,x,xe,y,ye,c,line in arcs:
  connected=any(abs(pe-t)<=1 and abs(pxe-x)<.001 and abs(pye-y)<.001 and pc==c and pt<t for pt,pe,px,pxe,py,pye,pc,pl in arcs)
  add(t,'arc_continuation' if connected else 'arc_start',line,e,'color '+c)
 rows.sort(key=lambda r:(r['time_ms'],r['source_line'],r['kind']))
 with (R/(difficulty+'-events.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 discrete=[r for r in rows if r['kind'] in ['floor_tap','hold_start','sky_tap']]
 ts=sorted(set(r['time_ms'] for r in discrete));hist=collections.Counter(b-a for a,b in zip(ts,ts[1:]));grid=collections.Counter()
 for r in discrete:
  for denom in [1,2,4,8,3,6,12,16]:
   if abs(r['time_ms']-round(r['time_ms']/B*denom)*B/denom)<=1.1:grid[str(denom)]+=1;break
  else:grid['off_grid']+=1
 counts=collections.Counter(r['kind'] for r in rows)
 summaries[difficulty]={'event_counts':dict(counts),'discrete_attacks':len(discrete),'unique_discrete_times':len(ts),'first_ms':min(r['time_ms'] for r in discrete),'last_ms':max(int(r['end_ms'] or r['time_ms']) for r in rows),'ioi_ms_histogram':dict(hist.most_common()),'coarsest_grid_denominator_counts_tolerance_1_1ms':dict(grid),'eight_beat_phrases':[{'start_beat':b,'end_beat':b+8,'counts':dict(collections.Counter(r['kind'] for r in rows if b*B-1<=r['time_ms']<(b+8)*B-1 and r['kind']!='trace_segment'))} for b in range(0,472,8)]}
 allrows[difficulty]=rows
# Compare discrete authored attack times, independent of lane or object type. Allow integer-ms rounding.
def discrete_set(rows):return sorted(set(r['time_ms'] for r in rows if r['kind'] in ['floor_tap','hold_start','sky_tap']))
f=discrete_set(allrows['future']);e=discrete_set(allrows['eternal'])
def near(t,arr):
 i=bisect.bisect_left(arr,t);return any(abs(t-v)<=1 for v in arr[max(0,i-1):i+1])
comparison={'shared_future_times':sum(near(t,e) for t in f),'future_only_ms':[t for t in f if not near(t,e)],'eternal_only_ms':[t for t in e if not near(t,f)],'time_match_tolerance_ms':1}
with (R/'timing-comparison.csv').open('w') as out:
 w=csv.writer(out);w.writerow(['time_ms','seconds','beat_at_204','future_attacks','eternal_attacks'])
 groups=[]
 for t in sorted(set(f+e)):
  if groups and t-groups[-1][0]<=1:groups[-1].append(t)
  else:groups.append([t])
 for g in groups:
  t=g[0];a=['%s(%s)'%(r['kind'],r['detail']) for r in allrows['future'] if r['time_ms'] in g and r['kind'] in ['floor_tap','hold_start','sky_tap']];b=['%s(%s)'%(r['kind'],r['detail']) for r in allrows['eternal'] if r['time_ms'] in g and r['kind'] in ['floor_tap','hold_start','sky_tap']]
  w.writerow([t,t/1000,round(t/B,6),'; '.join(a),'; '.join(b)])
result={'bpm':204,'audio_offset_ms':0,'source_timing_origin':'AFF file; not yet aligned to local MP3','summary':summaries,'comparison':comparison,'arc_chain_rule':'Geometrically matching same-color segments with end/start times within1ms. Derived chain starts, not independently verified game judgements. All raw segments retained in CSV.','count_warning':'AFF object/attack counts are NOT combo counts. Sustained scoring ticks omitted deliberately.','override_sha256_unchanged':before}
(R/'metrics.json').write_text(json.dumps(result,indent=2))
assert hashlib.sha256(override.read_bytes()).hexdigest()==before
for k,v in summaries.items():print(k,{x:y for x,y in v.items() if x!='eight_beat_phrases'})
print('shared',comparison['shared_future_times'],'future-only',len(comparison['future_only_ms']),'eternal-only',len(comparison['eternal_only_ms']));print('eternal-only first',comparison['eternal_only_ms'][:25])
