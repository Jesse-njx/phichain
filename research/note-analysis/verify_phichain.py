"""Read-only full import verification and bounded native render sampling."""
import json
from pathlib import Path
import sys

ROOT = Path('/Users/jesse/Projects/PhiChain/phichain')
sys.path.insert(0, str(ROOT / 'tools/phichain-mcp'))
import server
import motion
from agent_server import AgentServer

folder = Path(__file__).parent
endpoint = folder / 'override-phichain-endpoint.json'
receipt = json.loads((folder / 'override-phichain-import.json').read_text())
adapter = AgentServer(endpoint)
bridge = lambda name, args: server.call_editor(endpoint, name, args)
context = bridge('get_context', {})
guards = {k: context[k] for k in ('session', 'revision')}
snapshot = bridge('authoring_read', guards)['document']
errors, type_errors = [], []
for item in receipt['note_index']:
    source = receipt['decisions'][item['decision_id']]
    note = snapshot['notes'][item['native_note_id']]['note']
    beat = lambda b: b[0] + b[1] / b[2]
    assert snapshot['bpm_list'] == [{'beat': [0, 0, 1], 'bpm': 120.0}]
    t = beat(note['beat']) / 2
    errors.append(abs(t - source['time_seconds']))
    if note['kind'] == 'hold':
        errors.append(abs(t + beat(note['hold_beat']) / 2 - source['end_seconds']))
    if note['kind'] != source['suggested_type']:
        type_errors.append(item['native_note_id'])
assert not type_errors
assert len(snapshot['notes']) == 1424 and len(snapshot['lines']) == 4
assert max(errors) < .00006
chosen = [r['native_note_id'] for r in receipt['note_index']
          if 48.0 <= receipt['decisions'][r['decision_id']]['time_seconds'] < 49.6][:32]
data, _ = motion.inspect(bridge, {**guards, 'note_ids': chosen, 'from_seconds': 48,
                                'to_seconds': 49.8, 'frames': 6},
                         str(ROOT / 'target/debug/phichain-renderer'))
result = {'note_count': len(snapshot['notes']), 'line_count': len(snapshot['lines']),
          'max_head_or_tail_error_seconds': max(errors), 'note_types_preserved': True,
          'native_inspection': data['report_path'], 'live_revision_changed': data['live_revision_changed'],
          'inspection_note_ids': chosen, 'scope': 'Native sampled render and full timestamp/type correspondence; diagnostic layout, not playability approval.'}
(folder / 'override-phichain-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
# Leave the experiment paused at a useful dense passage, without opening reports.
current = bridge('get_context', {})
latest = {k: current[k] for k in guards}
print(adapter.execute('editor_view', {**latest, 'ids': [], 'line_id': min(current['lines'], key=lambda l:l['order'])['id']}))
print(adapter.execute('editor_navigate', {**latest, 'unit': 'audio_seconds', 'value': 48, 'action': 'pause'}))
