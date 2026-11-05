"""Edited official compatibility witnesses from real corpus sources."""
import hashlib
import json
import time
from pathlib import Path
from collections import Counter
from phigros_chart_mcp.core import Engine
BASE = Path('/Users/jesse/Projects/PhiChain/phichain')
manifest = json.loads((BASE/'../research/overnight-study/corpus/manifest.json').read_text())
requests = [("Rrhar'il",'IN'),('Stardust:RAY','IN'),('彩','IN'),('玩具狂奏曲 -終焉-','AT')]
report=[]
for title,difficulty in requests:
    row=next(r for r in manifest if r['title']==title and r['difficulty']==difficulty)
    path=BASE/row['chart']['path'];original=path.read_bytes();source=json.loads(original)
    e=Engine();r=dict(title=title,difficulty=difficulty,source_sha256=hashlib.sha256(original).hexdigest(),timings={});phase=time.perf_counter()
    try:
        c=e.chart_import(str(path));r['timings']['import_seconds']=time.perf_counter()-phase;phase=time.perf_counter()
        p=e.authoring_plan(c['chart_ref'],c['digest'],[{'type':'insert_notes','line_id':'line-0','notes':[
            {'id':'independent-witness','kind':'tap','beat':'1/2','x':-.123}]}])
        r['timings']['plan_seconds']=time.perf_counter()-phase;phase=time.perf_counter()
        c=e.authoring_apply(p['plan_ref'],c['digest']);r['timings']['apply_seconds']=time.perf_counter()-phase;phase=time.perf_counter()
        exported=e.chart_export(c['chart_ref'],c['digest'])['chart'];r['timings']['official_export_seconds']=time.perf_counter()-phase;phase=time.perf_counter()
        old=source['judgeLineList'][0];new=exported['judgeLineList'][0]
        encode=lambda n:json.dumps(n,sort_keys=True,separators=(',',':'))
        note_preserved=True
        for side in ['notesAbove','notesBelow']:
            a=Counter(encode(n) for n in old[side]);b=Counter(encode(n) for n in new[side])
            note_preserved &= all(b[k]>=v for k,v in a.items())
        tracks=['speedEvents','judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents']
        r.update(status='pass',untouched_lines_equal=source['judgeLineList'][1:]==exported['judgeLineList'][1:],
                 existing_notes_exactly_preserved=note_preserved,edited_line_tracks_equal=all(old[k]==new[k] for k in tracks))
        if not all(r[k] for k in ['untouched_lines_equal','existing_notes_exactly_preserved','edited_line_tracks_equal']):r['status']='unfaithful'
        try:e.chart_export(c['chart_ref'],c['digest'],format='phichain_native');r['native_status']='exported'
        except ValueError as error:r.update(native_status='explicit_compatibility_refusal',native_error=str(error))
    except ValueError as error:r.update(status='explicit_refusal',error=str(error))
    r['timings']['native_or_refusal_seconds']=time.perf_counter()-phase
    r['source_file_unchanged']=path.read_bytes()==original
    report.append(r)
    (BASE/'../research/overnight-study/research/independent-edited-compatibility.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(r,ensure_ascii=False),flush=True)
