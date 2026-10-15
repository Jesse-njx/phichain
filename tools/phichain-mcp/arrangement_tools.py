"""Bulk authored tap arrangements, composed through guarded live-editor edits."""
from fractions import Fraction
import math

MAX_NOTES = 10000


def finite(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite and numeric')
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f'{name} is out of range')
    return value


def fraction(beat):
    if (not isinstance(beat, list) or len(beat) != 3 or
            any(isinstance(x, bool) or not isinstance(x, int) for x in beat)):
        raise ValueError('Invalid beat triple')
    whole, part, denominator = beat
    if not 0 <= whole <= 1000000 or not 0 <= part < denominator <= 10000:
        raise ValueError('Beat must be canonical and nonnegative')
    return Fraction(whole) + Fraction(part, denominator)


def beat_at(seconds, context):
    """Elapsed audio seconds -> canonical native beat, including offset/BPM changes."""
    remaining = Fraction(str(seconds)) - Fraction(str(context['offset'])) / 1000
    if remaining < 0:
        raise ValueError('An onset precedes chart beat zero')
    entries = context['bpm_list']
    for i, entry in enumerate(entries):
        beat = fraction(entry['beat'])
        bpm = Fraction(str(entry['bpm']))
        if bpm <= 0:
            raise ValueError('BPM must be positive')
        if i + 1 < len(entries):
            span = (fraction(entries[i + 1]['beat']) - beat) * 60 / bpm
            if remaining >= span:
                remaining -= span
                continue
        result = (beat + remaining * bpm / 60).limit_denominator(10000)
        whole = int(result); part = result - whole
        triple = [whole, part.numerator, part.denominator]
        fraction(triple)
        return triple
    raise ValueError('Missing BPM map')


def compose(local, session, revision, mode, line_id=None, examples=None,
            start_seconds=1, duration_seconds=10, gap_seconds=3,
            horizontal_scale=1, horizontal_shift=0, speed_multiplier=1,
            start_beat=0, end_beat=1000001, max_contacts=2, dry_run=False,
            save=False, render_output_path=None, width=1280, height=720, fps=60):
    """Preflight the complete plan, then apply bounded batches without unsafe retries."""
    from pathlib import Path

    def read(name, args):
        value = local.bridge(name, args)
        if 'error' in value:
            raise ValueError(value['error'])
        return value

    if mode not in ('append', 'replace', 'transform'):
        raise ValueError('mode must be append, replace, or transform')
    finite(horizontal_scale, 'horizontal_scale', .01, 10)
    finite(horizontal_shift, 'horizontal_shift', -.5, .5)
    finite(speed_multiplier, 'speed_multiplier', .01, 10)
    finite(start_beat, 'start_beat', 0, 1000000)
    finite(end_beat, 'end_beat', 0, 1000001)
    if start_beat >= end_beat:
        raise ValueError('end_beat must exceed start_beat')
    if isinstance(max_contacts, bool) or not isinstance(max_contacts, int) or not 1 <= max_contacts <= 6:
        raise ValueError('max_contacts must be an integer from 1 to 6')
    for value, name in [(dry_run, 'dry_run'), (save, 'save')]:
        if not isinstance(value, bool):
            raise ValueError(f'{name} must be boolean')
    if render_output_path:
        path = Path(render_output_path)
        if not path.is_absolute() or path.suffix.lower() != '.mp4' or path.exists():
            raise ValueError('Render output must be a new absolute .mp4 path')
        for value, lo, hi, name in [(width,160,3840,'width'),(height,90,2160,'height'),(fps,1,120,'fps')]:
            if isinstance(value,bool) or not isinstance(value,int) or not lo <= value <= hi:
                raise ValueError(f'Invalid render {name}')
        if width % 2 or height % 2:
            raise ValueError('Render dimensions must be even')
        local.binary('renderer')
    context = read('get_context', {})
    if context['session'] != session or context['revision'] != revision:
        raise ValueError('Chart changed; read context and regenerate the bulk request')
    line_id = line_id or context.get('selected_line_id')
    if line_id not in [line['id'] for line in context['lines']]:
        raise ValueError('Select or supply a current line_id')
    section = read('read_section', dict(start_beat=0, end_beat=1000001, line_id=line_id))
    if section['session'] != session or section['revision'] != revision:
        raise ValueError('Chart changed during preflight; no edits applied')
    selected = [row for row in section['notes']
                if start_beat <= float(fraction(row['note']['beat'])) < end_beat]
    if any(row['note']['kind'] != 'tap' for row in selected) and mode != 'append':
        raise ValueError('Transform/replace only supports tap-only target ranges')
    if mode != 'append' and any(track['line_id'] == line_id for track in section['curve_tracks']):
        raise ValueError('Transform/replace does not support lines with curve tracks')

    operations, planned, guide = [], [], []

    def scaled(note):
        new = dict(note)
        new['x'] = finite(note['x'] * horizontal_scale + horizontal_shift * 1350, 'note x', -600, 600)
        new['speed'] = finite(note['speed'] * speed_multiplier, 'note speed', .000001)
        return new

    if mode == 'transform':
        if examples is not None:
            raise ValueError('transform does not accept examples')
        if not selected:
            raise ValueError('No target tap notes in the requested range')
        for row in selected:
            note = scaled(row['note'])
            planned.append(note)
            operations.append(dict(op='update_note', id=row['id'], note=note))
    else:
        if not isinstance(examples, list) or not 1 <= len(examples) <= 100:
            raise ValueError('append/replace requires 1–100 authored examples')
        finite(start_seconds, 'start_seconds', 0)
        finite(duration_seconds, 'duration_seconds', .01, 600)
        finite(gap_seconds, 'gap_seconds', 0, 600)
        if mode == 'replace':
            operations.extend(dict(op='delete_note', id=row['id']) for row in selected)
        onset = Fraction(str(start_seconds))
        for number, example in enumerate(examples, 1):
            if not isinstance(example.get('name'), str) or not example['name'].strip():
                raise ValueError('Every example requires a name')
            duration = example.get('duration_seconds', duration_seconds)
            finite(duration, 'example duration', .01, 600)
            duration = Fraction(str(duration))
            phrases = example.get('phrases')
            if not isinstance(phrases, list) or not phrases:
                raise ValueError('Every example requires authored phrases')
            phrase_start = Fraction(0); groups = {}; first = len(planned) + 1
            for phrase in phrases:
                length = phrase['duration_seconds']
                finite(length, 'phrase duration', .01, 600)
                length = Fraction(str(length))
                scale = finite(phrase.get('horizontal_scale', 1), 'phrase scale', .01, 10)
                shift = finite(phrase.get('horizontal_shift', 0), 'phrase shift', -.5, .5)
                for event in phrase['events']:
                    relative = finite(event['time_seconds'], 'relative onset', 0)
                    relative = Fraction(str(relative))
                    if relative >= length:
                        raise ValueError('Phrase events must lie in [0, phrase duration)')
                    xs = event['x']
                    if not isinstance(xs, list) or not 1 <= len(xs) <= max_contacts:
                        raise ValueError('Chord exceeds max_contacts or is empty')
                    at = onset + phrase_start + relative
                    group = groups.setdefault(at, [])
                    for x in xs:
                        finite(x, 'normalized x', -.5, .5)
                        group.append((x * scale + shift) * 1350)
                phrase_start += length
            if phrase_start != duration:
                raise ValueError('Phrase durations must sum to the example duration')
            if 'end_chord' in example:
                chord = example['end_chord']
                if not isinstance(chord, list) or not 1 <= len(chord) <= max_contacts:
                    raise ValueError('Invalid end_chord')
                groups[onset + duration] = [finite(x, 'end chord x', -.5, .5) * 1350 for x in chord]
            if not groups or min(groups) != onset:
                raise ValueError('Each example must start with a hit at relative zero')
            for at, xs in sorted(groups.items()):
                if len(xs) > max_contacts:
                    raise ValueError('Combined simultaneous events exceed max_contacts')
                if at > Fraction(str(context['audio_duration_seconds'])):
                    raise ValueError('Arrangement exceeds the current audio duration')
                beat = beat_at(float(at), context)
                if not start_beat <= float(fraction(beat)) < end_beat:
                    raise ValueError('Generated note falls outside the target beat range')
                for x in sorted(xs):
                    note = scaled(dict(kind='tap', above=True, beat=beat, x=x, speed=1))
                    planned.append(note)
                    operations.append(dict(op='create_note', line_id=line_id, note=note))
                    if len(planned) > MAX_NOTES:
                        raise ValueError('A bulk request supports at most 10000 notes')
            guide.append(dict(example=number, name=example['name'], start_seconds=float(onset),
                              end_seconds=float(onset + duration), first_note=first, last_note=len(planned)))
            onset += duration + Fraction(str(gap_seconds))
    if len(planned) > MAX_NOTES or len(operations) > 2 * MAX_NOTES:
        raise ValueError('Bulk request exceeds 10000 notes / 20000 operations')

    # Check the prospective line, including untouched notes, before ANY writes.
    replaced_ids = {row['id'] for row in selected} if mode != 'append' else set()
    prospective = [row['note'] for row in section['notes'] if row['id'] not in replaced_ids] + planned
    counts = {}; identities = set()
    for note in prospective:
        beat = fraction(note['beat'])
        key = (beat, note['above'], round(note['x'], 4))
        if key in identities:
            raise ValueError('Prospective chart contains duplicate notes')
        identities.add(key)
        counts[beat] = counts.get(beat, 0) + 1
        if counts[beat] > max_contacts:
            raise ValueError('Prospective simultaneous contacts exceed max_contacts')
    render_to = min(600, context['audio_duration_seconds'])
    if render_output_path and guide:
        render_to = guide[-1]['end_seconds'] + min(gap_seconds, 2)
        render_to = min(context['audio_duration_seconds'], render_to)
        if render_to > 600:
            raise ValueError('Bulk preview supports at most the first 600 audio seconds')
    receipt = dict(mode=mode, line_id=line_id, notes_planned=len(planned),
                   operations_planned=len(operations), examples=guide,
                   horizontal_scale=horizontal_scale, horizontal_shift=horizontal_shift,
                   speed_multiplier=speed_multiplier, dry_run=dry_run,
                   session=session, revision=revision, batches_applied=0, operations_applied=0,
                   undo_steps=0, saved=False)
    if dry_run:
        receipt['status'] = 'planned'
        receipt['note_preview'] = planned[:8]
        return receipt
    # Native apply_edits is atomic for each <=1000-operation chunk, with a fresh
    # revision for the next. A later failure is reported, never blindly undone.
    guard = dict(session=session, revision=revision)
    try:
        for offset in range(0, len(operations), 1000):
            chunk = operations[offset:offset + 1000]
            result = read('apply_edits', dict(**guard, operations=chunk))
            guard = {k: result[k] for k in ('session', 'revision')}
            receipt.update(guard)
            receipt['batches_applied'] += 1
            receipt['undo_steps'] += 1
            receipt['operations_applied'] += len(chunk)
        receipt['validation'] = read('validate_chart', dict(start_beat=start_beat,
            end_beat=end_beat, max_contacts=max_contacts))
        if any(receipt['validation'][k] != guard[k] for k in ('session','revision')):
            raise ValueError('Chart changed before final validation; inspect current context')
        if not receipt['validation'].get('valid'):
            receipt.update(status='validation_failed', error='Edits applied, but native validation found issues; inspect findings before saving')
            return receipt
        if save:
            result = read('save', guard)
            receipt['saved'] = result['saved']
        if render_output_path:
            receipt['render'] = local.render_preview(**guard, output_path=render_output_path,
                from_seconds=0, to_seconds=render_to, width=width, height=height, fps=fps)
        receipt['status'] = 'applied'
    except (OSError, ValueError, KeyError) as error:
        receipt.update(status='incomplete', error=str(error),
            recovery='Read current context before any retry. Completed chunks remain as shared undo entries; the last request may have executed after a transport failure.')
    return receipt
