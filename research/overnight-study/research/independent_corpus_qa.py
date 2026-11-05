"""Read-only official source regression; writes only its study report."""
import gc
import hashlib
import json
from pathlib import Path
import time
from phigros_chart_mcp.core import Engine

BASE = Path('/Users/jesse/Projects/PhiChain/phichain')
REPORT = BASE / '../research/overnight-study/research/independent-corpus-import.json'
results = []
core_path = Path('/Users/jesse/Projects/phigros-chart-mcp/src/phigros_chart_mcp/core.py')
core_sha = hashlib.sha256(core_path.read_bytes()).hexdigest()
for manifest in ['manifest.json', 'supplemental-manifest.json']:
    for row in json.loads((BASE / '../research/overnight-study/corpus' / manifest).read_text()):
        path = BASE / row['chart']['path']
        start = time.perf_counter()
        engine = Engine()
        result = dict(title=row['title'], difficulty=row['difficulty'], core_sha256=core_sha)
        try:
            source_bytes = path.read_bytes()
            source = json.loads(source_bytes)
            chart = engine.chart_import(str(path))
            exported = engine.chart_export(chart['chart_ref'], chart['digest'])['chart']
            result['status'] = 'pass' if exported == source else 'different'
            result['source_unchanged'] = path.read_bytes() == source_bytes
            result['raw_note_count'] = sum(len(l['notesAbove']) + len(l['notesBelow']) for l in source['judgeLineList'])
        except Exception as error:
            result.update(status='error', error=str(error))
        result['elapsed_seconds'] = time.perf_counter() - start
        results.append(result)
        REPORT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(len(results), result['status'], row['title'], flush=True)
        del engine
        gc.collect()
print('Total', len(results), 'pass', sum(r['status'] == 'pass' for r in results))
