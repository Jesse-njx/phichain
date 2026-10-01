"""Local preparation and persistent subprocess jobs. No desktop automation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import threading
import unicodedata
import uuid

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.ncm'}
REPO = Path(__file__).resolve().parents[2]

def absolute(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('Paths must be absolute')
    return path

def run(argv, timeout=120, input=None):
    p = subprocess.run([str(x) for x in argv], input=input, capture_output=True, timeout=timeout)
    if p.returncode:
        raise ValueError(p.stderr.decode('utf-8', errors='replace')[-3000:] or f'{argv[0]} failed')
    return p.stdout

def publish(source, destination):
    """Publish without replacing a file, including a racing writer's file."""
    destination = absolute(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as f:
        staging = Path(f.name)
        with open(source, 'rb') as src:
            shutil.copyfileobj(src, f)
    try:
        os.link(staging, destination)
    finally:
        staging.unlink()
    return str(destination)

def ncm_extract(source, directory):
    # NCM's AES-ECB key/metadata envelope and its repeating stream mask.
    def aes(data, key):
        decoded = run(['openssl', 'enc', '-d', '-aes-128-ecb', '-K', key, '-nopad'], input=data)
        padding = decoded[-1] if decoded else 0
        if not 1 <= padding <= 16 or decoded[-padding:] != bytes([padding])*padding:
            raise ValueError('Invalid NCM encryption padding')
        return decoded[:-padding]
    with open(source, 'rb') as f:
        def read(n):
            if not 0 <= n <= 512*1024*1024: raise ValueError('NCM field is too large')
            data = f.read(n)
            if len(data) != n: raise ValueError('Truncated NCM file')
            return data
        def u32(): return struct.unpack('<I', read(4))[0]
        if read(8) != b'CTENFDAM': raise ValueError('Unsupported NCM header')
        read(2)
        key = aes(bytes(x ^ 0x64 for x in read(u32())), '687A4852416D736F356B496E62617857')[17:]
        if not key: raise ValueError('Empty NCM key')
        box = list(range(256)); last = 0
        for i in range(256):
            c = (box[i]+last+key[i % len(key)]) & 255
            box[i], box[c] = box[c], box[i]; last = c
        metadata_envelope = read(u32())
        meta = {}
        if metadata_envelope:
            data = bytes(x ^ 0x63 for x in metadata_envelope)
            meta = json.loads(aes(base64.b64decode(data[22:], validate=True), '2331346C6A6B5F215C5D2630553C2728')[6:])
        read(4); read(1)
        allocation, size = u32(), u32()
        if size > allocation: raise ValueError('Invalid NCM artwork allocation')
        artwork = read(size); read(allocation-size)
        mask = bytes(box[(box[j]+box[(box[j]+j)&255])&255] for j in [i&255 for i in range(1,257)])
        extension = meta.get('format', 'mp3').lower()
        if extension not in ('mp3', 'flac'): raise ValueError('Unsupported NCM audio payload')
        audio = Path(directory)/('extracted.'+extension)
        with audio.open('wb') as output:
            while True:
                chunk = f.read(32768)
                if not chunk: break
                output.write(bytes(x ^ mask[i % 256] for i,x in enumerate(chunk)))
        art = None
        if artwork:
            if artwork.startswith(b'\x89PNG'): suffix = '.png'
            elif artwork.startswith(b'\xff\xd8'): suffix = '.jpg'
            else: raise ValueError('Unsupported embedded artwork')
            art = Path(directory)/('artwork'+suffix); art.write_bytes(artwork)
        # NetEase for macOS can store artwork in a sibling metadata directory.
        elif str(meta.get('musicId', '')).isdigit():
            sibling = Path(source).parent/'meta'/('track-'+str(meta['musicId'])+'.jpg')
            if sibling.is_file(): art = sibling
        return audio, meta, art

class LocalTools:
    NAMES = {'editor_status', 'launch_editor', 'create_project', 'find_local_audio', 'inspect_audio',
             'import_audio', 'render_preview', 'render_status', 'capture_preview', 'export_chart'}
    def __init__(self, endpoint, bridge, config=None):
        self.endpoint = absolute(str(Path(endpoint).absolute()))
        self.bridge = bridge
        self.config = config or {}
        self.job_root = Path(tempfile.gettempdir())/('phichain-mcp-'+str(os.getuid())+'-'+hashlib.sha256(str(self.endpoint).encode()).hexdigest()[:12])
        self.job_root.mkdir(mode=0o700, exist_ok=True)

    def binary(self, name):
        configured = self.config.get(name)
        if configured:
            path = absolute(configured)
            if not path.is_file(): raise ValueError(f'Missing configured {name}: {path}')
            return str(path)
        if name in ('ffmpeg', 'ffprobe'):
            path = shutil.which(name)
            if path: return path
        else:
            exe = {'editor':'phichain', 'renderer':'phichain-renderer', 'converter':'phichain-converter'}[name]
            for path in [REPO/'target/debug'/exe, REPO/'target/release'/exe, REPO/'local/PhiChain.app/Contents/MacOS'/exe]:
                # Release binaries require assets alongside the executable.
                if path.parent == REPO/'target/release' and name != 'converter' and not (path.parent/'assets/respack').is_dir():continue
                if path.is_file(): return str(path)
        raise ValueError(f'{name} is unavailable; configure --{name} with an absolute executable path')

    def call(self, name, args):
        return getattr(self, name)(**args)

    def editor_status(self):
        try:
            result = self.bridge('editor_status', {})
            if 'error' in result: raise ValueError(result['error'])
            return result
        except (OSError, ValueError, KeyError) as e:
            return {'connected':False, 'endpoint':str(self.endpoint), 'reason':str(e)}

    def launch_editor(self, project_path=None):
        status = self.editor_status()
        if status['connected']: return status
        if self.endpoint.exists():
            raise ValueError('Endpoint exists but is unreachable. Verify its owner exited before removing it; not launching a second instance')
        launch_record=self.job_root/'editor-launch.json'
        if launch_record.exists():
            previous=json.loads(launch_record.read_text())
            try:
                os.kill(previous['pid'],0)
                return {'status':'starting','pid':previous['pid'],'log_path':str(self.job_root/'editor.log'),'next':'editor_status'}
            except ProcessLookupError:pass
        if project_path: absolute(project_path)
        exe = self.binary('editor')
        env = os.environ.copy()
        if (REPO/'phichain-editor/lang/meta.json').is_file():
            env['CARGO_MANIFEST_DIR'] = str(REPO/'phichain-editor')
            env['BEVY_ASSET_ROOT'] = str(REPO)
        argv = [exe, '--mcp-endpoint', str(self.endpoint)]
        if project_path: argv += ['--project', project_path]
        self.endpoint.parent.mkdir(parents=True, exist_ok=True)
        log_path = self.job_root/'editor.log'
        with log_path.open('ab') as log:
            proc = subprocess.Popen(argv, cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        launch_record.write_text(json.dumps({'pid':proc.pid,'started_at':time.time()}))
        threading.Thread(target=proc.wait,daemon=True).start()
        return {'status':'starting', 'pid':proc.pid, 'executable':exe, 'log_path':str(log_path), 'next':'editor_status'}

    def find_local_audio(self, roots, query='', limit=50):
        if not roots or not 1 <= limit <= 200: raise ValueError('Provide roots and a limit between 1 and 200')
        terms = unicodedata.normalize('NFKC', query).casefold().split()
        matches=[]; visited=0; truncated=False
        for root in roots:
            root = absolute(root)
            if not root.is_dir(): raise ValueError(f'Not a directory: {root}')
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'target'))
                for filename in sorted(files):
                    visited += 1
                    if visited > 100000: truncated=True; break
                    path = Path(directory)/filename
                    name = unicodedata.normalize('NFKC', filename).casefold()
                    if path.suffix.lower() in AUDIO_EXTENSIONS and all(t in name for t in terms):
                        matches.append({'path':str(path), 'bytes':path.stat().st_size, 'container':path.suffix[1:]})
                        if len(matches)>=limit: truncated=True; break
                if truncated: break
            if truncated: break
        return {'matches':matches,'truncated':truncated,'files_scanned':visited,'matching':'normalized filename terms; inspect_audio reads embedded title/artist'}

    def probe(self, path):
        info = json.loads(run([self.binary('ffprobe'), '-v','error','-show_format','-show_streams','-of','json',path]))
        audio = next((s for s in info.get('streams',[]) if s.get('codec_type')=='audio'), None)
        if not audio: raise ValueError('No audio stream in file')
        return {'codec':audio['codec_name'], 'sample_rate':int(audio.get('sample_rate',0)), 'channels':audio.get('channels'),
                'duration_seconds':float(info.get('format',{}).get('duration',audio.get('duration',0))),
                'bitrate':int(info.get('format',{}).get('bit_rate',0)),
                'decoder_start_seconds':float(info.get('format',{}).get('start_time',0)),
                'tags':info.get('format',{}).get('tags',{}),
                'embedded_artwork':any(s.get('disposition',{}).get('attached_pic') for s in info.get('streams',[]))}

    def inspect_audio(self, path):
        source = absolute(path).resolve(strict=True)
        with tempfile.TemporaryDirectory() as temp:
            audio, meta, art = ncm_extract(source,temp) if source.suffix.lower()=='.ncm' else (source,{},None)
            return {'source_path':str(source), 'audio':self.probe(audio), 'netease_metadata':meta,
                    'artwork_available':bool(art), 'source_bytes':source.stat().st_size}

    def import_audio(self, source_path, output_path, format='mp3', artwork_output=None):
        source = absolute(source_path).resolve(strict=True); output = absolute(output_path)
        if format not in ('mp3','wav','flac','ogg'): raise ValueError('Unsupported target format')
        if output.suffix.lower() != '.'+format: raise ValueError('Output extension must match format')
        if output.exists(): raise ValueError('Output already exists; source/output are never overwritten')
        if artwork_output and absolute(artwork_output).exists(): raise ValueError('Artwork output already exists')
        with tempfile.TemporaryDirectory() as temp:
            audio, meta, art = ncm_extract(source,temp) if source.suffix.lower()=='.ncm' else (source,{},None)
            before = self.probe(audio)
            passthrough = before['codec'] == {'mp3':'mp3','wav':'pcm_s16le','flac':'flac','ogg':'vorbis'}[format] and audio.suffix.lower()=='.'+format
            if passthrough: prepared = audio
            else:
                prepared = Path(temp)/('prepared.'+format)
                codec = {'mp3':['-c:a','libmp3lame','-b:a','320k'], 'wav':['-c:a','pcm_s16le'], 'flac':['-c:a','flac'], 'ogg':['-c:a','libvorbis','-q:a','7']}[format]
                run([self.binary('ffmpeg'),'-v','error','-nostdin','-i',audio,'-map','0:a:0',*codec,prepared])
            verified = self.probe(prepared)
            if artwork_output and not art and before['embedded_artwork']:
                art=Path(temp)/'embedded.png'
                run([self.binary('ffmpeg'),'-v','error','-nostdin','-i',audio,'-map','0:v:0','-frames:v','1',art])
            if artwork_output and art:
                # Normalize artwork to the explicit requested filename's format.
                target = absolute(artwork_output)
                if target.suffix.lower() not in ('.jpg','.jpeg','.png'): raise ValueError('Artwork output must be JPG or PNG')
                prepared_art=Path(temp)/('prepared-art'+target.suffix)
                run([self.binary('ffmpeg'),'-v','error','-nostdin','-i',art,'-frames:v','1',prepared_art])
            published=[]
            try:
                published.append(publish(prepared, output))
                art_path=None
                if artwork_output and art:
                    art_path=publish(prepared_art,artwork_output);published.append(art_path)
            except Exception:
                for path in published: Path(path).unlink()
                raise
        digest=hashlib.sha256()
        with source.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        return {'source_path':str(source),'source_sha256':digest.hexdigest(),'output_path':str(output),
                'reencoded':not passthrough,'audio':verified,'metadata':meta,'artwork_path':art_path}

    def create_project(self, path, audio_path, meta, illustration_path=None):
        destination = absolute(path)
        if destination.exists(): raise ValueError('Project destination already exists')
        destination.parent.mkdir(parents=True,exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix='.phichain-project-',dir=destination.parent))
        try:
            source=absolute(audio_path).resolve(strict=True)
            if source.suffix.lower() not in ('.mp3','.wav','.ogg','.flac'): raise ValueError('Import audio before creating a project')
            info=self.probe(source)
            shutil.copyfile(source,temp/('music'+source.suffix.lower()))
            if illustration_path:
                art=absolute(illustration_path).resolve(strict=True)
                if art.suffix.lower() not in ('.jpg','.jpeg','.png'): raise ValueError('Artwork must be JPG or PNG')
                shutil.copyfile(art,temp/('illustration'+art.suffix.lower()))
            events=[{'kind':kind,'start_beat':[0,0,1],'end_beat':[1,0,1],'value':{'type':'constant','value':value}} for kind,value in [('x',0),('y',0),('rotation',0),('opacity',255),('speed',7)]]
            chart={'format':6,'offset':0,'bpm_list':[{'beat':[0,0,1],'bpm':120}], 'lines':[{'name':'Main','notes':[],'events':events,'children':[],'curve_note_tracks':[]}]}
            (temp/'chart.json').write_text(json.dumps(chart),encoding='utf-8')
            (temp/'meta.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
            # mkdir exclusively reserves the name; move children into only our empty directory.
            destination.mkdir()
            try:
                for child in temp.iterdir():child.rename(destination/child.name)
            except Exception:
                shutil.rmtree(destination);raise
        finally: shutil.rmtree(temp)
        return {'project_path':str(destination),'audio':info,'next':'open_project'}

    def start_job(self, commands, output, session=None, revision=None, snapshot_dir=None):
        output=absolute(output)
        if output.exists():raise ValueError('Output already exists')
        output.parent.mkdir(parents=True,exist_ok=True)
        job_id=uuid.uuid4().hex;directory=self.job_root/job_id;directory.mkdir(mode=0o700)
        manifest={'job_id':job_id,'state':'queued','commands':commands,'output_path':str(output),
                  'session':session,'revision':revision,'snapshot_dir':snapshot_dir,'created_at':time.time()}
        path=directory/'job.json';path.write_text(json.dumps(manifest),encoding='utf-8')
        with (directory/'worker.log').open('ab') as log:
            process = subprocess.Popen([sys.executable,str(Path(__file__).with_name('worker.py')),str(path)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        threading.Thread(target=process.wait,daemon=True).start()
        return {'job_id':job_id,'state':'queued','output_path':str(output),'session':session,'revision':revision,'next':'render_status'}

    def snapshot(self, session, revision):
        snapshot=self.bridge('project_snapshot',{'session':session,'revision':revision})
        if 'error' in snapshot:raise ValueError(snapshot['error'])
        directory=Path(tempfile.mkdtemp(prefix='snapshot-',dir=self.job_root))
        try:
            (directory/'chart.json').write_text(json.dumps(snapshot['chart']),encoding='utf-8')
            (directory/'meta.json').write_text(json.dumps(snapshot['meta'],ensure_ascii=False),encoding='utf-8')
            for key,stem in [('music_path','music'),('illustration_path','illustration')]:
                if snapshot.get(key):
                    source=Path(snapshot[key]);shutil.copyfile(source,directory/(stem+source.suffix))
            return directory,snapshot
        except Exception:shutil.rmtree(directory);raise

    def render_preview(self, session, revision, output_path, from_seconds, to_seconds, width=1280, height=720, fps=60):
        if not 0 <= from_seconds < to_seconds or to_seconds-from_seconds>600:raise ValueError('Provide a positive render range of at most 600 seconds')
        if not 160<=width<=3840 or not 90<=height<=2160 or width%2 or height%2 or not 1<=fps<=120:raise ValueError('Invalid video dimensions or FPS')
        renderer=self.binary('renderer');absolute(output_path)
        if Path(output_path).suffix.lower()!='.mp4':raise ValueError('Preview output must be .mp4')
        directory,snap=self.snapshot(session,revision)
        argv=[renderer,str(directory),'-o',str(directory/'preview.mp4'),'--from',str(from_seconds),'--to',str(to_seconds),'--width',str(width),'--height',str(height),'--fps',str(fps),'--no-telemetry']
        try:return self.start_job([argv],output_path,session,revision,str(directory))
        except Exception:shutil.rmtree(directory);raise

    def capture_preview(self, session, revision, output_path, time_seconds, width=1280, height=720):
        if time_seconds<0:raise ValueError('time_seconds must be nonnegative')
        if Path(output_path).suffix.lower()!='.png':raise ValueError('Still output must be .png')
        renderer=self.binary('renderer');ffmpeg=self.binary('ffmpeg')
        if not 160<=width<=3840 or not 90<=height<=2160 or width%2 or height%2:raise ValueError('Invalid dimensions')
        directory,snap=self.snapshot(session,revision)
        video=directory/'preview.mp4';still=directory/'still.png'
        commands=[[renderer,str(directory),'-o',str(video),'--from',str(time_seconds),'--to',str(time_seconds+.1),'--width',str(width),'--height',str(height),'--fps','30','--no-telemetry'],[ffmpeg,'-v','error','-nostdin','-i',str(video),'-frames:v','1',str(still)]]
        try:return self.start_job(commands,output_path,session,revision,str(directory))
        except Exception:shutil.rmtree(directory);raise

    def render_status(self, job_id):
        if len(job_id)!=32 or any(c not in '0123456789abcdef' for c in job_id):raise ValueError('Invalid job ID')
        path=self.job_root/job_id/'job.json'
        data=json.loads(path.read_text())
        return {k:v for k,v in data.items() if k not in ('commands','snapshot_dir')}

    def export_chart(self, session, revision, output_path, format):
        if format not in ('phichain','official','rpe'):raise ValueError('Unsupported export format')
        converter=self.binary('converter');directory,snap=self.snapshot(session,revision)
        argv=[converter,str(directory/'chart.json'),str(directory/'export.json'),'--from','phichain','--to',format,'--no-telemetry']
        try:return self.start_job([argv],output_path,session,revision,str(directory))
        except Exception:shutil.rmtree(directory);raise
