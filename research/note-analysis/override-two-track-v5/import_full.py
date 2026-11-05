"""Guarded native authoring, full correspondence verification and save."""
import json,sys,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0,str(ROOT/'tools/phichain-mcp'));sys.path.insert(0,str(ROOT/'tools/music-analysis'))
import server
from agent_server import AgentServer
from to_phichain import beat_array,beat_number,audio_to_beat


def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))


def main():
    a=json.loads((OUT/'analysis.json').read_text());endpoint=OUT/'endpoint.json'
    adapter=AgentServer(endpoint,str(ROOT/'target/debug/phichain-renderer'))
    def checked(r):
        if r.get('error') or r.get('isError'):raise RuntimeError(str(r)[:1500])
        return r
    call=lambda n,p:checked(adapter.execute(n,p))
    bridge=lambda n,p:checked(server.call_editor(endpoint,n,p))
    c=bridge('get_context',{});g={k:c[k] for k in ['session','revision']}
    assert Path(c['project_path'])==OUT/'project'
    assert hashlib.sha256(Path(c['music_path']).read_bytes()).hexdigest()==a['source']['sha256']
    assert not c['note_count'] and len(c['lines'])<=1
    save('templates.json',call('chart_templates',{}));before=bridge('authoring_read',g)['document'];save('before-document.json',before)
    assert not before['curve_tracks']
    assert c['bpm_list']==[{'beat':[0,0,1],'bpm':120.0}] and c['offset']==0
    b=lambda t:beat_array(t*2)
    rows=[]
    for e in a['events']:
        pitch=sum(e['pitches'])/len(e['pitches']) if e['pitches'] else None
        center=[60,72][e['track']]
        x=max(-28,min(28,(pitch-center)*2)) if pitch is not None else 0
        rows.append(dict(track=e['track'],kind=e['display_type'],beat=b(e['time_seconds']),
            hold_beat=b(e['display_end_seconds']-e['time_seconds']),x=round(x,4)))
    duration=a['source']['duration_seconds'];points=sorted({0.,duration,*[r[k] for r in a['climax_regions'] for k in ['start_seconds','end_seconds']]})
    opacity=[]
    for start,end in zip(points[:-1],points[1:]):
        high=any(r['start_seconds']<=(start+end)/2<r['end_seconds'] for r in a['climax_regions'])
        opacity.append(dict(start=b(start),end=b(end),value=230 if high else 85))
    prepared=dict(tracks=a['tracks'],events=rows,start=b(0),end=b(duration+2),opacity=opacity)
    save('import-input.json',prepared)
    args=dict(**g,source=(OUT/'author.js').read_text(),input=prepared,dry_run=True,label='Override continuous melody drums and main melody')
    save('dry-run.json',call('chart_script',args))
    latest=bridge('get_context',{});assert all(latest[k]==g[k] for k in g)
    commit=call('chart_script',dict(args,dry_run=False));save('commit.json',commit)
    c=bridge('get_context',{});g={k:c[k] for k in g};assert c['revision']==commit['revision']
    doc=bridge('authoring_read',g)['document'];assert len(doc['notes'])==len(rows) and len(doc['lines'])==2
    errors=[];index=[]
    for i,(e,p) in enumerate(zip(a['events'],rows)):
        key=commit['created_ids'][f'new:voice_note:{i}'];n=doc['notes'][key]
        assert n['line_id']==commit['created_ids'][f"new:voice_line:{e['track']}"]
        assert n['note']['kind']==p['kind'] and abs(n['note']['x']-p['x'])<.00001
        head=beat_number(n['note']['beat'])/2;errors.append(abs(head-e['time_seconds']))
        if p['kind']=='hold':errors.append(abs(head+beat_number(n['note']['hold_beat'])/2-e['display_end_seconds']))
        index.append(dict(native_id=key,event_id=e['id'],track=e['track']))
    assert max(errors)<.000051
    diagnosis=call('diagnose',g);save('diagnosis.json',diagnosis);assert not diagnosis.get('errors')
    save('save.json',call('project_save',g))
    save('verification.json',dict(events=len(rows),tracks=2,max_time_conversion_error_seconds=max(errors),revision=c['revision'],index=index))
    call('editor_view',dict(**g,ids=[],line_id=commit['created_ids']['new:voice_line:0']))
    call('editor_navigate',dict(**g,unit='audio_seconds',value=48,action='pause'))
    print(json.dumps(dict(events=len(rows),holds=sum(e['kind']=='hold' for e in rows),max_time_conversion_error_seconds=max(errors))))


if __name__=='__main__':main()
