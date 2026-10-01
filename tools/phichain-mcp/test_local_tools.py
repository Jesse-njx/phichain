import json
import base64
import struct
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from local_tools import LocalTools, publish, read_lyrics

class LocalToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.tools=LocalTools(self.root/'endpoint.json',lambda name,args:{'error':'no editor'})
    def tearDown(self):self.tmp.cleanup()
    def tone(self):
        path=self.root/'tone.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1',str(path)],check=True)
        return path
    def test_status_and_safe_launch(self):
        self.assertFalse(self.tools.editor_status()['connected'])
        self.tools.endpoint.write_text('{}')
        with self.assertRaisesRegex(ValueError,'unreachable'):self.tools.launch_editor()
    def test_search_unicode_and_bounds(self):
        (self.root/'オーバーライド.ncm').write_bytes(b'x')
        (self.root/'Other.mp3').write_bytes(b'y')
        result=self.tools.find_local_audio([str(self.root)],'オーバーライド')
        self.assertEqual(len(result['matches']),1)
        with self.assertRaises(ValueError):self.tools.find_local_audio([str(self.root)],limit=201)
    @unittest.skipUnless(shutil.which('openssl'),'openssl unavailable')
    def test_search_finds_netease_alias_without_extracting_audio(self):
        data=b'music:'+json.dumps({'musicName':'オーバーライド','alias':['Override'],'artist':[['重音テト',1]]},ensure_ascii=False).encode()
        encoded=subprocess.run(['openssl','enc','-aes-128-ecb','-K','2331346C6A6B5F215C5D2630553C2728'],input=data,capture_output=True,check=True).stdout
        meta=bytes(x^0x63 for x in b"163 key(Don't modify):"+base64.b64encode(encoded))
        path=self.root/'Japanese-title.ncm';path.write_bytes(b'CTENFDAM'+b'\x00\x00'+struct.pack('<I',0)+struct.pack('<I',len(meta))+meta)
        result=self.tools.find_local_audio([str(self.root)],'Override')
        self.assertEqual(len(result['matches']),1);self.assertTrue(result['matches'][0]['metadata_match'])

    def test_publish_never_replaces_existing(self):
        source=self.root/'src';source.write_bytes(b'new');dest=self.root/'dest';dest.write_bytes(b'old')
        with self.assertRaises(FileExistsError):publish(source,dest)
        self.assertEqual(dest.read_bytes(),b'old')
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg unavailable')
    def test_import_and_project_roundtrip(self):
        tone=self.tone();audio=self.root/'prepared.mp3'
        receipt=self.tools.import_audio(str(tone),str(audio))
        self.assertTrue(receipt['reencoded']);self.assertEqual(receipt['audio']['codec'],'mp3')
        duplicate=self.root/'copy.mp3';copy=self.tools.import_audio(str(audio),str(duplicate))
        self.assertFalse(copy['reencoded']);self.assertEqual(audio.read_bytes(),duplicate.read_bytes())
        meta=dict(name='test',composer='',charter='',illustrator='',level='')
        project=self.root/'project';self.tools.create_project(str(project),str(audio),meta)
        self.assertTrue((project/'music.mp3').exists());self.assertEqual(json.loads((project/'chart.json').read_text())['format'],6)
        with self.assertRaises(ValueError):self.tools.create_project(str(project),str(audio),meta)
        self.assertTrue(tone.exists())
    def test_jobs_survive_adapter_and_report_failure(self):
        staged=self.root/'result.txt';output=self.root/'output.txt'
        code="from pathlib import Path;Path("+repr(str(staged))+").write_text('done')"
        job=self.tools.start_job([[sys.executable,'-c',code,str(staged)]],str(output))
        another=LocalTools(self.tools.endpoint,self.tools.bridge)
        for _ in range(100):
            status=another.render_status(job['job_id'])
            if status['state'] in ('completed','failed'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'completed',status);self.assertEqual(output.read_text(),'done')
        job=self.tools.start_job([[sys.executable,'-c','raise RuntimeError("broken")']],str(self.root/'missing.txt'))
        for _ in range(100):
            status=self.tools.render_status(job['job_id'])
            if status['state'] in ('completed','failed'):break
            time.sleep(.02)
        self.assertEqual(status['state'],'failed');self.assertIn('broken',status['error'])
    def test_snapshot_preserves_live_revision(self):
        audio=self.root/'music.mp3';audio.write_bytes(b'audio')
        snapshot={'chart':{'unsaved':True},'meta':{'name':'live'},'music_path':str(audio),'illustration_path':None,'revision':'r','session':'s'}
        self.tools.bridge=lambda name,args:snapshot
        directory,result=self.tools.snapshot('s','r')
        try:
            self.assertEqual(result['revision'],'r');self.assertTrue(json.loads((directory/'chart.json').read_text())['unsaved'])
            self.assertEqual((directory/'music.mp3').read_bytes(),b'audio')
        finally:shutil.rmtree(directory)


class LyricTests(unittest.TestCase):
    def test_standard_and_netease_timestamps(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cues.lrc';path.write_text('[00:12:08]first\n[00:14.110][00:15.5]second\n[ar:Artist]\n')
            cues=read_lyrics(path)
            self.assertEqual([c['time_seconds'] for c in cues],[12.08,14.11,15.5])
            self.assertEqual(cues[2]['text'],'second')
            path.write_text('[00:99.0]bad')
            with self.assertRaises(ValueError):read_lyrics(path)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'ffmpeg unavailable')
    def test_analysis_reference_uses_real_gapless_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'audio.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3',str(path)],check=True)
            received=[]
            tools=LocalTools(root/'endpoint.json',lambda name,args:(received.append((name,args)) or {'analysis_id':'a','state':'running'}))
            result=tools.analyze_audio(path=str(path))
            self.assertEqual(result['analysis_id'],'a')
            self.assertEqual(received[0][0],'analyze_audio')
            self.assertLess(received[0][1]['reference_first_audible_seconds'],.01)
