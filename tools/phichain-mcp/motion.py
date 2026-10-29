"""Render an immutable live inspection snapshot; no chart authoring or job queue."""
import base64
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def executable(name, override=None):
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f'{name} override must be an existing absolute executable path')
        return str(path)
    candidates = [ROOT / 'target' / build / name for build in ('debug', 'release')]
    candidates += [ROOT / 'local/PhiChain.app/Contents/MacOS' / name]
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    found = shutil.which(name)
    if found:
        return found
    raise ValueError(f'{name} is required for inspect_motion; build/install it first')


def run(argv, env, timeout=90):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise ValueError('Motion inspection timed out; the live chart was not changed') from error
    if result.returncode:
        message = result.stderr.decode('utf-8', errors='replace')[-2000:]
        raise ValueError(f'Motion inspection process failed ({result.returncode}): {message}')


def report(data, folder):
    """Browser-readable overlays over real frames. No editor connection or scripts."""
    esc = html.escape
    chunks = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Motion inspection</title>',
        '<style>body{background:#14202c;color:#ecf3fa;font:16px system-ui;margin:32px}figure{margin:24px 0;max-width:960px}svg{width:100%;background:black}text{font:14px monospace;paint-order:stroke;stroke:#14202c;stroke-width:3px;fill:#fff}a{color:#85d6ff}input:not(:checked)~main .overlay{display:none}pre{white-space:pre-wrap}</style>',
        f'<h1>Motion inspection</h1><p>Live revision {esc(data["revision"])}. Default renderer styling; hit effects hidden. Dashed lines include invisible carriers and ancestors.</p>',
        '<input type="checkbox" id="overlay" checked><label for="overlay">Show diagnostic overlays</label><main>']
    for frame in data['frames']:
        chunks.append(f'<figure><figcaption>{frame["time_seconds"]:.4f}s audio · {frame["chart_time_seconds"]:.4f}s chart</figcaption><svg viewBox="0 0 960 540" xmlns="http://www.w3.org/2000/svg">')
        chunks.append(f'<image href="{esc(Path(frame["path"]).name)}" width="960" height="540"/><g class="overlay">')
        for line in frame['lines']:
            x,y=line['origin']['x'],line['origin']['y']
            a=math.radians(line['rotation_degrees']);dx,dy=1200*math.cos(a),-1200*math.sin(a)
            chunks.append(f'<path d="M {x-dx} {y-dy} L {x+dx} {y+dy}" stroke="#ffab52" stroke-width="1" stroke-dasharray="5 5"/>')
            if 0<=x<=960 and 0<=y<=540:
                chunks.append(f'<text x="{x+5}" y="{y-7}">L{esc(line["id"])} α={line["opacity"]:.2f}</text>')
        for note in frame['notes']:
            if not note['visible_by_timing_and_cover']:
                continue
            x,y=note['head']['x'],note['head']['y']
            chunks.append(f'<circle cx="{x}" cy="{y}" r="8" stroke="#6fffe9" fill="none"/>')
            if note['head_in_view']:
                chunks.append(f'<text x="{x+10}" y="{y-10}">N{esc(note["id"])}</text>')
            points=' '.join(f'{n["head"]["x"]},{n["head"]["y"]}' for f in data['frames'] for n in f['notes'] if n['id']==note['id'] and n['visible_by_timing_and_cover'])
            chunks.append(f'<polyline points="{points}" fill="none" stroke="#6fffe9" stroke-opacity=".5"/>')
        chunks.append('</g></svg></figure>')
    chunks += ['</main><p><a href="inspection.json">Exact IDs, source events, sampled trajectories and landing positions</a></p>',
               '<pre>'+esc('\n'.join(data['limitations']))+'</pre></html>']
    (folder / 'index.html').write_text('\n'.join(chunks), encoding='utf-8')


def inspect(call_editor, arguments, renderer=None, output_root=None):
    # Guard and capture before touching files. Older editors fail here explicitly.
    data = call_editor('inspect_motion', arguments)
    if 'error' in data:
        return data, []
    snapshot = data.pop('_render_snapshot')
    renderer = executable('phichain-renderer', renderer)
    ffmpeg = executable('ffmpeg')
    env = dict(os.environ)
    env['PATH'] = str(Path(ffmpeg).parent) + os.pathsep + env.get('PATH', '')
    env['CARGO_MANIFEST_DIR'] = str(ROOT / 'phichain-renderer')
    root = Path(output_root) if output_root else ROOT / 'local/motion-inspections'
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='inspection-', dir=root))
    try:
        # A temporary rendering input, never an independently editable chart session.
        with tempfile.TemporaryDirectory(prefix='phichain-motion-') as temporary:
            project = Path(temporary)
            (project / 'chart.json').write_text(json.dumps(snapshot['chart']), encoding='utf-8')
            (project / 'meta.json').write_text(json.dumps(snapshot['meta']), encoding='utf-8')
            music = Path(snapshot['music_path']).resolve(strict=True)
            # Copy assets: subsequent external file changes must not change these frames.
            shutil.copyfile(music, project / ('music' + music.suffix))
            if snapshot.get('illustration_path'):
                illustration = Path(snapshot['illustration_path']).resolve(strict=True)
                shutil.copyfile(illustration, project / ('illustration' + illustration.suffix))
            frames = data['frames']
            start = frames[0]['chart_time_seconds']
            end = frames[-1]['chart_time_seconds'] + 2 / 30
            video = project / 'inspection.mp4'
            run([renderer, str(project), '-o', str(video), '--from', str(start), '--to', str(end),
                 '--width', '960', '--height', '540', '--fps', '30', '--hide-hit-effect', '--no-telemetry'], env)
            images = []
            total = 0
            for i, frame in enumerate(frames):
                path = folder / f'frame-{i+1:02}.png'
                index = round((frame['chart_time_seconds']-start)*30)
                run([ffmpeg, '-v', 'error', '-i', str(video), '-vf', f'select=eq(n\\,{index})',
                     '-frames:v', '1', str(path)], env, 20)
                raw = path.read_bytes()
                if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Renderer did not produce a PNG frame')
                total += len(raw)
                if total > 8*1024*1024:
                    raise ValueError('Inspection images exceed 8 MiB; request fewer frames')
                frame['path'] = str(path)
                images.append({'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(raw).decode('ascii')})
        data['report_path'] = str(folder / 'index.html')
        data['snapshot_status'] = 'captured_revision'
        # The inspection is useful even if the user edits while it renders.
        try:
            current = call_editor('get_context', {})
            data['live_revision_changed'] = current.get('session') != data['session'] or current.get('revision') != data['revision']
            if 'error' in current:
                data['live_revision_changed'] = None
        except (OSError, ValueError, TypeError, KeyError):
            data['live_revision_changed'] = None
        report(data, folder)
        (folder / 'inspection.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return data, images
    except Exception:
        shutil.rmtree(folder)
        raise


def preview_passage(call_editor, arguments, renderer=None, output_root=None):
    """A bounded video from the guarded live revision; playback belongs to the browser."""
    start, end = arguments['from_seconds'], arguments['to_seconds']
    if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= 86400 or end-start > 12:
        raise ValueError('Passage must be a positive audio range of at most 12 seconds')
    context = call_editor('get_context', {})
    if 'error' in context:
        return context
    if any(context.get(k) != arguments[k] for k in ('session', 'revision')):
        raise ValueError('Project/revision changed; read context again')
    duration = context.get('audio_duration_seconds')
    if duration is None or end > duration:
        raise ValueError('Passage requires loaded audio and must end within its duration')
    snapshot = call_editor('project_snapshot', {k: arguments[k] for k in ('session', 'revision')})
    if 'error' in snapshot:
        return snapshot
    renderer = executable('phichain-renderer', renderer)
    ffmpeg = executable('ffmpeg')
    env = dict(os.environ)
    env['PATH'] = str(Path(ffmpeg).parent) + os.pathsep + env.get('PATH', '')
    env['CARGO_MANIFEST_DIR'] = str(ROOT / 'phichain-renderer')
    root = Path(output_root) if output_root else ROOT / 'local/passage-previews'
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='passage-', dir=root))
    try:
        with tempfile.TemporaryDirectory(prefix='phichain-passage-') as temporary:
            project = Path(temporary)
            (project/'chart.json').write_text(json.dumps(snapshot['chart']), encoding='utf-8')
            (project/'meta.json').write_text(json.dumps(snapshot['meta']), encoding='utf-8')
            for key, stem in [('music_path', 'music'), ('illustration_path', 'illustration')]:
                if snapshot.get(key):
                    source = Path(snapshot[key]).resolve(strict=True)
                    shutil.copyfile(source, project/(stem+source.suffix))
            offset = context['offset']/1000
            video = folder/'passage.mp4'
            run([renderer, str(project), '-o', str(video), '--from', str(start-offset), '--to', str(end-offset),
                 '--width', '960', '--height', '540', '--fps', '30', '--hide-hit-effect', '--no-telemetry'], env)
            if not video.is_file() or video.stat().st_size == 0:
                raise ValueError('Renderer did not produce a passage video')
        data = {k: arguments[k] for k in ('session', 'revision', 'from_seconds', 'to_seconds')}
        data.update(video_path=str(video), report_path=str(folder/'index.html'), snapshot_status='captured_revision')
        try:
            current = call_editor('get_context', {})
            data['live_revision_changed'] = None if 'error' in current else any(current.get(k) != data[k] for k in ('session','revision'))
        except (OSError, ValueError, TypeError, KeyError):
            data['live_revision_changed'] = None
        (folder/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Passage preview</title>'
            '<style>body{background:#14202c;color:#ecf3fa;font:16px system-ui;margin:32px}video{width:100%;max-width:960px}</style>'
            f'<h1>Passage preview</h1><p>{start:g}–{end:g}s audio · revision {html.escape(str(data["revision"]))}</p>'
            '<video src="passage.mp4" controls loop preload="metadata"></video>'
            '<p>Play, pause and scrub using the video controls. Playback loops within this captured passage. '
            'PhiChain render; default styling, hit effects hidden. The editor playback is unchanged.</p></html>', encoding='utf-8')
        (folder/'preview.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        return data
    except Exception:
        shutil.rmtree(folder)
        raise
