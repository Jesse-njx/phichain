import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import motion


class MotionTests(unittest.TestCase):
    def test_guard_failure_does_not_start_render_or_write_files(self):
        with patch.object(motion, 'executable') as exe:
            self.assertEqual(motion.inspect(lambda *_: {'error':'stale'}, {}), ({'error':'stale'}, []))
            exe.assert_not_called()

    def test_snapshot_pipeline_offset_frames_assets_and_stale_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            song = root/'song.ogg'; song.write_bytes(b'music')
            data = {'session':'s','revision':'r','limitations':[],
                    '_render_snapshot':{'chart':{'offset':500},'meta':{},'music_path':str(song)},
                    'frames':[{'time_seconds':t+.5,'chart_time_seconds':t,'notes':[],'lines':[]} for t in [1,2]]}
            bridge=Mock(side_effect=[copy.deepcopy(data),{'session':'s','revision':'changed'}])
            commands=[]
            def run(argv, env, timeout=90):
                commands.append(argv)
                if argv[0]=='/renderer':
                    project=Path(argv[1]);self.assertEqual((project/'music.ogg').read_bytes(),b'music')
                    self.assertEqual(json.loads((project/'chart.json').read_text())['offset'],500)
                    self.assertEqual(argv[argv.index('--from')+1],'1')
                    Path(argv[argv.index('-o')+1]).write_bytes(b'video')
                else:
                    Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\nframe')
            with patch.object(motion,'executable',side_effect=['/renderer','/ffmpeg']), patch.object(motion,'run',side_effect=run):
                result,images=motion.inspect(bridge,{'revision':'r'},output_root=root/'output')
            self.assertEqual(len(images),2)
            self.assertNotIn('_render_snapshot',result)
            self.assertTrue(result['live_revision_changed'])
            self.assertTrue(Path(result['report_path']).exists())
            self.assertIn('select=eq(n\\,30)',commands[-1])
            self.assertEqual([c.args[0] for c in bridge.call_args_list],['inspect_motion','get_context'])
            self.assertFalse(Path(commands[0][1]).exists())

    def test_render_failure_cleans_up_and_never_mutates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);song=root/'music.ogg';song.write_bytes(b'music')
            data={'_render_snapshot':{'chart':{},'meta':{},'music_path':str(song)},
                  'frames':[{'chart_time_seconds':1},{'chart_time_seconds':2}]}
            bridge=Mock(return_value=data)
            with patch.object(motion,'executable',side_effect=['/renderer','/ffmpeg']), patch.object(motion,'run',side_effect=ValueError('GPU unavailable')):
                with self.assertRaisesRegex(ValueError,'GPU unavailable'):
                    motion.inspect(bridge,{},output_root=root/'output')
            self.assertEqual(list((root/'output').iterdir()),[])
            self.assertEqual(bridge.call_count,1)

    def test_passage_snapshot_offset_video_and_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); song=root/'song.ogg';song.write_bytes(b'music')
            context={'session':'s','revision':'r','offset':500,'audio_duration_seconds':10}
            snap={'chart':{},'meta':{},'music_path':str(song)}
            bridge=Mock(side_effect=[context,snap,{'session':'s','revision':'changed'}])
            commands=[]
            def render(argv,env):
                commands.append(argv)
                self.assertEqual(argv[argv.index('--from')+1],'0.5')
                self.assertEqual(argv[argv.index('--to')+1],'2.5')
                Path(argv[argv.index('-o')+1]).write_bytes(b'video')
            args={'session':'s','revision':'r','from_seconds':1,'to_seconds':3}
            with patch.object(motion,'executable',side_effect=['/renderer','/ffmpeg']),patch.object(motion,'run',side_effect=render):
                result=motion.preview_passage(bridge,args,output_root=root/'output')
            self.assertTrue(result['live_revision_changed'])
            self.assertIn('controls loop',Path(result['report_path']).read_text())
            self.assertFalse(Path(commands[0][1]).exists())
            self.assertEqual([c.args[0] for c in bridge.call_args_list],['get_context','project_snapshot','get_context'])

    def test_passage_rejects_invalid_ranges_stale_and_capture_failure(self):
        args={'session':'s','revision':'r','from_seconds':1,'to_seconds':3}
        with patch.object(motion,'executable') as exe:
            for changes in [{'from_seconds':4},{'to_seconds':20},{'from_seconds':float('nan')}]:
                with self.assertRaises(ValueError):motion.preview_passage(Mock(),{**args,**changes})
            with self.assertRaisesRegex(ValueError,'changed'):
                motion.preview_passage(Mock(return_value={'session':'s','revision':'changed'}),args)
            bridge=Mock(side_effect=[{'session':'s','revision':'r','offset':0,'audio_duration_seconds':10},{'error':'stale'}])
            self.assertEqual(motion.preview_passage(bridge,args),{'error':'stale'})
            exe.assert_not_called()
