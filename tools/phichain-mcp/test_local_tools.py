import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from local_tools import LocalTools, publish

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
