"""Replay compact evidence/phrase recipe solely through the public MCP protocol."""
import asyncio, json, sys, time
from pathlib import Path
from fractions import Fraction
from collections import Counter, defaultdict
from protocol_client import connect
from motif_compiler import compile_phrase
ROOT=Path(__file__).resolve().parents[1]
def prepare():
    recipe=json.loads((ROOT/'recipe/phrase_recipe.json').read_text()); evidence=json.loads((ROOT/'evidence/phrase_events.json').read_text())
    batches=[]; notes=[]; summaries=[];state={}
    for config,section in zip(recipe['phrases'],evidence['sections']):
        ops,summary=compile_phrase(config,section,recipe,state);batches.append((config,section,ops));summaries.append(summary)
        notes.extend(n for op in ops for n in op.get('notes',[]))
    (ROOT/'recipe/prospective-summary.json').write_text(json.dumps({'head_count':len(notes),'kinds':dict(Counter(n['kind'] for n in notes)),'phrases':summaries},indent=2))
    audit(notes)
    return recipe,evidence,batches
def audit(notes):
    beat=lambda n:float(Fraction(n['beat'])); contacts=[]; gestures=defaultdict(list); fresh=defaultdict(list)
    for n in notes:
        if n['kind']=='hold':contacts.append(dict(start=beat(n),end=beat(n)+float(Fraction(n['duration'])),finger=n['annotation']['finger_key'],kind='hold',gesture=n['annotation']['gesture']))
        elif n['kind']=='drag':gestures[n['annotation']['gesture']].append(n)
        if n['kind']!='drag':fresh[beat(n)].append(n)
    for g,ns in gestures.items():contacts.append(dict(start=min(map(beat,ns)),end=max(map(beat,ns))+.125,finger=ns[0]['annotation']['finger_key'],kind='drag',gesture=g))
    conflicts=[]; four=[]; peak=0
    for b,heads in sorted(fresh.items()):
        active=[c for c in contacts if c['start']<b-1e-8 and b<c['end']-1e-8]; fingers=[c['finger'] for c in active]+[n['annotation']['finger_key'] for n in heads]
        if len(fingers)!=len(set(fingers)):conflicts.append({'beat':b,'active':active,'heads':[(n['kind'],n['annotation']['finger_key']) for n in heads]})
        peak=max(peak,len(set(fingers)))
        if len(set(fingers))==4:four.append({'beat':b,'seconds':b*60/225,'phrase':heads[0]['annotation']['phrase'],'held_or_drag':active,'fresh_fingers':[n['annotation']['finger_key'] for n in heads]})
    repeats=[]
    for f in ('L_middle','L_index','R_index','R_middle'):
        ns=sorted([n for n in notes if n['kind']!='drag' and n['annotation']['finger_key']==f],key=beat)
        for a,b in zip(ns,ns[1:]):repeats.append({'finger':f,'from':beat(a),'to':beat(b),'gap_ms':(beat(b)-beat(a))*60/225*1000,'travel_native_x':abs(a['x']-b['x'])*1350})
    result={'method':'Assigned finger occupancy: exact hold interval; drag gesture continuous through last target +1/8 beat; fresh strike distinct contact. Structural accounting, not a playtest.','head_count':len(notes),'peak_assigned_contacts':peak,'conflicts':conflicts,'four_contact_witness_count':len(four),'four_contact_witnesses':four[:40],'fastest_same_finger_strikes':sorted(repeats,key=lambda r:r['gap_ms'])[:20],'cross_phrase_contacts':[c for c in contacts if any(c['start']<b<c['end'] for b in [16,48,80,112,144,176,208,240,272,304,312,336,368,390,422,448,454,466,496,528,560,592,626.125,630,646])]}
    (ROOT/'recipe/corrected-prospective-finger-audit.json').write_text(json.dumps(result,indent=2))
    if conflicts:raise ValueError(f'{len(conflicts)} assigned finger conflicts; repair before replay')
async def main():
    recipe,evidence,batches=prepare(); receipts=[]
    output=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'baseline-v3');output.mkdir(exist_ok=True)
    async def invoke(session,name,args):
        t=time.perf_counter()
        raw=await session.call_tool(name,args)
        if raw.isError:
            print(name,args.get('config',{}).get('id'),raw.content);raise ValueError('Public MCP tool failed')
        result=raw.structuredContent or json.loads(next(c.text for c in raw.content if c.type=='text'))
        receipts.append({'tool':name,'arguments':args,'result':result,'payload_bytes':len(json.dumps(args).encode()),'elapsed_s':time.perf_counter()-t});return result
    async with connect() as session:
        state=await invoke(session,'chart_create',dict(metadata={'title':recipe['song'],'composer':'Ardolf vs. Daily天利','charter':'Original study arrangement — AI-assisted fanmade','difficulty_label':'AT 17 provisional','rationale':'One playing line; evidence-grounded motif development and assigned four-finger independence.'},bpm=225,offset_ms=0,audio_duration_seconds=173.7912018,main_line=recipe['defaults']['main_line']))
        for config,section,ops in batches:
            cached=await invoke(session,'evidence_import',dict(source_path=str(ROOT/'evidence/portable'/(config['id']+'.json'))))
            plan=await invoke(session,'authoring_plan_phrase',dict(chart_ref=state['chart_ref'],digest=state['digest'],evidence_ref=cached['evidence_ref'],config=config,lanes=recipe['lanes'],defaults={k:recipe['defaults'][k] for k in ['release_guard_beats','note_speed']},line_id='main'))
            state=await invoke(session,'authoring_apply',dict(plan_ref=plan['plan_ref'],digest=state['digest']))
        checked=await invoke(session,'authoring_check',dict(chart_ref=state['chart_ref'],digest=state['digest']))
        for fmt,name in [('phichain_native','chart.json'),('phigros_v3','chart.phigros.json')]:
            await invoke(session,'chart_export',dict(chart_ref=state['chart_ref'],digest=state['digest'],format=fmt,output_path=str(output/name)))
    (ROOT/'receipts'/(output.name+'-public-mcp.json')).write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
    (output/'check.json').write_text(json.dumps(checked,indent=2))
    (output/'finger-audit.json').write_text((ROOT/'recipe/corrected-prospective-finger-audit.json').read_text())
    print(json.dumps({'calls':len(receipts),'payload_bytes':sum(r['payload_bytes'] for r in receipts),'elapsed_s':sum(r['elapsed_s'] for r in receipts),'check':checked},indent=2))
if __name__=='__main__':asyncio.run(main())
