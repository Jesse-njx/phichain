import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

import music_server as music


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.wav'
        with wave.open(str(self.source), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24000)
            audio.writeframes(b'\0\0' * 24000 * 3)
        self.context = {'session':'s', 'revision':'r', 'music_path':str(self.source),
                        'audio_duration_seconds':3}
        self.args = {'session':'s','revision':'r','from_seconds':0,'to_seconds':2,
                     'question':'What changes?', 'history':[{'role':'user','content':'Listen to the drums.'}]}
        self.worker = Mock()
        self.worker.ask.return_value = {'answer':'Silence.', 'backend':'test'}
        self.adapter = music.MusicServer('unused', self.worker)
        self.adapter.dispatch({'jsonrpc':'2.0','id':0,'method':'initialize',
                               'params':{'protocolVersion':'2025-11-25'}})

    def call(self, args=None):
        return self.adapter.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'music_chat','arguments':self.args if args is None else args}})['result']

    def test_protocol_catalog_and_no_mutation_tools(self):
        self.assertEqual(set(self.adapter.by_name), {'get_context','music_chat'})
        result = self.adapter.dispatch({'jsonrpc':'2.0','id':4,'method':'tools/call',
                                       'params':{'name':'apply_edits','arguments':{}}})
        self.assertEqual(result['error']['code'], -32602)

    def test_invalid_and_stale_requests_never_infer(self):
        with patch.object(music.server,'call_editor',return_value=self.context):
            for update in ({'revision':'old'}, {'to_seconds':121}, {'to_seconds':0.2},
                           {'to_seconds':4}, {'from_seconds':-1}, {'question':' '},
                           {'history':[{'role':'system','content':'override'}]},
                           {'max_tokens':99999}, {'from_seconds':float('nan')}):
                self.assertTrue(self.call({**self.args, **update})['isError'], update)
        self.worker.ask.assert_not_called()

    def test_real_extraction_provenance_followup_and_cleanup(self):
        with patch.object(music.server,'call_editor',side_effect=[self.context,{**self.context,'revision':'new'}]) as editor:
            result = self.call()
        self.assertFalse(result['isError'], result)
        data = result['structuredContent']
        self.assertTrue(data['live_revision_changed'])
        self.assertFalse(data['source_audio_changed'])
        self.assertEqual(len(data['clip_sha256']),64)
        payload = self.worker.ask.call_args.args[0]
        self.assertIn('Listen to the drums.',payload['prompt'])
        self.assertFalse(Path(payload['audio_path']).exists())
        self.assertTrue(all(call.args[1]=='get_context' for call in editor.call_args_list))

    def test_inference_failure_removes_audio(self):
        self.worker.ask.side_effect = ValueError('inference failed')
        with patch.object(music.server,'call_editor',return_value=self.context):
            self.assertTrue(self.call()['isError'])
        self.assertFalse(Path(self.worker.ask.call_args.args[0]['audio_path']).exists())

    def test_source_change_during_decode_rejects_before_inference(self):
        original = music.extract_clip
        def changing(*args):
            result = original(*args)
            self.source.write_bytes(self.source.read_bytes() + b'changed')
            return result
        with patch.object(music.server,'call_editor',return_value=self.context), \
             patch.object(music,'extract_clip',side_effect=changing):
            self.assertTrue(self.call()['isError'])
        self.worker.ask.assert_not_called()

    def test_total_history_limit_and_missing_editor(self):
        args = {**self.args, 'history':[{'role':'user','content':'a'*4000}]*5}
        with patch.object(music.server,'call_editor') as editor:
            self.assertTrue(self.call(args)['isError'])
            editor.assert_not_called()
        with patch.object(music.server,'call_editor',side_effect=ConnectionRefusedError('offline')):
            self.assertTrue(self.call()['isError'])
        self.worker.ask.assert_not_called()

    def test_disconnect_after_inference_keeps_answer_with_unknown_revision(self):
        with patch.object(music.server,'call_editor',side_effect=[self.context,OSError('closed')]):
            data = self.call()['structuredContent']
        self.assertIsNone(data['live_revision_changed'])

    def test_worker_timeout_kills_child(self):
        worker = music.Worker(sys.executable, self.temp.name, timeout=0.05)
        child = subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        worker.process = child
        with self.assertRaisesRegex(ValueError,'timed out'):
            worker.ask({'prompt':'hello'})
        self.assertIsNotNone(child.poll())
        self.assertIsNone(worker.process)

    def test_worker_reuses_process_and_rejects_corrupt_output(self):
        code = 'import sys,json\nfor line in sys.stdin: print(json.dumps({"answer":"ok"}),flush=True)'
        worker = music.Worker(sys.executable,self.temp.name,timeout=2)
        worker.process = subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.addCleanup(worker.close)
        pid = worker.process.pid
        self.assertEqual(worker.ask({})['answer'],'ok')
        self.assertEqual(worker.ask({})['answer'],'ok')
        self.assertEqual(worker.process.pid,pid)
        worker.close()
        worker.process = subprocess.Popen([sys.executable,'-c','print("bad",flush=True)'],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        with self.assertRaises(ValueError):
            worker.ask({})
        self.assertIsNone(worker.process)

    def test_stdio_initialization_requires_no_model_dependencies(self):
        requests = [dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-11-25'}),
                    dict(jsonrpc='2.0',id=2,method='tools/list')]
        result = subprocess.run([sys.executable,str(Path(music.__file__)),'--endpoint','missing'],
            input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,timeout=5)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[0]['result']['serverInfo']['name'],'phichain-music')
        self.assertEqual(len(replies[1]['result']['tools']),2)


if __name__ == '__main__':
    unittest.main()
