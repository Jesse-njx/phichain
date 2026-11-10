import copy
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import chart_speed as cs


def chart():
    def line(bpm):
        events = [dict(startTime=0,endTime=32,value=2),dict(startTime=32,endTime=48,value=0),
                  dict(startTime=48,endTime=64,value=-1),dict(startTime=64,endTime=80,value=100),
                  dict(startTime=80,endTime=1_000_000_000,value=2)]
        timeline = cs.Scroll(events,bpm)
        for i,e in enumerate(events): e['floorPosition'] = timeline.floors[i]
        return {'bpm':bpm, 'speedEvents':events,
                'notesAbove':[dict(type=1,time=24,holdTime=0,positionX=3,speed=1.2,floorPosition=timeline.floor(24)+0.125),
                              dict(type=3,time=96,holdTime=16,positionX=-2,speed=2,floorPosition=timeline.floor(96))],
                'notesBelow':[dict(type=4,time=128,holdTime=0,positionX=0,speed=1,floorPosition=timeline.floor(128))],
                'judgeLineMoveEvents':[dict(startTime=0,endTime=200,start=0.2,end=0.8,start2=0.1,end2=0.9)],
                'judgeLineRotateEvents':[dict(startTime=0,endTime=200,start=270,end=-80)],
                'judgeLineDisappearEvents':[dict(startTime=-100,endTime=-90,start=0,end=0)]}
    return {'formatVersion':3,'offset':0.123,'judgeLineList':[line(120),line(190)]}


def policy(source):
    return {'multiplier_range':[0.5,2.0],'lines':[{'line':i,'gain':1,'reason':'Synthetic approach'} for i in range(len(source['judgeLineList']))],
            'transparent_tails':True,'review':'Synthetic structural tests; no human review.'}


class MathTests(unittest.TestCase):
    def setUp(self):
        self.base = chart()
        self.policy = policy(self.base)

    def test_identity_and_no_mutation(self):
        original = copy.deepcopy(self.base)
        self.assertEqual(cs.transform(self.base,self.policy,1),self.base)
        cs.transform(self.base,self.policy,1.7)
        self.assertEqual(self.base,original)

    def test_integrals_reverse_stops_and_holds(self):
        out = cs.transform(self.base,self.policy,1.3)
        for old,new in zip(self.base['judgeLineList'],out['judgeLineList']):
            a,b = cs.Scroll(old['speedEvents'],old['bpm']),cs.Scroll(new['speedEvents'],new['bpm'])
            for t in (0,24,32,47,48,63,64,79,80,96,200):
                self.assertAlmostEqual(b.floor(t),1.3*a.floor(t),places=10)
            self.assertEqual(new['speedEvents'][1]['value'],0)
            self.assertEqual(new['speedEvents'][2]['value'],-1.3)
            self.assertEqual(new['notesAbove'][0]['speed'],1.2)
            self.assertAlmostEqual(new['notesAbove'][1]['speed'],2.6)
            self.assertEqual(new['notesBelow'][0]['speed'],1)
            self.assertAlmostEqual(new['notesAbove'][0]['floorPosition']-b.floor(24),0.125)
        cs.verify_invariants(self.base,out)

    def test_event_override_reintegrates_future_distance(self):
        self.policy['lines'][0]['events'] = [{'event':3,'gain':0,'reason':'Preserve instantaneous release speed'}]
        out = cs.transform(self.base,self.policy,1.5)
        old,new = self.base['judgeLineList'][0],out['judgeLineList'][0]
        self.assertEqual(new['speedEvents'][3]['value'],100)
        expected = ((32*2)+(16*-1)+(16*100)+(16*2)) * 1.875/120
        modified = ((32*3)+(16*-1.5)+(16*100)+(16*3)) * 1.875/120
        self.assertAlmostEqual(old['notesAbove'][1]['floorPosition'],expected)
        self.assertAlmostEqual(new['notesAbove'][1]['floorPosition'],modified)

    def test_preserved_window_detects_future_integral_coupling(self):
        self.policy['lines'][0]['events'] = [{'event':0,'gain':0,'reason':'Unchanged local speed'}]
        self.policy['preserve_windows'] = [{'line':0,'side':'notesBelow','note':0,'from':0,'to':16,'reason':'Early choreography'}]
        with self.assertRaisesRegex(cs.ProfileError,'trajectory conflict'):
            cs.transform(self.base,self.policy,1.3)

    def test_preserved_line_is_exact(self):
        self.policy['lines'][0]['gain'] = 0
        self.policy['preserve_windows'] = [{'line':0,'side':'notesAbove','note':1,'from':0,'to':24,'reason':'Held display'}]
        out = cs.transform(self.base,self.policy,1.8)
        self.assertEqual(out['judgeLineList'][0],self.base['judgeLineList'][0])

    def test_hold_body_conflict(self):
        self.policy['preserve_windows'] = [{'line':0,'side':'notesAbove','note':1,'from':0,'to':24,'reason':'Hold display'}]
        with self.assertRaisesRegex(cs.ProfileError,'Hold length conflict'):
            cs.transform(self.base,self.policy,1.3)

    def test_multiplier_boundaries(self):
        for x in (float('nan'),float('inf'),0,-1,0.49,2.01,True):
            with self.subTest(x=x), self.assertRaises(cs.ProfileError):
                cs.transform(self.base,self.policy,x)

    def test_factor_sign_checked_across_range(self):
        self.policy['lines'][0]['gain'] = -2
        with self.assertRaisesRegex(cs.ProfileError,'nonpositive'):
            cs.transform(self.base,self.policy,1)

    def test_complete_and_unambiguous_rules(self):
        for rules in ([self.policy['lines'][0]], [self.policy['lines'][0]]*2):
            p = dict(self.policy,lines=rules)
            with self.assertRaises(cs.ProfileError): cs.transform(self.base,p,1.3)
        self.policy['lines'][0]['events'] = [{'event':99,'gain':0,'reason':'bad'}]
        with self.assertRaises(cs.ProfileError): cs.transform(self.base,self.policy,1.3)

    def test_unsupported_and_bad_speed_ranges(self):
        for version in (1,6,'3'):
            with self.assertRaises(cs.ProfileError): cs.transform(dict(self.base,formatVersion=version),self.policy,1.3)
        self.base['judgeLineList'][0]['speedEvents'][1]['startTime'] += 1
        with self.assertRaisesRegex(cs.ProfileError,'contiguous'):
            cs.transform(self.base,self.policy,1.3)

    def test_opacity_tail_negative_time_and_fade(self):
        self.base['judgeLineList'][1]['judgeLineDisappearEvents'] = [dict(startTime=100,endTime=120,start=1,end=0)]
        fixed,repairs = cs.transparent_tails(self.base)
        self.assertEqual(len(repairs),2)
        self.assertEqual(fixed['judgeLineList'][0]['judgeLineDisappearEvents'][-1]['startTime'],0)
        self.assertEqual(fixed['judgeLineList'][1]['judgeLineDisappearEvents'][-1]['startTime'],120)
        for a,b in zip(self.base['judgeLineList'],fixed['judgeLineList']):
            self.assertEqual(a['judgeLineDisappearEvents'],b['judgeLineDisappearEvents'][:-1])
        self.assertEqual(cs.transparent_tails(fixed),(fixed,[]))

    def test_nonzero_final_opacity_is_not_guessed(self):
        self.base['judgeLineList'][0]['judgeLineDisappearEvents'][-1]['end']=1
        with self.assertRaisesRegex(cs.ProfileError,'not zero'): cs.transparent_tails(self.base)

    def test_hidden_opacity_spanning_zero_already_covers_horizon(self):
        for line in self.base['judgeLineList']:
            line['judgeLineDisappearEvents'] = [dict(startTime=-999999,endTime=1_000_000_000,start=0,end=0)]
        self.assertEqual(cs.transparent_tails(self.base),(self.base,[]))

    def test_zero_duration_source_markers_keep_indices_and_zero_area(self):
        base = copy.deepcopy(self.base)
        events = base['judgeLineList'][0]['speedEvents']
        events.insert(1,dict(startTime=32,endTime=32,value=999,floorPosition=1))
        events.insert(2,dict(startTime=32,endTime=32,value=-7,floorPosition=1))
        a = cs.Scroll(self.base['judgeLineList'][0]['speedEvents'],120)
        b = cs.Scroll(events,120)
        self.assertEqual(b.index(32),3)
        for t in (0,24,31,32,33,64,96):
            self.assertAlmostEqual(a.floor(t),b.floor(t))
        out = cs.transform(base,self.policy,1.3)
        self.assertEqual(len(out['judgeLineList'][0]['speedEvents']),7)
        self.assertEqual(out['judgeLineList'][0]['speedEvents'][1]['startTime'],32)
        self.assertEqual(out['judgeLineList'][0]['speedEvents'][1]['endTime'],32)

    def test_zero_speed_holds_are_preserved_without_relaxing_other_notes(self):
        self.base['judgeLineList'][0]['notesAbove'][1]['speed']=0
        out=cs.transform(self.base,self.policy,1.3)
        self.assertEqual(out['judgeLineList'][0]['notesAbove'][1]['speed'],0)
        self.base['judgeLineList'][0]['notesAbove'][0]['speed']=0
        with self.assertRaisesRegex(cs.ProfileError,'Invalid note speed'):
            cs.validate_chart(self.base)

    def test_individual_note_gain_keeps_shared_staging_and_hold_exact(self):
        p=policy(self.base)
        for r in p['lines']:r['gain']=0
        p['lines'][0]['note_gains']=[{'side':'notesAbove','note':0,'gain':1,'reason':'Reviewed ordinary non-Hold'}]
        p['preserve_windows']=[{'line':0,'side':'notesAbove','note':1,'from':0,'to':96,'reason':'Keep staged Hold exact'}]
        out=cs.transform(self.base,p,1.5)
        expected=copy.deepcopy(self.base)
        expected['judgeLineList'][0]['notesAbove'][0]['speed']*=1.5
        self.assertEqual(out,expected)
        cs.verify_invariants(self.base,out,p)
        with self.assertRaisesRegex(cs.ProfileError,'Non-scroll fields'):
            cs.verify_invariants(self.base,out)

    def test_per_note_gain_cannot_silently_change_a_protected_trajectory(self):
        p=policy(self.base)
        for r in p['lines']:r['gain']=0
        p['lines'][0]['note_gains']=[{'side':'notesAbove','note':0,'gain':1,'reason':'Conflict fixture'}]
        p['preserve_windows']=[{'line':0,'side':'notesAbove','note':0,'from':0,'to':16,'reason':'Must remain original'}]
        with self.assertRaisesRegex(cs.ProfileError,'trajectory conflict'):
            cs.transform(self.base,p,1.5)

    def test_note_gains_reject_holds_duplicate_addresses_and_double_scaling(self):
        p=policy(self.base)
        p['lines'][0]['note_gains']=[{'side':'notesAbove','note':0,'gain':1,'reason':'Fixture'}]
        with self.assertRaisesRegex(cs.ProfileError,'unchanged line'):
            cs.validate_policy(p,self.base)
        p['lines'][0]['gain']=0
        p['lines'][0]['note_gains'][0]['note']=1
        with self.assertRaisesRegex(cs.ProfileError,'Hold head'):
            cs.validate_policy(p,self.base)
        p['lines'][0]['note_gains'][0]['note']=0
        p['lines'][0]['note_gains']*=2
        with self.assertRaisesRegex(cs.ProfileError,'Duplicate per-note'):
            cs.validate_policy(p,self.base)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root/'profiles'
        self.source = self.root/'original.json'
        self.source.write_bytes(cs.json_bytes(chart()))
        (self.root/'music.ogg').write_bytes(b'synthetic asset bytes')
        (self.root/'cover.png').write_bytes(b'synthetic image bytes')
        self.recipe = {'schema_version':1,'id':'fixture','name':'Fixture AT','aliases':['Test song'],
                       'source':'original.json','source_sha256':cs.digest(self.source.read_bytes()),
                       'music':'music.ogg','illustration':'cover.png','metadata':{'charter':'Original credit','level':'AT'},
                       'policy':policy(chart())}
        self.recipe_path = self.root/'recipe.json'
        self.recipe_path.write_bytes(cs.json_bytes(self.recipe))

    def compile(self):
        return cs.compile_profile(self.recipe_path,self.registry)

    def test_compile_identity_and_repeated_generation(self):
        bundle,manifest = self.compile()
        self.assertEqual(manifest['notes'],6)
        output = self.root/'one.json'
        cs.generate('test SONG',1,self.registry,output)
        self.assertEqual(output.read_bytes(),(bundle/'baseline.json').read_bytes())
        cs.generate('fixture',2,self.registry,self.root/'two.json')
        cs.generate('Fixture AT',1.3,self.registry,self.root/'a.json')
        cs.generate('Fixture AT',1.3,self.registry,self.root/'b.json')
        self.assertEqual((self.root/'a.json').read_bytes(),(self.root/'b.json').read_bytes())
        self.assertEqual(cs.digest(self.source.read_bytes()),self.recipe['source_sha256'])

    def test_deterministic_package_and_credits(self):
        self.compile()
        for name in ('a.pez','b.pez'):
            cs.generate('fixture',1.5,self.registry,self.root/name)
        self.assertEqual((self.root/'a.pez').read_bytes(),(self.root/'b.pez').read_bytes())
        with zipfile.ZipFile(self.root/'a.pez') as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read('music.ogg'),b'synthetic asset bytes')
            self.assertIn(b'Original credit',z.read('info.yml'))
            self.assertEqual(len(json.loads(z.read('chart.json'))['judgeLineList']),2)

    def test_source_and_bundle_hash_guards(self):
        self.source.write_bytes(self.source.read_bytes()+b' ')
        with self.assertRaisesRegex(cs.ProfileError,'source hash'): self.compile()
        self.source.write_bytes(self.source.read_bytes()[:-1])
        bundle,_ = self.compile()
        (bundle/'baseline.json').write_bytes((bundle/'baseline.json').read_bytes()+b' ')
        with self.assertRaisesRegex(cs.ProfileError,'asset hash'):
            cs.generate('fixture',1.3,self.registry,self.root/'out.json')
        self.assertFalse((self.root/'out.json').exists())

    def test_dry_run_and_no_clobber(self):
        self.compile()
        out = self.root/'missing'/'out.pez'
        report = cs.generate('fixture',1.3,self.registry,out,dry_run=True)
        self.assertTrue(report['dry_run'])
        self.assertFalse(out.parent.exists())
        cs.generate('fixture',1.3,self.registry,out)
        data = out.read_bytes()
        with self.assertRaisesRegex(cs.ProfileError,'Output exists'):
            cs.generate('fixture',1.5,self.registry,out)
        self.assertEqual(out.read_bytes(),data)
        cs.generate('fixture',1.5,self.registry,out,force=True)
        self.assertNotEqual(out.read_bytes(),data)

    def test_same_command_reuses_identical_output_without_rewriting(self):
        self.compile()
        out = self.root/'same.pez'
        first = cs.generate('fixture',1.3,self.registry,out)
        stamp = out.stat().st_mtime_ns
        again = cs.generate('fixture',1.3,self.registry,out)
        self.assertFalse(first['reused'])
        self.assertTrue(again['reused'])
        self.assertEqual(stamp,out.stat().st_mtime_ns)
        self.assertEqual(first['output_sha256'],again['output_sha256'])

    def test_input_protection_including_hardlinks(self):
        bundle,_ = self.compile()
        for out in (self.source,bundle/'baseline.json'):
            with self.subTest(out=out), self.assertRaises(cs.ProfileError):
                cs.generate('fixture',1.3,self.registry,out,force=True)
        alias = self.root/'alias.json'
        os.link(self.source,alias)
        with self.assertRaisesRegex(cs.ProfileError,'original chart'):
            cs.generate('fixture',1.3,self.registry,alias,force=True)

    def test_duplicate_profile_and_alias_ambiguity(self):
        self.compile()
        with self.assertRaisesRegex(cs.ProfileError,'already exists'): self.compile()
        recipe = dict(self.recipe,id='second')
        self.recipe_path.write_bytes(cs.json_bytes(recipe))
        self.compile()
        with self.assertRaisesRegex(cs.ProfileError,'found 2'):
            cs.generate('Test song',1.3,self.registry,self.root/'out.json')

    def test_protected_phase_rejected_at_compile(self):
        self.recipe['policy']['preserve_windows'] = [{'line':0,'side':'notesBelow','note':0,'from':0,'to':24,'reason':'Protect animation'}]
        self.recipe_path.write_bytes(cs.json_bytes(self.recipe))
        with self.assertRaisesRegex(cs.ProfileError,'trajectory conflict'): self.compile()
        self.assertFalse((self.registry/'fixture').exists())


class ReviewedRuleTests(unittest.TestCase):
    def test_raw_identity_does_not_parse_validate_transform_or_repair(self):
        raw = b'\xef\xbb\xbf  original unsupported chart bytes\r\n'
        with mock.patch.object(cs,'decode',side_effect=AssertionError('parsed')), \
             mock.patch.object(cs,'validate_chart',side_effect=AssertionError('validated')), \
             mock.patch.object(cs,'transform',side_effect=AssertionError('transformed')), \
             mock.patch.object(cs,'transparent_tails',side_effect=AssertionError('repaired')):
            self.assertIs(cs.apply_reviewed_rule(raw,b'invalid rule',1),raw)
            self.assertIs(cs.apply_reviewed_rule(raw,None,1),raw)

    def test_reviewed_source_hash_and_nonidentity_transformation(self):
        raw = cs.json_bytes(chart())
        p = policy(chart())
        p['transparent_tails'] = False
        rule = cs.json_bytes({'schema_version':1,'source_sha256':cs.digest(raw),'policy':p})
        out = cs.decode(cs.apply_reviewed_rule(raw,rule,1.3))
        cs.verify_invariants(chart(),out)
        self.assertAlmostEqual(out['judgeLineList'][0]['speedEvents'][0]['value'],2.6)
        with self.assertRaisesRegex(cs.ProfileError,'source hash'):
            cs.apply_reviewed_rule(raw+b' ',rule,1.3)
        with self.assertRaisesRegex(cs.ProfileError,'rule is required'):
            cs.apply_reviewed_rule(raw,None,1.3)

    def test_file_identity_without_rule_and_input_alias_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source,output = root/'original.json',root/'out.json'
            source.write_bytes(b'untouched raw original')
            result = cs.apply_file(source,root/'missing-rule.json',1,output)
            self.assertEqual(output.read_bytes(),source.read_bytes())
            self.assertTrue(result['original_byte_bypass'])
            self.assertTrue(cs.apply_file(source,None,1,output)['reused'])
            alias = root/'alias.json'
            os.link(source,alias)
            with self.assertRaisesRegex(cs.ProfileError,'original chart'):
                cs.apply_file(source,None,1,alias,True)


class ApproachReplayTests(unittest.TestCase):
    def fixture(self):
        base=chart()
        line=base['judgeLineList'][0]
        extra=copy.deepcopy(line['notesAbove'][1])
        extra.update(type=1,holdTime=0,speed=1,positionX=1)
        line['notesAbove'].append(extra)
        line['numOfNotes']=4
        line['numOfNotesAbove']=3
        line['numOfNotesBelow']=1
        line['judgeLineDisappearEvents']=[dict(startTime=0,endTime=72,start=-1,end=-1),dict(startTime=72,endTime=1_000_000_000,start=1,end=1)]
        raw=cs.json_bytes(base)
        rule={'schema_version':2,'source_sha256':cs.digest(raw),'multiplier_range':[1,2],
              'plans':[{'line':0,'whole_line':False,'direct':[{'side':'notesAbove','note':0}],
                        'helpers':[{'side':'notesAbove','note':1,'start':80,'visible_from':0},
                                   {'side':'notesAbove','note':2,'start':80,'visible_from':0}],
                        'preserve':[{'side':'notesBelow','note':0}],'reason':'Synthetic mixed carrier'},
                       {'line':1,'whole_line':True,'direct':[],'helpers':[],'preserve':[],
                        'reason':'Synthetic ordinary carrier'}]}
        return base,raw,rule

    def test_grouped_helper_replays_path_and_retains_judgment_contact_and_opacity(self):
        base,raw,rule=self.fixture()
        ap=cs.approach_module()
        source=base['judgeLineList'][0]
        oldscroll=cs.Scroll(source['speedEvents'],source['bpm'])
        for x in (1.1,1.25,1.3,1.5,2):
            out=cs.decode(cs.apply_reviewed_rule(raw,cs.json_bytes(rule),x))
            self.assertEqual(len(out['judgeLineList']),3)
            self.assertEqual(sum(len(l[s])for l in out['judgeLineList']for s in cs.SIDES),7)
            unchanged,helper=out['judgeLineList'][0],out['judgeLineList'][2]
            self.assertEqual(unchanged['notesBelow'],source['notesBelow'])
            self.assertEqual(unchanged['speedEvents'],source['speedEvents'])
            for channel in cs.ANIMATIONS:self.assertEqual(unchanged[channel],source[channel])
            self.assertEqual(unchanged['numOfNotes'],2)
            self.assertEqual(helper['numOfNotes'],2)
            self.assertEqual(helper['notesAbove'][0],source['notesAbove'][1])
            self.assertEqual(helper['notesAbove'][1],source['notesAbove'][2])
            self.assertTrue(all(e['start']<=0 and e['end']<=0 for e in helper['judgeLineDisappearEvents']))
            newscroll=cs.Scroll(helper['speedEvents'],helper['bpm'])
            begin=96-16/x
            for t in (0,24,71,79,80,(80+begin)/2,(begin+96)/2,96,104,112):
                expected=t if t<80 or t>=96 else (80 if t<begin else 96+x*(t-96))
                self.assertAlmostEqual(newscroll.floor(t),oldscroll.floor(expected),places=9)
                for name,pairs in [('judgeLineMoveEvents',[('start','end'),('start2','end2')]),('judgeLineRotateEvents',[('start','end')])]:
                    actual=ap.Channel(helper[name],pairs).at(t)
                    wanted=ap.Channel(source[name],pairs).at(expected)
                    for a,b in zip(actual,wanted):self.assertAlmostEqual(a,b,places=9)
            self.assertEqual(ap.Channel(helper['judgeLineDisappearEvents'],[('start','end')]).at(24),(-1,))
        self.assertEqual(cs.json_bytes(base),raw)

    def test_replay_plan_is_complete_pinned_and_raw_at_one(self):
        base,raw,rule=self.fixture()
        self.assertIs(cs.apply_reviewed_rule(raw,b'invalid rule',1),raw)
        with self.assertRaisesRegex(cs.ProfileError,'source hash'):
            cs.apply_reviewed_rule(raw+b' ',cs.json_bytes(rule),1.3)
        rule['plans'][0]['preserve']=[]
        with self.assertRaisesRegex(cs.ProfileError,'every original note'):
            cs.apply_reviewed_rule(raw,cs.json_bytes(rule),1.3)

    def test_legacy_backwards_zero_opacity_is_preserved_and_helpers_stay_hidden(self):
        base,_,rule=self.fixture()
        events=[dict(startTime=0,endTime=72,start=1,end=1),
                dict(startTime=90,endTime=80,start=0,end=0),
                dict(startTime=80,endTime=1_000_000_000,start=1,end=1)]
        base['judgeLineList'][0]['judgeLineDisappearEvents']=events
        raw=cs.json_bytes(base);rule['source_sha256']=cs.digest(raw)
        out=cs.decode(cs.apply_reviewed_rule(raw,cs.json_bytes(rule),1.25))
        self.assertEqual(out['judgeLineList'][0]['judgeLineDisappearEvents'],events)
        self.assertEqual(out['judgeLineList'][2]['judgeLineDisappearEvents'],
                         [dict(startTime=0,endTime=1_000_000_000,start=0,end=0)])
        self.assertIs(cs.apply_reviewed_rule(raw,None,1),raw)
        for value in (-1,1):
            events[1]['start']=events[1]['end']=value
            with self.assertRaisesRegex(cs.ProfileError,'reversed animation'):
                cs.validate_chart(base)


if __name__ == '__main__':
    unittest.main()
