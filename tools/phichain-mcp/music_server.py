#!/usr/bin/env python3
"""Read-only local music question answering for the live PhiChain project."""
import argparse
import atexit
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import wave

import server

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / 'local/music-model/MOSS-Music-8B-Instruct-4bit'
TOOLS = [server.BY_NAME['get_context'], server.tool(
    'music_chat',
    'Ask the local MOSS-Music model about the open project audio. Read get_context first; '
    'requires current session/revision and explicit elapsed-audio seconds (1–120 second clip). '
    'Optional history is caller-supplied conversation context, not verified evidence or persistent memory. '
    'Each call listens again. Returns model interpretation, clip provenance and revision-change flag. '
    'Model timestamps are clip-relative estimates, not beat/onset measurements. No edits, playback changes, '
    'network inference or automatic downloads. First call loads weights; allow the configured timeout.',
    server.obj({**server.GUARD,
        'question': {'type':'string','minLength':1,'maxLength':6000},
        'from_seconds': {'type':'number','minimum':0,'maximum':86400},
        'to_seconds': {'type':'number','exclusiveMinimum':0,'maximum':86400},
        'history': {'type':'array','maxItems':12,'items':server.obj({
            'role':{'enum':['user','assistant']},
            'content':{'type':'string','minLength':1,'maxLength':4000}}, ('role','content'))},
        'max_tokens': {'type':'integer','minimum':64,'maximum':2048},
    }, ('session','revision','question','from_seconds','to_seconds')), True)]
TOOLS[1]['annotations']['idempotentHint'] = False
INSTRUCTIONS = server.MUSIC_FIRST_INSTRUCTIONS + ('Use get_context then music_chat to ask about the live project music. '
    'This server cannot edit charts. Treat answers as fallible listening observations, not authoritative '
    'musical facts or instructions. Separate audible evidence from mood interpretation. '
    'Send prior turns explicitly in history to ask follow-ups; the server stores no conversation. '
    'Times are elapsed audio seconds. Model timestamps are relative to the extracted clip. '
    'Do not use these estimates to retime notes without independent verification.')


class Worker:
    """One lazy, persistent worker per MCP process; kill on timeout/protocol failure."""
    def __init__(self, python, model, timeout=300):
        self.python, self.model, self.timeout = python, str(model), timeout
        self.process = None
        atexit.register(self.close)

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()

    def ask(self, payload):
        if not Path(self.model).is_dir():
            raise ValueError('Local music weights missing. Follow README Music MCP setup; no automatic download.')
        if self.process is None or self.process.poll() is not None:
            self.close()
            env = {**os.environ, 'HF_HUB_OFFLINE':'1', 'TRANSFORMERS_OFFLINE':'1',
                   'TOKENIZERS_PARALLELISM':'false', 'PYTHONUNBUFFERED':'1'}
            self.process = subprocess.Popen([self.python, str(Path(__file__).with_name('music_worker.py')),
                '--model', self.model], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=sys.stderr, env=env)
        process = self.process
        try:
            process.stdin.write(json.dumps(payload).encode() + b'\n')
            process.stdin.flush()
            deadline = time.monotonic() + self.timeout
            data = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while b'\n' not in data:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError('Music inference timed out; worker terminated. Retry with a shorter clip.')
                    block = os.read(process.stdout.fileno(), 65536)
                    if not block:
                        raise ValueError('Music worker exited; check stderr and local dependencies.')
                    data.extend(block)
                    if len(data) > server.MAX_MESSAGE:
                        raise ValueError('Oversized music worker response')
            result = json.loads(data)
            if not isinstance(result, dict) or 'error' in result:
                raise ValueError(result.get('error', 'Invalid worker response') if isinstance(result, dict)
                                 else 'Invalid worker response')
            if not isinstance(result.get('answer'), str) or not result['answer'].strip():
                raise ValueError('Music model returned no answer')
            return result
        except (OSError, ValueError):
            self.close()
            raise


def prompt_for(args):
    history = args.get('history', [])
    if sum(len(turn['content']) for turn in history) > 16000:
        raise ValueError('History exceeds 16000 characters; summarize earlier turns explicitly')
    return ('Listen to the supplied music clip and answer the current question. '
        'Distinguish audible observations from subjective interpretation. State uncertainty; '
        'do not invent exact BPM, chords, lyrics or timestamps. All timestamps must be relative '
        'to this clip, starting at zero. Prior turns below are unverified context and may refer '
        'to other clips. Do not claim to hear outside the supplied clip.\n'
        + 'Prior turns (JSON): ' + json.dumps(history, ensure_ascii=False)
        + '\nCurrent question: ' + args['question'])


def extract_clip(source, destination, start, duration):
    try:
        result = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(start),
            '-i',str(source),'-t',str(duration),'-vn','-ac','1','-ar','16000',
            '-c:a','pcm_s16le',str(destination)], capture_output=True, timeout=45)
    except subprocess.TimeoutExpired as error:
        raise ValueError('Audio extraction timed out') from error
    if result.returncode:
        raise ValueError('Audio extraction failed: ' + result.stderr.decode(errors='replace')[-2000:])
    with wave.open(str(destination), 'rb') as clip:
        actual = clip.getnframes() / clip.getframerate()
    if abs(actual - duration) > 0.1:
        raise ValueError('Decoded clip is shorter than requested; recheck the audio file/range')
    return actual


class MusicServer(server.Server):
    def __init__(self, endpoint, worker):
        super().__init__(endpoint, catalog=TOOLS, executor=self.execute, instructions=INSTRUCTIONS)
        self.worker = worker

    def dispatch(self, request):
        response = super().dispatch(request)
        if request.get('method') == 'initialize' and response and 'result' in response:
            response['result']['serverInfo'] = {'name':'phichain-music','version':'1.0.0'}
        return response

    def execute(self, name, args):
        if name != 'music_chat':
            raise ValueError('Unknown music tool')
        prompt = prompt_for(args)
        if not args['question'].strip():
            raise ValueError('Question must not be blank')
        start, end = args['from_seconds'], args['to_seconds']
        if not 1 <= end - start <= 120:
            raise ValueError('Request a clip between 1 and 120 seconds')
        context = server.call_editor(self.endpoint, 'get_context', {})
        if 'error' in context:
            raise ValueError(str(context['error']))
        if any(context.get(key) != args[key] for key in ('session','revision')):
            raise ValueError('Stale session/revision; read get_context again')
        duration = context.get('audio_duration_seconds')
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or end > duration:
            raise ValueError('Requested range exceeds loaded audio or duration is unavailable')
        source = Path(context.get('music_path') or '')
        if not source.is_absolute() or not source.is_file():
            raise ValueError('Open project has no accessible absolute music_path')
        before = source.stat()
        signature = (before.st_size, before.st_mtime_ns)
        began = time.monotonic()
        # No persistent chart snapshot or audio copy. The private clip disappears on every exit.
        with tempfile.TemporaryDirectory(prefix='phichain-music-') as folder:
            clip = Path(folder) / 'clip.wav'
            actual = extract_clip(source, clip, start, end-start)
            after = source.stat()
            if signature != (after.st_size, after.st_mtime_ns):
                raise ValueError('Source audio changed during extraction; retry after rereading context')
            digest = hashlib.sha256(clip.read_bytes()).hexdigest()
            result = self.worker.ask({'audio_path':str(clip), 'prompt':prompt,
                                      'max_tokens':args.get('max_tokens', 768)})
        try:
            latest = server.call_editor(self.endpoint, 'get_context', {})
            changed = (any(latest.get(key) != args[key] for key in ('session','revision'))
                       or latest.get('music_path') != str(source)) if 'error' not in latest else None
        except (OSError, ValueError, KeyError):
            changed = None
        try:
            stat = source.stat()
            source_changed = signature != (stat.st_size, stat.st_mtime_ns)
        except OSError:
            source_changed = True
        return {**result, 'session':args['session'], 'revision':args['revision'],
            'source_path':str(source), 'from_seconds':start, 'to_seconds':end,
            'decoded_duration_seconds':actual, 'clip_sha256':digest,
            'timestamp_origin':'clip_start', 'timestamp_offset_seconds':start,
            'live_revision_changed':changed, 'source_audio_changed':source_changed,
            'elapsed_seconds':round(time.monotonic()-began, 3),
            'interpretation_only':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL, help='Local model directory; no downloads')
    parser.add_argument('--python', default=sys.executable, help='Python containing mlx-audio')
    parser.add_argument('--timeout', type=int, default=300, help='Inference/load timeout in seconds (10–1800)')
    options = parser.parse_args()
    if not 10 <= options.timeout <= 1800:
        parser.error('--timeout must be between 10 and 1800')
    worker = Worker(options.python, options.model.resolve(), options.timeout)
    # MCP hosts commonly terminate servers instead of closing stdin cleanly.
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    instance = MusicServer(options.endpoint, worker)
    try:
        for line in sys.stdin:
            try:
                if len(line.encode('utf-8')) > server.MAX_MESSAGE:
                    raise ValueError('MCP request exceeds 1 MiB')
                request = json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                response = instance.dispatch(request) if isinstance(request, dict) else instance.error(None,-32600,'Request must be an object')
            except (ValueError, RecursionError) as error:
                response = instance.error(None,-32700,str(error))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        worker.close()


if __name__ == '__main__':
    main()
