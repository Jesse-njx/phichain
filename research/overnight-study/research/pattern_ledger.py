import pathlib,json,collections,math
P=pathlib.Path('../research/overnight-study/corpus');R=P.parent/'research';M=json.loads((P/'manifest.json').read_text());M.sort(key=lambda m:(not m['recent_three_years'],m['difficulty']!='AT'))
found=collections.defaultdict(list)
def add(kind,m,li,ns,hypothesis):
 if len(found[kind])>=2 or any(x['id']==m['id'] for x in found[kind]):return
 found[kind].append(dict(id=m['id'],title=m['title'],difficulty=m['difficulty'],line=li,start_seconds=ns[0]['seconds'],notes=[{k:n[k] for k in ['seconds','type','positionX','duration_seconds','side']} for n in ns],fingering_hypothesis=hypothesis,qualification='Decoded official source line-local arrangement; visual transformations, overlapping source lines and actual hit windows still require review. Hypothesis is not validated playability.'))
for m in M:
 d=json.loads(pathlib.Path(m['chart']['path']).read_text())
 for li,l in enumerate(d['judgeLineList']):
  ns=sorted([dict(n,seconds=n['time']*1.875/l['bpm']+d.get('offset',0),duration_seconds=n['holdTime']*1.875/l['bpm'],side=side) for side in ['notesAbove','notesBelow'] for n in l[side]],key=lambda n:n['seconds'])
  taps=[n for n in ns if n['type']==1];groups=collections.defaultdict(list)
  for n in taps:groups[round(n['seconds'],4)].append(n)
  gs=sorted(groups.items())
  for k in range(len(taps)-3):
   q=taps[k:k+4];gaps=[q[i+1]['seconds']-q[i]['seconds'] for i in range(3)];xs=[n['positionX'] for n in q]
   if all(.025<=g<=.25 for g in gaps):
    if max(gaps)-min(gaps)<.005 and abs(xs[0]-xs[2])<.05 and abs(xs[1]-xs[3])<.05 and abs(xs[0]-xs[1])>1:add('alternating_trill',m,li,q,'Alternate the two contact stations L/R if the source line shares the main playing locus. Exit ownership must consider the next object and any holds.')
    steps=[xs[i+1]-xs[i] for i in range(3)]
    if all(s>.4 for s in steps) or all(s<-.4 for s in steps):
     if max(abs(s) for s in steps)-min(abs(s) for s in steps)<.15:
      add('four_position_stair',m,li,q,'Four ordered evenly spaced strike stations: a 4K execution hypothesis is L-middle → L-index → R-index → R-middle for ascending x; reverse for descending. A four-hit stair alone does not prove a persistent 4K chart segment.')
   if all(.025<=g<=.25 for g in gaps) and max(gaps)-min(gaps)<.005 and all(abs(abs(xs[i+1]-xs[i])-4)<.05 for i in range(3)) and abs(sum(xs)/4)<.1 and len(set(round(x,2) for x in xs))==4 and (all(xs[i+1]>xs[i] for i in range(3)) or all(xs[i+1]<xs[i] for i in range(3))):
    neighbourhood=[n for n in taps if q[0]['seconds']-.4<=n['seconds']<=q[-1]['seconds']+.4]
    if all(min(abs(n['positionX']-x) for x in xs)<.06 for n in neighbourhood):add('four_key_stair_local_segment',m,li,q,'This local segment uses the four symmetric stations x=-6,-2,2,6 with equally spaced judgments. Ascending execution hypothesis: L-middle,L-index,R-index,R-middle; reverse for descending. Confirm simultaneous notes/holds on other carriers before committing.')
   if all(.04<=g<=.3 for g in gaps) and max(xs)-min(xs)<.05:add('jack_repeated_station',m,li,q,'Repeated same-lane strikes need re-press/release between judgments. Choose one repeated finger or alternate hands only after checking following entry and held fingers.')
  for k in range(len(gs)-1):
   t,q=gs[k];u,v=gs[k+1]
   if len(q)==2 and len(v)==1 and .03<u-t<.35:add('jump_then_single',m,li,q+v,'Two separated simultaneous strikes need two prepared fingers, distributed across one or both hands according to position; then the available/nearest finger carries the single. Its x and next ownership decide the alternation.')
  for k in range(len(gs)-2):
   a,b,c=gs[k:k+3]
   if len(a[1])>=2 and len(b[1])>=2 and len(c[1])>=2 and .03<b[0]-a[0]<.35 and .03<c[0]-b[0]<.35:add('chord_stream',m,li,a[1]+b[1]+c[1],'Maintain consistent paired fingers across chord rows; redistribute only if a lane crosses, a new hold owns a finger, or the interval permits a planned hand switch.')
  drag=[n for n in ns if n['type']==2]
  for k in range(len(drag)-4):
   q=drag[k:k+5];xs=[n['positionX'] for n in q];gaps=[q[i+1]['seconds']-q[i]['seconds'] for i in range(4)]
   if all(0<=g<=.12 for g in gaps) and (all(xs[i+1]>=xs[i] for i in range(4)) or all(xs[i+1]<=xs[i] for i in range(4))) and abs(xs[-1]-xs[0])>3:add('drag_sweep',m,li,q,'Trace the ordered contour with continuous contact when its world path stays reachable; do not turn each yellow object into a tap or count every object as a finger.')
  holds=[n for n in ns if n['type']==3 and n['duration_seconds']>.7]
  for h in holds:
   q=[n for n in taps if h['seconds']+.02<n['seconds']<h['seconds']+h['duration_seconds']-.02 and abs(n['positionX']-h['positionX'])>2][:4]
   if len(q)>=3:add('hold_plus_independent_stream',m,li,[h]+q,'Assign a dedicated holding finger/hand and play the stream with the remaining fingers. Confirm moving hold path and world-space collision; local x separation alone is insufficient.')
   q=[n for n in ns if n['type']==4 and abs(n['seconds']-(h['seconds']+h['duration_seconds']))<.075][:1]
   if q:add('flick_near_hold_release',m,li,[h]+q,'Prepare a release/accent gesture while preserving the hold through its tail; separate motion finger when overlapping contact zones or timing make one-finger reuse unreliable.')
  fg=collections.defaultdict(list)
  for n in ns:
   if n['type']==4:fg[round(n['seconds'],4)].append(n)
  for t,q in fg.items():
   if len(q)>=2:add('flick_chord',m,li,q[:4],'Use independently prepared swipe contacts for separated accents; the official judgment window and proximity can permit shared motion, so raw flick count is not necessarily finger count.')
(R/'pattern-ledger.json').write_text(json.dumps(dict(coordinate_convention='Official source line-local positionX units, increasing left-to-right before visual rotation. Chart seconds include offset. Note1tap2drag3hold4flick. Main-locus inference and carrier remapping are intentionally not automated.',patterns=dict(found)),ensure_ascii=False,indent=2))
md=['# Decoded pattern vocabulary','','Examples are exact decoded object tuples from official-format chart files. They are candidate arrangements on one source line. Fingering is a hypothesis, not proof of hand feasibility. Flattening line choreography must preserve carrier/main-locus relationships and simultaneous hold ownership, so raw local x cannot be blindly merged across arbitrary lines.','']
for kind,examples in found.items():
 md+=['## '+kind,'']
 for e in examples:
  md+=[f"**{e['title']} {e['difficulty']}, source line {e['line']}, {e['start_seconds']:.4f}s**",'', '|Seconds|Type|Line-local x|Hold duration|Side|','|---|---|---|---|---|']
  md += ['|%.4f|%s|%.3f|%.4f|%s|'%(n['seconds'],['','Tap','Drag','Hold','Flick'][n['type']],n['positionX'],n['duration_seconds'],n['side']) for n in e['notes']]
  md+=['',e['fingering_hypothesis'],'']
(R/'pattern-ledger.md').write_text('\n'.join(md));print({k:len(v) for k,v in found.items()})
