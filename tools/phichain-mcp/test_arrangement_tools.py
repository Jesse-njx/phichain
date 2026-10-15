import copy
from pathlib import Path
import tempfile
import unittest

from arrangement_tools import beat_at
from local_tools import LocalTools
from server import Server


class LiveChart:
    def __init__(self, count=0):
        self.revision = 'r0'; self.calls = []; self.batch = 0
        self.notes = [dict(id=str(i+1), line_id='10',
            note=dict(kind='tap', above=True, beat=[i,0,1], x=-100 if i%2 else 100, speed=1))
            for i in range(count)]
        self.context = dict(session='s', revision='r0', selected_line_id='10',
            lines=[dict(id='10')], offset=0, bpm_list=[dict(beat=[0,0,1], bpm=120)],
            audio_duration_seconds=1000)
        self.fail_batch = None; self.transport_batch = None
    def __call__(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == 'get_context':
            return dict(self.context, revision=self.revision)
        if name == 'read_section':
            return dict(session='s', revision=self.revision, notes=copy.deepcopy(self.notes), curve_tracks=[])
        if name == 'apply_edits':
            self.batch += 1
            if self.batch == self.fail_batch:
                return dict(error='Human edit made this chunk stale')
            if args['revision'] != self.revision:
                return dict(error='Stale revision')
            for op in args['operations']:
                if op['op'] == 'update_note':
                    row = next(n for n in self.notes if n['id']==op['id'])
                    row['note'] = copy.deepcopy(op['note'])
                elif op['op'] == 'delete_note':
                    self.notes = [n for n in self.notes if n['id'] != op['id']]
                else:
                    self.notes.append(dict(id=str(100000+len(self.notes)),line_id=op['line_id'],note=copy.deepcopy(op['note'])))
            self.revision = f'r{self.batch}'
            if self.batch == self.transport_batch:
                raise OSError('Connection lost after execution')
            return dict(session='s', revision=self.revision)
        if name == 'validate_chart':
            return dict(session='s', revision=self.revision, valid=True, findings=[])
        if name == 'save':
            return dict(saved=True)
        raise AssertionError(name)


def example(name='A'):
    return dict(name=name,phrases=[dict(duration_seconds=10,events=[
        dict(time_seconds=0,x=[-.2,.2]),dict(time_seconds=.125,x=[.1]),
        dict(time_seconds=9.5,x=[-.1])])],end_chord=[-.2,.2])


class ArrangementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.bridge=LiveChart()
        self.tools=LocalTools(Path(self.tmp.name)/'endpoint',self.bridge)
    def tearDown(self):self.tmp.cleanup()
    def run_tool(self, **kwargs):
        return self.tools.compose_tap_arrangements(session='s',revision='r0',mode=kwargs.pop('mode','replace'),**kwargs)
    def mutations(self):
        return [c for c in self.bridge.calls if c[0] in ('apply_edits','save')]
    def test_seconds_follow_bpm_changes_and_audio_offset(self):
        context=dict(offset=1000,bpm_list=[dict(beat=[0,0,1],bpm=120),dict(beat=[4,0,1],bpm=60)])
        self.assertEqual(beat_at(1,context),[0,0,1])
        self.assertEqual(beat_at(3,context),[4,0,1])
        self.assertEqual(beat_at(4.5,context),[5,1,2])
        with self.assertRaisesRegex(ValueError,'precedes'):beat_at(.5,context)
    def test_generated_spacing_speed_and_three_second_gap(self):
        result=self.run_tool(examples=[example('A'),example('B')],horizontal_scale=1.2,speed_multiplier=1.5,save=True)
        self.assertEqual(result['status'],'applied');self.assertTrue(result['saved'])
        self.assertEqual([e['start_seconds'] for e in result['examples']],[1,14])
        self.assertEqual([e['end_seconds'] for e in result['examples']],[11,24])
        notes=[r['note'] for r in self.bridge.notes]
        self.assertEqual(notes[0]['beat'],[2,0,1]);self.assertEqual(notes[0]['x'],-324)
        self.assertTrue(all(n['kind']=='tap' and n['speed']==1.5 for n in notes))
    def test_bad_last_example_never_deletes_or_creates_notes(self):
        self.bridge.notes=LiveChart(5).notes
        bad=example('Bad');bad['phrases'][0]['events'][-1]['x']=[-.3,0,.3]
        before=copy.deepcopy(self.bridge.notes)
        with self.assertRaisesRegex(ValueError,'max_contacts'):
            self.run_tool(examples=[example(),bad])
        self.assertEqual(before,self.bridge.notes);self.assertEqual(self.mutations(),[])
    def test_merged_onsets_and_existing_append_collisions_are_preflighted(self):
        a=example();a['phrases'][0]['events'].append(dict(time_seconds=0,x=[0]))
        with self.assertRaisesRegex(ValueError,'simultaneous'):self.run_tool(examples=[a])
        self.assertEqual(self.mutations(),[])
        self.bridge.notes=[dict(id='1',line_id='10',note=dict(kind='tap',above=True,beat=[2,0,1],x=-270,speed=1))]
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.run_tool(mode='append',examples=[example()])
        self.assertEqual(self.mutations(),[])
    def test_dry_run_and_stale_guard_do_not_mutate(self):
        result=self.run_tool(examples=[example()],dry_run=True,save=True)
        self.assertEqual(result['status'],'planned');self.assertEqual(self.mutations(),[])
        self.bridge.revision='human'
        with self.assertRaisesRegex(ValueError,'changed'):self.run_tool(examples=[example()])
        self.assertEqual(self.mutations(),[])
    def test_transform_preserves_timing_side_and_outside_range(self):
        self.bridge.notes=LiveChart(4).notes
        self.bridge.notes[1]['note']['above']=False
        before=copy.deepcopy(self.bridge.notes)
        result=self.run_tool(mode='transform',start_beat=1,end_beat=3,horizontal_scale=1.2,speed_multiplier=1.5)
        self.assertEqual(result['notes_planned'],2)
        for i in (1,2):
            self.assertEqual(self.bridge.notes[i]['note']['beat'],before[i]['note']['beat'])
            self.assertEqual(self.bridge.notes[i]['note']['above'],before[i]['note']['above'])
            self.assertEqual(self.bridge.notes[i]['note']['speed'],1.5)
        self.assertEqual(self.bridge.notes[0],before[0]);self.assertEqual(self.bridge.notes[3],before[3])
    def test_offscreen_transform_and_unsupported_kind_are_rejected_before_edits(self):
        self.bridge.notes=LiveChart(1).notes;self.bridge.notes[0]['note']['x']=590
        with self.assertRaisesRegex(ValueError,'note x'):self.run_tool(mode='transform',horizontal_scale=1.2)
        self.bridge.notes[0]['note']['kind']='hold'
        with self.assertRaisesRegex(ValueError,'tap-only'):self.run_tool(mode='transform')
        self.assertEqual(self.mutations(),[])
    def test_multiple_chunks_report_partial_failure_and_never_undo(self):
        self.bridge.notes=LiveChart(1001).notes;self.bridge.fail_batch=2
        result=self.run_tool(mode='transform',speed_multiplier=1.5,save=True)
        self.assertEqual(result['status'],'incomplete');self.assertEqual(result['operations_applied'],1000)
        self.assertEqual(result['undo_steps'],1);self.assertFalse(result['saved'])
        self.assertEqual(self.bridge.notes[999]['note']['speed'],1.5)
        self.assertEqual(self.bridge.notes[1000]['note']['speed'],1)
        self.assertNotIn('history',[c[0] for c in self.bridge.calls])
    def test_transport_failure_is_not_retried(self):
        self.bridge.notes=LiveChart(1001).notes;self.bridge.transport_batch=1
        result=self.run_tool(mode='transform',speed_multiplier=1.5)
        self.assertEqual(result['status'],'incomplete');self.assertEqual(result['batches_applied'],0)
        self.assertEqual(self.bridge.batch,1);self.assertIn('may have executed',result['recovery'])
        self.assertEqual(self.bridge.notes[0]['note']['speed'],1.5)
    def test_tool_is_exposed_and_dispatched_via_mcp(self):
        adapter=Server(str(Path(self.tmp.name)/'endpoint'));adapter.local.bridge=self.bridge
        adapter.dispatch(dict(jsonrpc='2.0',id=0,method='initialize',params=dict(protocolVersion='2025-11-25')))
        response=adapter.dispatch(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(
            name='compose_tap_arrangements',arguments=dict(session='s',revision='r0',mode='replace',examples=[example()],dry_run=True))))
        self.assertFalse(response['result']['isError'])
        self.assertEqual(response['result']['structuredContent']['status'],'planned')


if __name__=='__main__':unittest.main()
