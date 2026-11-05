"""Sol6.1-medium prompt interpretations replayed over public MCP, with independent assertions.

This is a visible eight-task behavioral baseline, not a held-out model comparison.
The agent selected these operations from the natural-language prompts; Python is
the protocol/measurement/assertion controller, not another language model.
"""
import asyncio,json,time,sys
from pathlib import Path
from fractions import Fraction as F
from protocol_client import connect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'behavioral-baseline'
SOURCE=Path('/Users/jesse/Projects/phigros-chart-mcp/evaluation/tasks.json')
def bytes_json(v):return len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
def note(kind,beat,x,**extra):return dict(kind=kind,beat=str(beat),x=x,**extra)
def effect(line,ch,a,z,v,w):return dict(type='set_effect',line_id=line,channel=ch,start=str(a),end=str(z),a=v,b=w,easing='linear',replace=True)
def annotation(f,role):return {'finger_key':f,'hand':f[0],'finger':f.split('_')[1],'voice':role,'gesture':role}

async def main():
    OUT.mkdir();fixture=json.loads(SOURCE.read_text());(OUT/'tasks.json').write_bytes(SOURCE.read_bytes())
    receipts=[];reports=[];setup=fixture['common_setup'];context={}
    async def call(s,name,args,task,phase):
        t=time.perf_counter();raw=await s.call_tool(name,args)
        result=raw.structuredContent
        if result is None:
            text=next(c.text for c in raw.content if c.type=='text')
            try:result=json.loads(text)
            except json.JSONDecodeError:result={'sdk_text':text}
        row={'task':task,'phase':phase,'tool':name,'arguments':args,'result':result,'is_error':bool(raw.isError),'argument_utf8_bytes':bytes_json(args),'result_utf8_bytes':bytes_json(result),'elapsed_s':time.perf_counter()-t};receipts.append(row)
        (OUT/'protocol-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
        if raw.isError:raise ValueError(row)
        return result
    async def plan_apply(s,state,ops,task,phase='task',rationale='Prompt-directed edit'):
        p=await call(s,'authoring_plan',dict(chart_ref=state['chart_ref'],digest=state['digest'],operations=ops,section={'name':task,'rationale':rationale}),task,phase)
        return await call(s,'authoring_apply',dict(plan_ref=p['plan_ref'],digest=state['digest']),task,phase)
    async def create(s,t):
        state=await call(s,'chart_create',dict(metadata={'title':'Behavioral baseline: '+t['id']},bpm=setup['bpm'],offset_ms=setup['offset_ms'],main_line=setup['main_line']),t['id'],'setup')
        if t['seed']:state=await plan_apply(s,state,[dict(type='insert_notes',line_id='main',notes=t['seed'])],t['id'],'setup','Provided pre-existing fixture, not an inferred edit')
        return state
    async def read(s,state,t,start='0',end='100',phase='verification'):
        return await call(s,'chart_read',dict(chart_ref=state['chart_ref'],digest=state['digest'],start=start,end=end,limit=100,include_events=True),t,phase)
    async def exports(s,state,t,path):
        await call(s,'authoring_check',dict(chart_ref=state['chart_ref'],digest=state['digest']),t,'verification')
        for fmt,name in [('phichain_native','chart.json'),('phigros_v3','chart.phigros.json')]:await call(s,'chart_export',dict(chart_ref=state['chart_ref'],digest=state['digest'],format=fmt,output_path=str(path/name)),t,'artifacts')
    def judge(t,values,rationale,clarification=None):
        failed=[label for label,ok in values.items() if not ok]
        reports.append({'id':t['id'],'model':'gpt-6.1-sol','reasoning_effort':'medium','prompt':t['prompt'],'prompt_utf8_bytes':len(t['prompt'].encode()),'acceptance':values,'critical_errors':failed,'repairs':[],'clarification':clarification,'clarification_count':int(clarification is not None),'rationale':rationale,'artifact_directory':str((OUT/t['id']).resolve())})
        if failed:raise AssertionError((t['id'],failed))
    async with connect() as s:
        listed=await s.list_tools();context['tools']=listed.model_dump(mode='json')
        for uri in ['phigros-authoring://guide/v1','phigros-authoring://operations/v1']:
            resource=await s.read_resource(uri);context[uri]=resource.model_dump(mode='json')
        (OUT/'shared-context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2))
        for t in fixture['tasks'][:-1]:
            ident=t['id'];path=OUT/ident;path.mkdir();state=await create(s,t);rationale='';checks={};clarification=None
            if ident=='two_bar_four_key_stair':
                ops=[dict(type='insert_pattern',line_id='main',pattern='stairs',start=str(start),count=16,step='1/4',lane_x=[-.3,-.1,.1,.3],order=order,kind='tap') for start,order in [(32,[0,1,2,3]),(36,[3,2,1,0])]]
                ops.append(dict(type='transform_notes',line_id='main',start='159/4',end='40',kind='flick'))
                rationale='Two 4/4 bars contain32 sixteenth heads; descending second bar changes positions, and the terminal release alone is a flick.'
                state=await plan_apply(s,state,ops,ident,rationale=rationale);p=await read(s,state,ident,'32','40');ns=p['notes'];by={F(n['beat']):n for n in ns}
                checks={'32 exact sixteenths':len(ns)==32 and set(by)=={F(32)+F(i,4) for i in range(32)},'first bar ascends':[by[F(32)+F(i,4)]['x'] for i in range(4)]==[-.3,-.1,.1,.3],'second bar descends':[by[F(36)+F(i,4)]['x'] for i in range(4)]==[.3,.1,-.1,-.3],'only terminal flick':sum(n['kind']=='flick' for n in ns)==1 and by[F(159,4)]['kind']=='flick','one main line':len(p['lines'])==1 and all(n['canonical_axis']['anchor_id']=='main' for n in ns)}
            elif ident=='approach_speed_not_rhythm':
                before=await read(s,state,ident,'8','12','task_read');state=await plan_apply(s,state,[dict(type='transform_notes',line_id='main',start='8',end='12',speed_multiplier=2)],ident,rationale='Double note approach multiplier only; preserve beat lattice, BPM and judgment geometry.')
                p=await read(s,state,ident,'8','12');a=before['notes'];b=p['notes'];checks={'four unchanged head times':len(b)==4 and [n['time'] for n in a]==[n['time'] for n in b],'world targets unchanged':[n['world_target'] for n in a]==[n['world_target'] for n in b],'speed doubles':all(y['speed']==2*x['speed'] for x,y in zip(a,b)),'BPM unchanged':p['tempo_map']==before['tempo_map']};rationale='Faster approach means scroll speed, not doubled BPM or denser rhythm.'
            elif ident=='independent_note_sway':
                before=await read(s,state,ident,'10','15','task_read');target=next(n for n in before['notes'] if F(n['beat'])==12)
                ops=[dict(type='create_line',id='carrier',name='Isolated approach sway',role='note_carrier',anchor_id='main',x=0,y=-.25,rotation=0,opacity=0,speed=2)]
                for a,z,v,w in [(10,10.5,0,-.025),(10.5,11,-.025,.025),(11,11.5,.025,-.0125),(11.5,11.75,-.0125,0)]:ops.append(effect('carrier','x',a,z,v,w))
                ops.append(dict(type='move_note',line_id='main',id=target['id'],target_line_id='carrier',x=.1));state=await plan_apply(s,state,ops,ident,rationale='Carrier isolates one approach; it settles before the original target, while main line and neighboring notes stay fixed.')
                p=await read(s,state,ident,'10','15');by={F(n['beat']):n for n in p['notes']};old={F(n['beat']):n for n in before['notes']};line=next(l for l in p['lines'] if l['id']=='carrier');main=next(l for l in p['lines'] if l['id']=='main')
                checks={'isolated carrier':by[F(12)]['line_id']=='carrier' and line['note_count']==1,'declared main anchor':line['anchor_id']=='main','original target preserved':by[F(12)]['world_target']==old[F(12)]['world_target'],'other notes unchanged':all(by[F(k)]['time']==old[F(k)]['time'] and by[F(k)]['x']==old[F(k)]['x'] and by[F(k)]['line_id']=='main' for k in [10,14]),'main geometry unchanged':main['events']==before['lines'][0]['events'],'prehit lateral motion':any(e['channel']=='x' and e['a']!=e['b'] for e in line['events'])};rationale='Hidden carrier gives independent sway; no unsupported note animation or second playing locus.'
            elif ident=='sustained_voice_and_answers':
                ns=[note('hold',8,x,duration='7/2',annotation=annotation(f,'sustained outer chord')) for x,f in [(-.3,'L_middle'),(.3,'R_middle')]]
                ns += [note('tap',b,x,annotation=annotation(f,'inner answer')) for b,x,f in [(8.5,-.1,'L_index'),(9.5,.1,'R_index'),(10.5,-.1,'L_index'),(11.5,.1,'R_index')]]
                state=await plan_apply(s,state,[dict(type='insert_notes',line_id='main',notes=ns)],ident,rationale='Outer middle fingers sustain to11.5, giving half-beat release; index fingers alternate independent inner attacks.')
                p=await read(s,state,ident,'8','12');tail=await read(s,state,ident,'10','11');hs=[n for n in p['notes'] if n['kind']=='hold'];ts=[n for n in p['notes'] if n['kind']=='tap'];checks={'two holds8–11.5':len(hs)==2 and all(F(n['beat'])==8 and F(n['duration'])==F(7,2) for n in hs),'four exact inner taps':sorted(F(n['beat']) for n in ts)==[F(17,2),F(19,2),F(21,2),F(23,2)],'ownership distinct':{n['annotation']['finger_key'] for n in hs}=={'L_middle','R_middle'} and {n['annotation']['finger_key'] for n in ts}=={'L_index','R_index'},'targets separated':{n['x'] for n in hs}=={-.3,.3} and {n['x'] for n in ts}=={-.1,.1},'overlapping holds included':sum(n['kind']=='hold' for n in tail['notes'])==2};rationale='At answer instants two sustained contacts plus one fresh index strike are intended; raw object counts do not prove comfort.'
            elif ident=='rest_despite_audio_energy':
                ops=[dict(type='create_line',id='rest-guide',name='Empty reverb guide',role='decorative',x=0,y=-.1,rotation=0,opacity=0,speed=2),effect('rest-guide','rotation',16.5,22.5,4,0),effect('rest-guide','y',16.5,22.5,-.1,-.25),effect('rest-guide','opacity',16.5,17.5,0,.12),effect('rest-guide','opacity',17.5,21,.12,.12),effect('rest-guide','opacity',21,22.5,.12,0)]
                state=await plan_apply(s,state,ops,ident,rationale='Loud reverb is sustained energy, not evidence of fresh attacks. Empty decoration fades before pickup; full physical rest remains16–24.')
                p=await read(s,state,ident,'12','25');ns=p['notes'];decor=next(l for l in p['lines'] if l['id']=='rest-guide');main=next(l for l in p['lines'] if l['id']=='main');checks={'source heads preserved':len(ns)==2 and sorted(F(n['beat']) for n in ns)==[F(12),F(24)],'hold ends16':next(F(n['beat'])+F(n['duration']) for n in ns if n['kind']=='hold')==16,'no contacts16–24':not any(F(n['beat'])<24 and (F(n['beat'])+(F(n['duration']) if n['kind']=='hold' else 0))>16 for n in ns),'empty decorative guide':decor['role']=='decorative' and decor['note_count']==0,'main landmark unchanged':all(e['a']==e['b']==1 for e in main['events'] if e['channel']=='opacity')};rationale='Preserve recovery despite a loud tail; decorations own no notes.'
            elif ident=='four_types_without_quota':
                ns=[note('tap',b,-.13 if b%2==0 else .13,annotation=annotation('L_index' if b%2==0 else 'R_index','dry attack')) for b in range(4)]+[note('hold',4,-.13,duration='3',annotation=annotation('L_index','sustained sound'))]
                state=await plan_apply(s,state,[dict(type='insert_notes',line_id='main',notes=ns)],ident,rationale='Four discrete attacks and one sustain; no connected flourish or release accent, so no drag/flick. Release at7 leaves onebeat before8.')
                p=await read(s,state,ident,'0','8');ns=p['notes'];checks={'four attacks0–3':sorted(F(n['beat']) for n in ns if n['kind']=='tap')==[F(i) for i in range(4)],'one sustained4–7':sum(n['kind']=='hold' and F(n['beat'])==4 and F(n['duration'])==3 for n in ns)==1,'no forced kinds':len(ns)==5 and not any(n['kind']in('drag','flick') for n in ns),'explicit recovery':max(F(n['beat'])+(F(n['duration']) if n['kind']=='hold' else 0) for n in ns)==7};rationale='Gesture vocabulary follows supplied attacks and sustain; four kinds are not a quota.'
            else:
                p=await read(s,state,ident,'8','10','clarification_read');clarification='Do you mean denser rhythms, faster note approach, or faster line movement?';rationale='These interpretations change different musical/visual properties; no dependent edit before the answer.';checks={'one targeted clarification':bool(clarification),'no dependent mutation':not any(r['task']==ident and r['phase']=='task' and r['tool'] in ['authoring_plan','authoring_apply'] for r in receipts),'original two heads':len(p['notes'])==2 and [F(n['beat']) for n in p['notes']]==[F(8),F(9)]}
            await exports(s,state,ident,path)
            if ident in ('independent_note_sway','rest_despite_audio_energy'):
                m=json.loads((path/'chart.authoring.json').read_text())['model'];main=next(l for l in m['lines'] if l['id']=='main');expected={'x':0,'y':-.25,'rotation':0,'opacity':1,'speed':2}
                checks['whole exported main track unchanged']=set(e['channel'] for e in main['events'])==set(expected) and all(e['a']==e['b']==expected[e['channel']] for e in main['events'])
            judge(t,checks,rationale,clarification)
        recovery=fixture['tasks'][-1];path=OUT/recovery['id'];path.mkdir();state=await create(s,recovery);old=dict(state);checkpoint=await call(s,'chart_export',dict(chart_ref=state['chart_ref'],digest=state['digest'],format='phichain_native',output_path=str(path/'checkpoint.json')),recovery['id'],'disconnect_setup')
    # A new stdio process models the lost connection and invalid ephemeral handles.
    async with connect() as s:
        recovered=await call(s,'chart_import',dict(source_path=str(path/'checkpoint.authoring.json')),recovery['id'],'recovery');p=await read(s,recovered,recovery['id'],'8','10','recovery');await exports(s,recovered,recovery['id'],path)
        judge(recovery,{'imports durable sidecar':recovered['chart_ref']!=old['chart_ref'],'exactly two original heads':len(p['notes'])==2 and [F(n['beat']) for n in p['notes']]==[F(8),F(9)],'no blind replay':not any(r['task']==recovery['id'] and r['phase']=='recovery' and r['tool']=='authoring_apply' for r in receipts),'recovered digest used':all(r['arguments'].get('digest',recovered['digest'])==recovered['digest'] for r in receipts if r['task']==recovery['id'] and r['phase'] in ['recovery','verification','artifacts'])},'Read the recovered phrase before continuation; it already exists, so do not replay the lost apply. Old ephemeral handles are discarded.')
    for report in reports:
        rows=[r for r in receipts if r['task']==report['id']];report.update(tool_calls=len(rows),argument_utf8_bytes=sum(r['argument_utf8_bytes'] for r in rows),result_utf8_bytes=sum(r['result_utf8_bytes'] for r in rows),tool_elapsed_s=sum(r['elapsed_s'] for r in rows),shared_context_utf8_bytes=bytes_json(context));(OUT/report['id']/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary={'model':'gpt-6.1-sol','reasoning_effort':'medium','visible_prompt_interpretations':True,'tasks':reports,'passed':sum(not r['critical_errors'] for r in reports),'total_tasks':len(reports),'shared_context_utf8_bytes':bytes_json(context),'transport_serialization':'Compact JSON UTF-8, ensure_ascii=False; not model-token estimates. Setup/artifact calls included and phases retained.','limitation':'This tests the eight supplied authoring behaviors with a Sol6.1-medium agent interpretation and public protocol replay. It is not a Luna run, hidden-task benchmark, human playtest or full-song official-quality proof.'};(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({'passed':summary['passed'],'tasks':len(reports),'calls':len(receipts),'arguments':sum(r['argument_utf8_bytes'] for r in receipts),'results':sum(r['result_utf8_bytes'] for r in receipts)},indent=2))
if __name__=='__main__':asyncio.run(main())
