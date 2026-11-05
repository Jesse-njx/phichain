import pathlib,json,collections,bisect,math
P=pathlib.Path('../research/overnight-study/corpus');R=P.parent/'research';M=json.loads((P/'manifest.json').read_text())+json.loads((P/'supplemental-manifest.json').read_text());out=[]
def val(es,t):
 if not es:return 0
 i=max(0,bisect.bisect_right([e['startTime'] for e in es],t)-1);e=es[i];f=max(0,min(1,(t-e['startTime'])/(e['endTime']-e['startTime']))) if e['endTime']!=e['startTime'] else 1;return e['start']+(e['end']-e['start'])*f
for m in M:
 d=json.loads(pathlib.Path(m['chart']['path']).read_text());hist=collections.Counter();ns=[]
 for li,l in enumerate(d['judgeLineList']):
  fac=1.875/l['bpm']
  for side in ['notesAbove','notesBelow']:
   for n in l[side]:
    angle=(90-val(l['judgeLineRotateEvents'],n['time'])+(180 if side=='notesBelow' else 0))%360;bucket=round(angle/90)*90%360;err=abs((angle-bucket+180)%360-180);label={0:'rightward',90:'downward',180:'leftward',270:'upward'}[bucket] if err<=15 else 'oblique';hist[label]+=1
    ns.append(dict(seconds=n['time']*fac+d.get('offset',0),line=li,type=n['type'],line_local_x=n['positionX'],approach_angle_screen_degrees=angle,approach_category=label,duration=n['holdTime']*fac))
 groups=collections.defaultdict(list)
 for n in ns:
  if n['type'] in [1,3,4]:groups[round(n['seconds'],4)].append(n)
 examples=[]
 for t,q in sorted(groups.items()):
  cats=set(n['approach_category'] for n in q)
  if len(cats)>=2 and len(q)>1:examples.append(dict(time=t,approach_categories=sorted(cats),heads=q))
  if len(examples)>=6:break
 out.append(dict(id=m['id'],title=m['title'],difficulty=m['difficulty'],supplemental=m.get('supplemental',False),onset_object_approach_histogram=dict(hist),contrasting_simultaneous_head_examples=examples))
(R/'approach-directions.json').write_text(json.dumps(dict(method='Approach direction at note onset from official line rotation and above/below side; screen-space90deg downward. Cardinal category tolerance15deg; excludes speed reversal, stop/accelerate mechanics. Raw object counts are not finger counts. Same-source line-local x is not a solved common main-locus mapping.',charts=out),ensure_ascii=False,indent=2));print('\n'.join(str((x['title'],x['difficulty'],x['onset_object_approach_histogram'],[e['time'] for e in x['contrasting_simultaneous_head_examples']])) for x in out if x['supplemental']))
