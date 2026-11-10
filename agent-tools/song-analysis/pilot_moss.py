#!/usr/bin/env python3
"""Pilot of the song-analysis framework's listening protocol on a local MOSS-Music model.

Read-only with respect to charts, the editor and the source audio. It extracts
clips with ffmpeg into a scratch directory, runs one question per model call,
and writes every raw answer with clip provenance into the output directory.
Nothing here edits a chart or an editor project.

Usage (from any directory):
  <music-runtime python> pilot_moss.py --audio song.mp3 --out DIR --clips SCRATCH \
      [--only A1_W1,C1,...] [--list]
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / 'runtime/music-model/MOSS-Music-8B-Instruct-4bit'

# Default grid is Override's (first pilot). Any other song passes --config with its own measured grid.
GRID = {'bpm': 204.0, 'offset_seconds': 0.348}
CONFIG = None  # set from --config: {"bpm", "offset_seconds", "sections": {name: [start_beat, end_beat|null]},
#                                    "pairs": [[id, a, b]], "control_pairs": [[id, a, b]], "intensity_pairs": [[id, a, b]]}


def beat(b):
    return round(GRID['offset_seconds'] + b * 60.0 / GRID['bpm'], 3)


def extract(source, destination, start, end):
    duration = round(end - start, 3)
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(start), '-i', str(source),
                             '-t', str(duration), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le',
                             str(destination)], capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    with wave.open(str(destination), 'rb') as clip:
        actual = clip.getnframes() / clip.getframerate()
    return actual


def chat(user_text, audio_count):
    spans = ''.join('<|audio_bos|><|AUDIO|><|audio_eos|>\n' for _ in range(audio_count))
    return ('<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n'
            f'<|im_start|>user\n{spans}{user_text}<|im_end|>\n<|im_start|>assistant\n')


def pair_chat(user_text):
    return ('<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n'
            '<|im_start|>user\nClip A:\n<|audio_bos|><|AUDIO|><|audio_eos|>\n'
            'Clip B:\n<|audio_bos|><|AUDIO|><|audio_eos|>\n'
            f'{user_text}<|im_end|>\n<|im_start|>assistant\n')


# ---- clip plan -------------------------------------------------------------
def plan(duration):
    clips = {}
    # Pass A: overlapping overview windows covering the whole song.
    for name, (a, b) in {'W1': (0, 48), 'W2': (40, 90), 'W3': (82, 130), 'W4': (100, duration)}.items():
        clips[name] = (a, min(b, duration))
    # Pass D: shifted windows for stability checks.
    clips['W1s'] = (4, 52)
    clips['W2s'] = (44, 94)
    # Pass B: section-aligned clips from the reviewed map (editor beats, [start,end)).
    sections = {'S_open': (0, 40), 'S_verse1': (40, 104), 'S_pre': (104, 136), 'S_chorus1': (136, 200),
                'S_hook2': (200, 232), 'S_verse2a': (232, 264), 'S_verse2b': (264, 304),
                'S_chorus2': (304, 368), 'S_climax3': (368, 432), 'S_hook3': (432, None)}
    for name, (a, b) in sections.items():
        clips[name] = (beat(a), duration if b is None else beat(b))
    # Pass C: pair-comparison members.
    pairs = {'P_hook1': (8, 40), 'P_hook2': (200, 232), 'P_hook3': (432, 464), 'P_ch1': (136, 200),
             'P_ch2': (304, 368), 'P_cl3': (368, 432), 'P_v1': (40, 72), 'P_v2': (232, 264), 'P_ch1a': (136, 168)}
    for name, (a, b) in pairs.items():
        clips[name] = (beat(a), beat(b))
    clips['E_grid'] = (beat(136), beat(136) + 30)
    # Protocol v2 probes (added after the first pilot): short sliding clips for change points.
    for start in (52, 60, 68, 76, 84):
        clips[f'CP_{start}'] = (start, start + 16)
    return clips


Q = {
    'A1': ('Describe the musical structure of this clip. List each section in order with its start time in '
           'seconds from the beginning of the clip, its function (intro, verse, pre-chorus, chorus, instrumental '
           'hook, interlude, bridge, outro), the main sound that defines it, and whether lead vocals are present. '
           'One line per section.', 600),
    'A2': ('List every moment in this clip where an instrument or voice enters, drops out, or changes role, for '
           'example drums stop, bass enters, lead synth takes over, the singer begins or ends a phrase. Give one '
           'line per event in the form "<seconds from clip start>: <event>". Only list events you actually hear.', 600),
    'A3': ('Rate the energy of this clip in consecutive 4-second windows, from 1 (sparse or quiet) to 5 (full, '
           'climactic). Output one line per window in the form "<start seconds>: <rating> - <what drives it>".', 500),
    'A4': ('Transcribe the lyrics of this clip with a timestamp for each line. If a passage has no singing, write '
           '"[no vocals]" with its time range.', 700),
    'B1': ('In this clip, which layer carries the main melodic line a listener would follow: lead vocal, lead synth, '
           'guitar, piano, bass, or none? Describe that line\'s rhythm: mostly long sustained notes, steady eighth '
           'notes, fast sixteenth-note runs, syncopated or off-beat, or call-and-response between two voices. Note '
           'any moment (seconds from clip start) where the lead layer changes.', 400),
    'B2': ('Describe the drum pattern in this clip: the kick pattern (four-on-the-floor, half-time, syncopated, or '
           'absent), where the snare or clap falls, the hi-hat subdivision, any fills or breaks with their times in '
           'seconds from clip start, and whether the pattern changes within the clip.', 400),
    'B3': ('What is the function of this passage within a pop song: intro, verse, pre-chorus, chorus, post-chorus '
           'hook, interlude, bridge, final chorus, or outro? Rate its energy from 1 to 5 and its tension as building, '
           'steady, or releasing. Does the passage start with a pickup before the downbeat, start cleanly on a '
           'downbeat, or start in the middle of a phrase? Does it end with a fill, a cut, a sustained note, or run '
           'straight into the next passage?', 400),
    'C': ('Are these two clips the same section of the same song returning (for example the same chorus or hook), '
          'a variation of the same material, or different sections? Answer first with exactly one of: SAME, '
          'VARIATION, DIFFERENT. Then explain in two sentences what is shared or changed in melody, lyrics, '
          'instrumentation and energy.', 200),
    'E': ('Estimate the tempo of this clip in BPM and its time signature. Answer with the numbers only, then one '
          'sentence on how confident you are.', 100),
    # v3 questions
    'VP': ('Is there a singing voice (lead or backing vocals, sung or rapped words) in this clip? Answer first with '
           'exactly one of: VOCALS, NO VOCALS. If VOCALS, give the time in seconds from clip start where singing '
           'first starts and where it last stops.', 80),
    'B1v': ('Which layer carries the main line a listener follows in this clip: a singing voice, or an instrument? '
            'Answer first with exactly one of: VOCAL, INSTRUMENT, NONE. If INSTRUMENT, name it (lead synth, guitar, '
            'piano, strings, bass, drums) in a few words. Then say in one sentence whether that line is mostly '
            'sustained notes, steady repeated notes, fast runs, or syncopated hits.', 120),
    # v2 probes
    'CP': ('Does the music change to a different section anywhere inside this clip, for example the singing starts '
           'or stops, the arrangement drops out or arrives, or a new section begins? Answer "NO CHANGE", or give '
           'the time in seconds from the clip start of each change and what changes, one per line.', 200),
    'PI': ('Which clip is more intense and energetic, A or B? Answer with exactly one of: A, B, EQUAL. Then one '
           'sentence on why.', 120),
    'CM': ('Ignoring the words being sung, do these two clips have the same vocal melody over the same instrumental '
           'arrangement, that is, are they two choruses of the same song? Answer first with exactly one of: SAME '
           'MELODY, VARIATION, DIFFERENT. Then explain in two sentences.', 200),
}


def calls(clips):
    out = []
    for w in ('W1', 'W2', 'W3', 'W4'):
        for q in ('A1', 'A2', 'A3', 'A4'):
            out.append((f'{q}_{w}', q, [w]))
    for s in [c for c in clips if c.startswith('S_')]:
        for q in ('B1', 'B2', 'B3'):
            out.append((f'{q}_{s[2:]}', q, [s]))
    pairs = [('C1', 'P_hook1', 'P_hook2'), ('C2', 'P_hook1', 'P_hook3'), ('C3', 'P_ch1', 'P_ch2'),
             ('C4', 'P_ch2', 'P_cl3'), ('C5', 'P_v1', 'P_v2'), ('C6_control', 'P_v1', 'P_ch1a')]
    for name, a, b in pairs:
        out.append((name, 'C', [a, b]))
    out.append(('D1_A1_W1s', 'A1', ['W1s']))
    out.append(('D2_A1_W2s', 'A1', ['W2s']))
    out.append(('E1_grid', 'E', ['E_grid']))
    return out


def plan_v3(duration):
    """Config-driven plan: section clips of at most 20 s, pair members, one grid-check clip."""
    clips = {}
    for name, (a, b) in CONFIG['sections'].items():
        start, end = beat(a), duration if b is None else beat(b)
        end = min(end, duration)
        n = max(1, int((end - start) // 20) + (1 if (end - start) % 20 > 2 else 0))
        if n == 1:
            clips[f'S_{name}'] = (start, end)
        else:
            step = (end - start) / n
            for i in range(n):
                clips[f'S_{name}_{i + 1}'] = (round(start + i * step, 3), round(start + (i + 1) * step, 3))
    for group in ('pairs', 'control_pairs', 'intensity_pairs'):
        for _, a, b in CONFIG.get(group, []):
            for m in (a, b):
                if m not in clips and m in CONFIG.get('clips', {}):
                    x, y = CONFIG['clips'][m]
                    clips[m] = (beat(x), duration if y is None else beat(y))
    for group in ('pairs', 'control_pairs', 'intensity_pairs'):
        for pid, a, b in CONFIG.get(group, []):
            for m in (a, b):
                if m not in clips:
                    raise SystemExit(f'{group} {pid}: unknown clip {m!r}. Available: {sorted(clips)}')
    first = next(iter(CONFIG['sections'].values()))[0]
    clips['E_grid'] = (beat(first), min(beat(first) + 30, duration))
    return clips


def calls_v3(clips):
    """Protocol v3 = framework rules 1–11: short clips, one value per call, pairs in both orders, lyrics gated."""
    out = []
    for name in [c for c in clips if c.startswith('S_')]:
        out.append((f'VP_{name[2:]}', 'VP', [name]))      # vocal present? gates lyrics
        out.append((f'B3_{name[2:]}', 'B3', [name]))
        out.append((f'B1_{name[2:]}', 'B1v', [name]))
    for pid, a, b in CONFIG.get('pairs', []) + CONFIG.get('control_pairs', []):
        out += [(f'{pid}_AB', 'C', [a, b]), (f'{pid}_BA', 'C', [b, a]),
                (f'{pid}_CM_AB', 'CM', [a, b]), (f'{pid}_CM_BA', 'CM', [b, a])]
    for pid, a, b in CONFIG.get('intensity_pairs', []):
        out += [(f'{pid}_AB', 'PI', [a, b]), (f'{pid}_BA', 'PI', [b, a])]
    out.append(('E1_grid', 'E', ['E_grid']))
    return out


def calls_v2(clips):
    out = [(f'V2_CP_{a}', 'CP', [f'CP_{a}']) for a in (52, 60, 68, 76, 84)]
    out += [('V2_PI_verse1_vs_chorus1', 'PI', ['P_v1', 'P_ch1a']), ('V2_PI_chorus2_vs_climax3', 'PI', ['P_ch2', 'P_cl3']),
            ('V2_PI_verse2a_vs_verse2b', 'PI', ['S_verse2a', 'S_verse2b']), ('V2_PI_hook2_vs_chorus1', 'PI', ['S_hook2', 'P_ch1a']),
            ('V2_PI_control_hook1_vs_hook2', 'PI', ['P_hook1', 'P_hook2'])]
    out.append(('V2_CM_chorus1_vs_chorus2', 'CM', ['P_ch1', 'P_ch2']))
    out += [(f'V2_A4_{s}', 'A4', [f'S_{s}']) for s in ('verse1', 'chorus1', 'chorus2', 'climax3')]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--clips', required=True, type=Path, help='scratch directory for extracted clips')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--only', default='', help='comma-separated call ids')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--protocol', default='v1', choices=['v1', 'v2', 'v3'])
    parser.add_argument('--config', type=Path, default=None, help='song config JSON (required for v3)')
    args = parser.parse_args()
    global CONFIG
    if args.config:
        CONFIG = json.loads(args.config.read_text())
        GRID['bpm'] = float(CONFIG['bpm'])
        GRID['offset_seconds'] = float(CONFIG['offset_seconds'])
    if args.protocol == 'v3' and CONFIG is None:
        parser.error('--protocol v3 requires --config')

    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                            str(args.audio)], capture_output=True, text=True, check=True)
    duration = float(probe.stdout.strip())
    clips = plan_v3(duration) if args.protocol == 'v3' else plan(duration)
    todo = {'v1': calls, 'v2': calls_v2, 'v3': calls_v3}[args.protocol](clips)
    if args.only:
        wanted = set(args.only.split(','))
        todo = [c for c in todo if c[0] in wanted]
    if args.list:
        for name, q, members in todo:
            print(name, q, [(m, clips[m]) for m in members])
        return
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'calls').mkdir(exist_ok=True)
    args.clips.mkdir(parents=True, exist_ok=True)
    source_sha = hashlib.sha256(args.audio.read_bytes()).hexdigest()

    needed = sorted({m for _, _, members in todo for m in members})
    clip_meta = {}
    for name in needed:
        a, b = clips[name]
        path = args.clips / f'{name}.wav'
        actual = extract(args.audio, path, a, b)
        clip_meta[name] = {'from_seconds': a, 'to_seconds': round(b, 3), 'decoded_seconds': round(actual, 3),
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'path': str(path)}
    manifest = {'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'source_path': str(args.audio.resolve()),
                'source_sha256': source_sha, 'source_duration_seconds': duration, 'grid': GRID,
                'model': str(args.model.resolve()), 'backend': 'mlx-audio', 'temperature': 0.0,
                'time_markers': 'enabled (model-native, every 2 s, clip-relative)',
                'clips': clip_meta, 'questions': {k: v[0] for k, v in Q.items()}}
    manifest['config'] = CONFIG
    (args.out / ('manifest.json' if args.protocol == 'v1' else f'manifest-{args.protocol}.json')).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')

    import mlx.core as mx
    from mlx_audio.stt import load
    started = time.monotonic()
    model = load(str(args.model), strict=True)
    print(f'model loaded in {time.monotonic() - started:.1f}s', file=sys.stderr, flush=True)

    log = (args.out / 'calls.jsonl').open('a')
    index = 0
    while index < len(todo):
        name, q, members = todo[index]
        index += 1
        text, max_tokens = Q[q]
        prompt = pair_chat(text) if len(members) == 2 else chat(text, 1)
        audio = [clip_meta[m]['path'] for m in members]
        mx.reset_peak_memory()
        began = time.monotonic()
        try:
            result = model.generate(audio if len(audio) > 1 else audio[0], prompt=prompt, max_tokens=max_tokens,
                                    temperature=0.0, prefill_step_size=512, strip_thinking=True, verbose=False)
            record = {'answer': result.text, 'generation_tokens': result.generation_tokens,
                      'prompt_tokens': result.prompt_tokens,
                      'output_may_be_truncated': result.generation_tokens >= max_tokens}
        except Exception as error:  # record and continue; the run is a pilot
            record = {'error': f'{type(error).__name__}: {error}'}
        record.update({'id': name, 'question_id': q, 'question': text, 'clips': {m: clip_meta[m] for m in members},
                       'absolute_offset_seconds': [clip_meta[m]['from_seconds'] for m in members],
                       'elapsed_seconds': round(time.monotonic() - began, 2),
                       'mlx_peak_memory_bytes': mx.get_peak_memory()})
        mx.clear_cache()
        (args.out / 'calls' / f'{name}.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
        log.write(json.dumps(record, ensure_ascii=False) + '\n')
        log.flush()
        print(f'{name}: {record["elapsed_seconds"]}s {"ERROR " + record["error"] if "error" in record else record["answer"][:160]!r}',
              file=sys.stderr, flush=True)
        if args.protocol == 'v3' and q == 'VP' and 'answer' in record:
            # Rule 8: lyrics only where singing is present. Prefer measured vocal ranges from the config
            # (the model answered VOCALS on an instrumental clip in a smoke test); fall back to the model's answer.
            a, b = clip_meta[members[0]]['from_seconds'], clip_meta[members[0]]['to_seconds']
            ranges = CONFIG.get('vocal_ranges_seconds')
            if ranges is not None:
                gate = any(min(b, y) - max(a, x) >= 2.0 for x, y in ranges)
            else:
                gate = record['answer'].strip().upper().startswith('VOCALS')
            if gate:
                todo.append((f'A4_{name[3:]}', 'A4', members))
    log.close()


if __name__ == '__main__':
    main()
