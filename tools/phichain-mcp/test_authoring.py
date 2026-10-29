import copy
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_server
import authoring
import server


def document():
    return {'lines':{'10':{'name':'Line','role':'simple','order':0,'parent_id':None}},
        'notes':{'20':{'line_id':'10','note':{'kind':'tap','above':True,'beat':[4,0,1],'x':120,'speed':1}},
                 '21':{'line_id':'10','note':{'kind':'hold','hold_beat':[2,0,1],'above':True,'beat':[8,0,1],'x':-60,'speed':1}}},
        'events':{},'curve_tracks':{},'meta':{'name':'Test','composer':'','charter':'','illustrator':'','level':''},
        'bpm_list':[{'beat':[0,0,1],'bpm':120}],'offset':500}


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.live=document(); self.calls=[]; self.revision='r'
        self.adapter=agent_server.AgentServer('unused')
        self.adapter.dispatch({'jsonrpc':'2.0','id':0,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
    def bridge(self,endpoint,name,args):
        self.calls.append((name,args))
        if name=='get_context':return {'session':'s','revision':self.revision,'lines':[{'id':'10'}]}
        if name=='authoring_read':
            if args!={'session':'s','revision':self.revision}:return {'error':'stale'}
            return {'session':'s','revision':self.revision,'document':copy.deepcopy(self.live)}
        if name=='authoring_commit':
            if args['revision']!=self.revision:return {'error':'stale'}
            if not args['dry_run']: self.live=copy.deepcopy(args['document']); self.revision+='1'
            return {'session':'s','revision':self.revision,'undo_steps':0 if args['dry_run'] else 1,'changes':[]}
        return {'session':'s','revision':self.revision}
    def call(self,name,args):
        with patch.object(server,'call_editor',side_effect=self.bridge):
            return self.adapter.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})['result']
    def write(self,name,**args):
        return self.call(name,{'session':'s','revision':self.revision,'dry_run':False,**args})
    def test_partial_patch_preserves_unrequested_fields_and_commits_once(self):
        old=copy.deepcopy(self.live['notes']['21'])
        result=self.write('chart_patch',operations=[{'op':'set','path':'/notes/20/note/x','value':-120}])
        self.assertFalse(result['isError'],result)
        self.assertEqual(self.live['notes']['20']['note']['x'],-120)
        self.assertEqual(self.live['notes']['21'],old)
        self.assertEqual([n for n,_ in self.calls],['authoring_read','authoring_commit'])
    def test_dry_run_and_stale_state_do_not_commit(self):
        original=copy.deepcopy(self.live)
        result=self.call('chart_patch',{'session':'s','revision':'r','dry_run':True,'operations':[{'op':'set','path':'/notes/20/note/x','value':0}]})
        self.assertFalse(result['isError']);self.assertEqual(self.live,original)
        result=self.call('chart_patch',{'session':'s','revision':'old','dry_run':False,'operations':[{'op':'set','path':'/notes/20/note/x','value':0}]})
        self.assertTrue(result['isError']);self.assertEqual(self.live,original)
    def test_note_ordinal_query_is_exact_and_beat_sort_uses_values(self):
        args={'session':'s','revision':'r','collection':'notes','sort':'/note/beat','limit':1}
        result=self.call('chart_query',args)
        self.assertEqual(result['structuredContent']['items'][0]['id'],'20')
        self.assertEqual(result['structuredContent']['total'],2)
        args.update(start=9,end=10)
        result=self.call('chart_query',args)
        self.assertEqual(result['structuredContent']['items'][0]['id'],'21')
    def test_new_line_and_note_are_one_candidate(self):
        result=self.write('chart_patch',operations=[{'op':'insert','path':'/lines/new:carrier','value':{'name':'Carrier','role':'complex','parent_id':None,'order':1}}, {'op':'set','path':'/notes/20/line_id','value':'new:carrier'}])
        self.assertFalse(result['isError']); self.assertEqual(self.live['notes']['20']['line_id'],'new:carrier')
        self.assertEqual(len([n for n,_ in self.calls if n=='authoring_commit']),1)
        defaults={r['event']['kind']:r['event']['value']['value'] for r in self.live['events'].values() if r['line_id']=='new:carrier'}
        self.assertEqual(defaults,{'x':0,'y':0,'rotation':0,'opacity':255,'speed':10})
    def test_duplicate_remaps_subtree_notes_and_curve_endpoints(self):
        self.live['curve_tracks']['30']={'line_id':'10','from_id':'20','to_id':'21','options':{'kind':'drag','density':16,'curve':{'type':'linear'}}}
        result=self.write('line_manage',action='duplicate',line_id='10',alias='new:copy')
        self.assertFalse(result['isError'],result)
        track=self.live['curve_tracks']['new:copy:curve_tracks:30']
        self.assertEqual(track['from_id'],'new:copy:notes:20');self.assertEqual(track['line_id'],'new:copy')
        self.assertEqual(self.live['notes']['20']['line_id'],'10')
    def test_invalid_schema_and_actions_never_reach_editor(self):
        for name,args in [('chart_patch',{'operations':[]}),('line_manage',{'action':'create'}),('chart_transform',{'path':'/notes','expressions':{'/note/x':5}})]:
            result=self.write(name,**args);self.assertTrue(result['isError'],result)
        self.assertEqual(self.calls,[])
    def test_bad_pointer_batch_is_atomic(self):
        before=copy.deepcopy(self.live)
        result=self.write('chart_patch',operations=[{'op':'set','path':'/notes/20/note/x','value':0},{'op':'set','path':'/missing/a','value':1}])
        self.assertTrue(result['isError']);self.assertEqual(self.live,before)
        self.assertNotIn('authoring_commit',[n for n,_ in self.calls])
    def test_malformed_candidate_does_not_crash_server_or_commit(self):
        for bad in [None,42,[]]:
            result=self.write('chart_patch',operations=[{'op':'insert','path':'/events/new:bad','value':{'line_id':'10','event':bad}}])
            self.assertTrue(result['isError'],result)
        self.assertNotIn('authoring_commit',[n for n,_ in self.calls])
        self.assertFalse(self.call('editor_context',{})['isError'])
    def test_discovery_lists_real_schemas_without_hidden_activation(self):
        result=self.call('agent_tools',{'names':['chart_script']})
        self.assertEqual([t['name'] for t in result['structuredContent']['tools']],['chart_script'])
        self.assertEqual(self.calls,[])
    def test_actual_agent_stdio_entrypoint_advertises_both_flavours(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        process=subprocess.run([sys.executable,str(Path(__file__).with_name('agent_server.py')),'--endpoint','missing'],input='\n'.join(map(json.dumps,requests))+'\n',capture_output=True,text=True,check=True)
        tools=json.loads(process.stdout.splitlines()[1])['result']['tools']
        self.assertEqual({t['name'] for t in tools},set(agent_server.BY_NAME))
        self.assertIn('chart_script',{t['name'] for t in tools});self.assertIn('inspect_motion',{t['name'] for t in tools})


@unittest.skipUnless(shutil.which('node'),'Node.js required')
class ComputationTests(unittest.TestCase):
    def test_transform_batches_native_values_and_keeps_hold_timing(self):
        doc=document(); original=copy.deepcopy(doc)
        output=authoring.compute('transform',doc,{'path':'/notes','expressions':{'/note/x':'-x','/note/beat':'beat+0.25'}})
        self.assertEqual(output['document']['notes']['20']['note']['x'],-120)
        self.assertEqual(output['document']['notes']['21']['note']['beat'],[8,1,4])
        self.assertEqual(output['document']['notes']['21']['note']['hold_beat'],[2,0,1])
        self.assertEqual(doc,original)
    def test_generate_sequence_and_canonical_beats(self):
        output=authoring.compute('generate',document(),{'path':'/notes','count':41,'template':agent_server.templates()['note']|{'line_id':'10'},'expressions':{'/note/beat':'i/3','/note/x':'100*sin(u*pi)'}})
        self.assertEqual(len(output['result']['aliases']),41)
        self.assertEqual(len(output['document']['notes']),43)
        self.assertEqual(output['document']['notes']['new:generated:0']['note']['beat'],[0,0,1])
    def test_script_moves_existing_id_and_creates_dependent_objects(self):
        source='chart.lines["new:carrier"] = api.createLine("Carrier",1); chart.notes["20"].line_id = "new:carrier"; chart.notes[api.id("tap")]={line_id:"new:carrier",note:api.createNote("tap",12,50)}; api.report({moved:1});'
        output=authoring.compute('script',document(),{'source':source})
        self.assertEqual(output['document']['notes']['20']['line_id'],'new:carrier')
        self.assertEqual(output['result'],[{'moved':1}])
    def test_script_has_no_host_apis_and_constructor_escape_is_blocked(self):
        for source in ['return {result: typeof process + ":" + typeof require + ":" + typeof fetch};', 'return {result: chart.constructor.constructor("return process")()};']:
            if 'constructor' in source:
                with self.assertRaises(ValueError):authoring.compute('script',document(),{'source':source})
            else:self.assertEqual(authoring.compute('script',document(),{'source':source})['result'],'undefined:undefined:undefined')
    def test_timeout_and_expression_injection_return_without_mutation(self):
        doc=document()
        with self.assertRaisesRegex(ValueError,'timed out'):authoring.compute('script',doc,{'source':'while(true){}','timeout_ms':100})
        for expression in ['process.exit()','1/0','constructor.constructor("return process")()']:
            with self.assertRaises(ValueError):authoring.compute('transform',doc,{'path':'/notes','expressions':{'/note/x':expression}})
        self.assertEqual(doc,document())


if __name__=='__main__':unittest.main()
