"""Generic presentation recipe replay through MCP; no native chart writes."""
import asyncio,json,sys,time
from pathlib import Path
from fractions import Fraction
from protocol_client import connect
ROOT=Path(__file__).resolve().parents[1]
async def main():
    config=json.loads((ROOT/'recipe/presentation_recipe.json').read_text());evidence=json.loads((ROOT/'evidence/phrase_events.json').read_text());ranges={s['id']:(s['beat_start'],s['beat_end']) for s in evidence['sections']}
    out=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'final');out.mkdir(exist_ok=True);receipts=[]
    async def call(s,name,args):
        t=time.perf_counter();raw=await s.call_tool(name,args)
        if raw.isError:raise ValueError(str(raw.content))
        r=raw.structuredContent or json.loads(raw.content[0].text);receipts.append(dict(tool=name,arguments=args,result=r,payload_bytes=len(json.dumps(args).encode()),elapsed_s=time.perf_counter()-t));return r
    async with connect() as s:
        baseline=ROOT/(sys.argv[2] if len(sys.argv)>2 else 'baseline-v3')
        state=await call(s,'chart_import',dict(source_path=str(baseline/'chart.authoring.json')))
        async def apply(ops,section):
            nonlocal state
            p=await call(s,'authoring_plan',dict(chart_ref=state['chart_ref'],digest=state['digest'],operations=ops,section=section));state=await call(s,'authoring_apply',dict(plan_ref=p['plan_ref'],digest=state['digest']))
        await apply([dict(type='annotate_notes',line_id='main',start='312',end='336',annotation_patch={'rationale':'Sparse melodic contour, two preferred index fingers with recovery-aware fallback. Exact official articulation timing is evidence; instrument identity is unverified.'})],dict(name='Provenance wording correction',rationale='Use melodic rather than unverified piano identity; scoring and ownership unchanged.'))
        ops=[dict(type='set_effect',line_id='main',channel='y',start=str(p['start']),end=str(p['end']),a=p['a'],b=p['b'],easing='linear',replace=True) for p in config.get('main_y_transitions',[])]
        if config.get('main_opacity_tail'):
            p=config['main_opacity_tail'];ops.append(dict(type='set_effect',line_id='main',channel='opacity',start=str(p['start']),end=str(p['end']),a=p['a'],b=p['b'],easing='linear',replace=True))
        if ops:await apply(ops,dict(name='Main-anchor breathing and final release',rationale='Only one bright horizontal playing locus. It lifts during the long actual contact rest and settles six beats before pickup; a restrained final lift begins after all contacts and their release guard. Holds keep fixed contact points through their tails.',recipe=config.get('main_y_transitions')))
        for spec in config['lateral_phrases']:
            a,z=ranges[spec['phrase']];cell=spec['cell_beats'] or z-a;ops=[];i=0
            while a<z-1e-8:
                end=min(z,a+cell);shift=spec['center_amplitude']*spec['center_cycle'][i%len(spec['center_cycle'])]
                ops.append(dict(type='transform_notes',line_id='main',start=str(a),end=str(end),scale=spec['scale'],shift=shift));a=end;i+=1
            await apply(ops,dict(name='lateral '+spec['phrase'],rationale=spec['rationale'],recipe=spec))
        # Public bounded reads provide IDs for five deliberate carrier accents.
        for i,spec in enumerate(config['carrier_accents']):
            a,z=ranges[spec['phrase']];notes=[];cursor=0
            while True:
                page=await call(s,'chart_read',dict(chart_ref=state['chart_ref'],digest=state['digest'],start=str(a),end=str(z),line_id='main',limit=4,cursor=cursor,include_events=False));notes.extend(page['notes'])
                if len([n for n in notes if n['kind']==spec['kind']])>spec['ordinal'] or page.get('next_cursor') is None:break
                cursor=page['next_cursor']
            candidates=sorted([n for n in notes if n['kind']==spec['kind'] and n['annotation'].get('phrase')==spec['phrase']],key=lambda n:Fraction(n['time']))
            n=candidates[spec['ordinal']];b=float(Fraction(n['time']))*225/60;line='carrier-'+str(i+1);template=config['carrier_template'];start=max(0,b-template['lead_beats']);settle=b-template['settle_before_beats'];main=config['main_line_invariant']
            ops=[dict(type='create_line',id=line,name='Approach accent '+spec['phrase'],role='note_carrier',anchor_id='main',x=0,y=main['y'],rotation=0,opacity=0,speed=1.4)]
            for channel,a,z in [('x',spec['offset_x'],0),('y',main['y']+spec['offset_y'],main['y'])]:ops.append(dict(type='set_effect',line_id=line,channel=channel,start=str(start),end=str(settle),a=a,b=z,easing='linear',replace=True))
            ops.append(dict(type='move_note',line_id='main',id=n['id'],target_line_id=line,x=n['x']))
            await apply(ops,dict(name='Settled carrier '+spec['phrase'],rationale='Only one isolated attack approaches with subtle lateral displacement; hidden carrier settles 0.75 beat before impact onto the visible main playing line.',recipe=spec,target_beat=b))
        for i,sign in enumerate(config['decorative_guide_factors']):
            line='decorative-fold-'+str(i+1);ops=[dict(type='create_line',id=line,name='Empty cycle guide '+str(i+1),role='decorative',x=0,y=-.28,rotation=0,opacity=0,speed=1.4)]
            for fold in config['decorative_folds']:
                a,z=fold['start'],fold['end'];alpha=fold['opacity']
                for channel,begin,finish in [('rotation',sign*fold['amplitude'],0)]:
                    if fold.get('mode')=='open_close':
                        middle=fold['middle'];segments=[(a,middle,finish,begin),(middle,z,begin,finish)]
                    else:segments=[(a,z,begin,finish)]
                    for start,end,v,w in segments:ops.append(dict(type='set_effect',line_id=line,channel=channel,start=str(start),end=str(end),a=v,b=w,easing='linear',replace=True))
                path=fold.get('center_y_path',[[a,-.28],[z,-.28]])
                def center(t):
                    for (p,v),(q,w) in zip(path,path[1:]):
                        if p<=t<=q:return v+(w-v)*(t-p)/(q-p)
                    return path[-1][1]
                def offset(t):
                    if fold.get('mode')=='open_close':
                        middle=fold['middle'];ratio=(t-a)/(middle-a) if t<=middle else (z-t)/(z-middle)
                    else:ratio=(z-t)/(z-a)
                    return sign*.16*ratio
                breaks=sorted(set([a,z]+[p for p,v in path if a<p<z]+([fold['middle']] if fold.get('mode')=='open_close' else [])))
                for start,end in zip(breaks,breaks[1:]):ops.append(dict(type='set_effect',line_id=line,channel='y',start=str(start),end=str(end),a=center(start)+offset(start),b=center(end)+offset(end),easing='linear',replace=True))
                for start,end,v,w in [(a,a+2,0,alpha),(a+2,z-2,alpha,alpha),(z-2,z,alpha,0)]:ops.append(dict(type='set_effect',line_id=line,channel='opacity',start=str(start),end=str(end),a=v,b=w,easing='linear',replace=True))
            await apply(ops,dict(name='Empty cycle folds',rationale='Four empty fan guides unfold during preserved rests and the final pedal, then converge and fade. Main anchor stays brighter. Guides never contain notes or introduce another playing locus.',recipe=config['decorative_folds']))
        checked=await call(s,'authoring_check',dict(chart_ref=state['chart_ref'],digest=state['digest']))
        for fmt,name in [('phichain_native','chart.json'),('phigros_v3','chart.phigros.json')]:await call(s,'chart_export',dict(chart_ref=state['chart_ref'],digest=state['digest'],format=fmt,output_path=str(out/name)))
    (ROOT/'receipts'/(out.name+'-presentation-public-mcp.json')).write_text(json.dumps(receipts,ensure_ascii=False,indent=2));(out/'check.json').write_text(json.dumps(checked,indent=2));print(json.dumps({'calls':len(receipts),'payload_bytes':sum(r['payload_bytes'] for r in receipts),'elapsed_s':sum(r['elapsed_s'] for r in receipts),'check':checked},indent=2))
if __name__=='__main__':asyncio.run(main())
