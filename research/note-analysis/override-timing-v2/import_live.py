"""Import the isolated Override experiment into a fresh empty live project."""
from pathlib import Path
import json
import hashlib
import sys

OUT=Path(__file__).resolve().parent
ROOT=Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0,str(ROOT/'tools/phichain-mcp'))
sys.path.insert(0,str(ROOT/'tools/music-analysis'))
import server
from agent_server import AgentServer
from to_phichain import audio_to_beat,beat_array,beat_number


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))


def checked(result):
    if 'error' in result or result.get('isError'):raise RuntimeError(str(result)[:1500])
    return result


def main():
    endpoint=OUT/'endpoint.json'
    adapter=AgentServer(endpoint,str(ROOT/'target/debug/phichain-renderer'))
    call=lambda name,args:checked(adapter.execute(name,args))
    bridge=lambda name,args:checked(server.call_editor(endpoint,name,args))
    data=json.loads((OUT/'analysis.json').read_text())
    c=bridge('get_context',{})
    assert Path(c['project_path']).resolve()==(OUT/'project').resolve()
    resume='--verify-only' in sys.argv
    if not resume: assert c['note_count']==0 and len(c['lines'])<=1
    assert hashlib.sha256(Path(c['music_path']).read_bytes()).hexdigest()==data['source']['sha256']
    assert abs(c['audio_duration_seconds']-data['source']['duration_seconds'])<.001
    guards={k:c[k] for k in ('session','revision')}
    if resume:
        before=json.loads((OUT/'before-document.json').read_text())
        prepared=json.loads((OUT/'import-input.json').read_text())
        commit=json.loads((OUT/'commit.json').read_text())
        assert c['revision']==commit['revision'], 'Live edits occurred; inspect instead of resuming.'
    else:
        write('templates.json',call('chart_templates',{}))
        before=bridge('authoring_read',guards)['document']
        assert not before['notes'] and not before['curve_tracks']
        write('before-document.json',before)
        convert=lambda t:beat_array(audio_to_beat(t,c['bpm_list'],c['offset']))
        prepared=dict(tracks=[dict(name=f"{i+1:02} / {t['name']} / attack L>R",center=(i-1)*400) for i,t in enumerate(data['tracks'])],
            rows=[dict(id=e['id'],track=e['track'],beat=convert(e['time_seconds']),x=round((e['attack_strength']-50)/50*45,4)) for e in data['events']],
            range_start=convert(0),range_end=convert(data['source']['duration_seconds']+2))
        write('import-input.json',prepared)
        args=dict(**guards,source=(OUT/'author.js').read_text(),input=prepared,dry_run=True,label='Override onset timing v2 / three frequency bands')
        dry=call('chart_script',args);write('dry-run.json',dry)
        latest=bridge('get_context',{})
        assert all(latest[k]==guards[k] for k in guards)
        commit=call('chart_script',dict(args,dry_run=False));write('commit.json',commit)
    now=bridge('get_context',{});guards={k:now[k] for k in guards}
    assert now['revision']==commit['revision'] and now['note_count']==len(data['events']) and len(now['lines'])==3
    snapshot=bridge('authoring_read',guards)['document']
    assert snapshot['bpm_list']==before['bpm_list'] and snapshot['offset']==before['offset']
    assert snapshot['bpm_list']==[{'beat':[0,0,1],'bpm':120.0}] and snapshot['offset']==0
    errors=[]; index=[]
    for i,e in enumerate(data['events']):
        key=commit['created_ids'][f'new:onset_note:{i}'];row=snapshot['notes'][key];note=row['note']
        assert note['kind']=='tap' and abs(note['x']-prepared['rows'][i]['x'])<.00001
        assert row['line_id']==commit['created_ids'][f"new:onset_line:{e['track']}"]
        errors.append(abs(beat_number(note['beat'])/2-e['time_seconds']))
        index.append(dict(native_note_id=key,event_id=e['id'],time_seconds=e['time_seconds'],track=e['track']))
    assert max(errors)<.000026
    diag=call('diagnose',guards);write('diagnosis.json',diag)
    assert not diag.get('errors')
    write('save.json',call('project_save',guards))
    write('verification.json',dict(note_count=now['note_count'],line_count=len(now['lines']),
        max_time_serialization_error_seconds=max(errors),revision=now['revision'],native_note_index=index,
        scope='Native event identity, timestamp, type, position, line, source audio and structural checks; not musical correctness.'))
    call('editor_view',dict(**guards,ids=[],line_id=sorted(now['lines'],key=lambda l:l['order'])[0]['id']))
    call('editor_navigate',dict(**guards,unit='audio_seconds',value=48,action='pause'))
    print(json.dumps(dict(notes=now['note_count'],lines=len(now['lines']),max_serialization_error_seconds=max(errors),project=now['project_path'])))


if __name__=='__main__':main()
