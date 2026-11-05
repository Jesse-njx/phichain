"""Explicit, editable authoring operations for native PhiChain format 6.

This is an agent's structured tool kit, not an arbitrary natural-language parser.
No editor connection or user file is changed by these pure helpers or the CLI.
"""
from __future__ import annotations
import argparse
import copy
from fractions import Fraction
import json
import math
from pathlib import Path

KINDS = {'tap', 'drag', 'hold', 'flick'}
EVENT_KINDS = {'x', 'y', 'rotation', 'opacity', 'speed'}
EASINGS = {'linear', 'ease_in_sine', 'ease_out_sine', 'ease_in_out_sine',
           'ease_in_quad', 'ease_out_quad', 'ease_in_out_quad',
           'ease_in_cubic', 'ease_out_cubic', 'ease_in_out_cubic'}
MAX_BEAT = 1_000_000
MAX_NOTES = 100_000


def finite(value, name, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite numeric')
    if low is not None and value < low or high is not None and value > high:
        raise ValueError(f'{name} outside [{low}, {high}]')
    return value


def fraction(value):
    """Accept exact beat strings, numbers, Fractions, or canonical native triples."""
    if isinstance(value, bool):
        raise ValueError('Beat cannot be boolean')
    if isinstance(value, list):
        if len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, int) for v in value):
            raise ValueError('Beat must have three integers')
        whole, part, denominator = value
        if not 0 <= whole <= MAX_BEAT or not 0 <= part < denominator <= 10000:
            raise ValueError('Beat triple must be canonical and nonnegative')
        return Fraction(whole) + Fraction(part, denominator)
    try:
        result = value if isinstance(value, Fraction) else Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError) as error:
        raise ValueError('Invalid beat') from error
    if not 0 <= result <= MAX_BEAT or result.denominator > 10000:
        raise ValueError('Beat out of range or denominator exceeds 10000; use exact beat strings')
    return result


def beat(value):
    result = fraction(value)
    whole = result.numerator // result.denominator
    part = result - whole
    return [whole, part.numerator, part.denominator]


def note(kind, at, x, *, duration=None, above=True, speed=1):
    if kind not in KINDS:
        raise ValueError(f'Unknown note kind {kind}')
    if not isinstance(above, bool):
        raise ValueError('above must be boolean')
    result = dict(kind=kind, above=above, beat=beat(at), x=finite(x, 'x'),
                  speed=finite(speed, 'speed', 0.000001))
    if kind == 'hold':
        if duration is None or fraction(duration) <= 0:
            raise ValueError('Hold requires positive duration in beats')
        if fraction(at) + fraction(duration) > MAX_BEAT:
            raise ValueError('Hold tail out of range')
        result['hold_beat'] = beat(duration)
    elif duration is not None:
        raise ValueError('Only hold notes accept duration')
    return result


def event(kind, start, end, a, b=None, easing='linear'):
    if kind not in EVENT_KINDS:
        raise ValueError(f'Unknown event kind {kind}')
    if fraction(end) <= fraction(start):
        raise ValueError('Event duration must be positive (avoids zero-length tween division)')
    if easing not in EASINGS:
        raise ValueError('Unsupported authoring easing; use native editor for other easing families')
    lo, hi = (0, 1) if kind == 'opacity' else (None, None)
    finite(a, kind, lo, hi)
    if b is None:
        value = dict(type='constant', value=a)
    else:
        finite(b, kind, lo, hi)
        value = dict(type='transition', start=a, end=b, easing=dict(type=easing))
    return dict(kind=kind, start_beat=beat(start), end_beat=beat(end), value=value)


def line(name, notes=None, events=None, children=None):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Line requires nonempty name')
    if events is None:
        events = [event(k, 0, 1, v) for k, v in [('x', 0), ('y', 0),
                  ('rotation', 0), ('opacity', 1), ('speed', 10)]]
    return dict(name=name, notes=copy.deepcopy(notes or []), events=copy.deepcopy(events),
                children=copy.deepcopy(children or []), curve_note_tracks=[])


def chart(lines, bpm=120, offset=0, bpm_list=None):
    return dict(format=6, offset=finite(offset, 'offset'),
                bpm_list=copy.deepcopy(bpm_list) if bpm_list is not None else
                [dict(beat=beat(0), bpm=finite(bpm, 'bpm', 0.000001))],
                lines=copy.deepcopy(lines))


def pattern(kind, start, count, step='1/4', lanes=(-360, -120, 120, 360),
            order=None, note_kind='tap', above=True, speed=1, duration=None):
    """Build stairs, alternating, chord, or drag_arc; count counts onsets.

    stairs may use any explicit lane order; drag_arc traverses lanes evenly.
    A chord visits every lane at each onset; an alternating pattern needs 2 lanes.
    note_kind can be a kind or a repeating list of kinds (duration only for holds).
    """
    if kind not in {'stairs', 'alternating', 'chord', 'drag_arc'}:
        raise ValueError('Unknown pattern kind')
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
        raise ValueError('count must be 1..10000')
    if not isinstance(lanes, (list, tuple)) or not 1 <= len(lanes) <= 10:
        raise ValueError('lanes must contain 1..10 native x values')
    for x in lanes:
        finite(x, 'lane x')
    if len(set(lanes)) != len(lanes):
        raise ValueError('Lane positions must be distinct')
    if kind == 'alternating' and len(lanes) != 2:
        raise ValueError('Alternating needs exactly two lanes')
    order = list(range(len(lanes))) if order is None else order
    if not isinstance(order, (list, tuple)) or not order or any(
            isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(lanes) for i in order):
        raise ValueError('order must contain valid lane indices')
    kinds = [note_kind] if isinstance(note_kind, str) else note_kind
    if not isinstance(kinds, (list, tuple)) or not kinds or any(k not in KINDS for k in kinds):
        raise ValueError('note_kind must be a kind or a nonempty kind cycle')
    if kind == 'drag_arc' and kinds != ['drag']:
        raise ValueError('drag_arc requires note_kind="drag"')
    start, step = fraction(start), fraction(step)
    if step <= 0:
        raise ValueError('step must be positive')
    result = []
    for i in range(count):
        at = start + step * i
        nk = kinds[i % len(kinds)]
        if kind == 'chord':
            xs = lanes
        elif kind == 'drag_arc':
            position = i * (len(lanes) - 1) / max(1, count - 1)
            j = min(int(position), len(lanes) - 2) if len(lanes) > 1 else 0
            xs = [lanes[0] if len(lanes) == 1 else lanes[j] +
                  (lanes[j + 1] - lanes[j]) * (position - j)]
        else:
            xs = [lanes[order[i % len(order)]]]
        result.extend(note(nk, at, x, duration=duration if nk == 'hold' else None,
                           above=above, speed=speed) for x in xs)
    return result


def transform_notes(notes, *, start=0, end=MAX_BEAT, shift=0, mirror=False,
                    scale=1, speed_multiplier=1, beat_shift=0, kind=None, above=None):
    """Copy notes; edit only heads in [start,end), preserving hold durations."""
    start, end = fraction(start), fraction(end)
    if start >= end:
        raise ValueError('Selection end must exceed start')
    finite(shift, 'shift'); finite(scale, 'scale', 0.000001)
    finite(speed_multiplier, 'speed_multiplier', 0.000001)
    if not isinstance(mirror, bool) or above is not None and not isinstance(above, bool):
        raise ValueError('mirror/above must be boolean')
    if kind is not None and kind not in KINDS - {'hold'}:
        raise ValueError('Kind conversion accepts tap, drag, flick; create holds with explicit duration')
    try:
        beat_shift = Fraction(str(beat_shift))
    except (ValueError, ZeroDivisionError):
        raise ValueError('Invalid beat_shift')
    result = copy.deepcopy(notes)
    for n in result:
        if start <= fraction(n['beat']) < end:
            n['beat'] = beat(fraction(n['beat']) + beat_shift)
            n['x'] = finite(((-1 if mirror else 1) * n['x']) * scale + shift, 'x')
            n['speed'] = finite(n['speed'] * speed_multiplier, 'speed', 0.000001)
            if kind is not None:
                n['kind'] = kind
                n.pop('hold_beat', None)
            if above is not None:
                n['above'] = above
    return result


def seconds_at(at, bpm_list, offset=0):
    """Exact piecewise beat-to-audio time. offset is native milliseconds."""
    at = fraction(at)
    total = Fraction(str(offset)) / 1000
    for i, point in enumerate(bpm_list):
        start = fraction(point['beat'])
        end = min(at, fraction(bpm_list[i + 1]['beat'])) if i + 1 < len(bpm_list) else at
        if at < start:
            break
        total += (end - start) * 60 / Fraction(str(point['bpm']))
        if end == at:
            break
    return float(total)


def compile_spec(spec):
    """Compile editable JSON instructions; reject unknown operation keys."""
    allowed = {'bpm', 'bpm_list', 'offset', 'lines'}
    if not isinstance(spec, dict) or set(spec) - allowed:
        raise ValueError('Unknown specification keys')
    compiled = []
    for source in spec['lines']:
        if set(source) - {'name', 'notes', 'patterns', 'events', 'transforms'}:
            raise ValueError('Unknown line specification keys')
        notes = copy.deepcopy(source.get('notes', []))
        for p in source.get('patterns', []):
            notes.extend(pattern(**p))
        for transform in source.get('transforms', []):
            notes = transform_notes(notes, **transform)
        notes.sort(key=lambda n: (fraction(n['beat']), n['x']))
        compiled.append(line(source['name'], notes, source.get('events')))
    return chart(compiled, bpm=spec.get('bpm', 120), offset=spec.get('offset', 0),
                 bpm_list=spec.get('bpm_list'))


def bridge_operations(native_line, line_id, *, include_events=False):
    """Explicit append plan for apply_edits; replacing event tracks needs deletion.

    No guard is inferred. Caller reads context and supplies session/revision, runs
    native validate_chart, and checks every receipt. Never retry an unknown result.
    """
    if not isinstance(line_id, str) or not line_id:
        raise ValueError('line_id required')
    operations = [dict(op='create_note', line_id=line_id, note=copy.deepcopy(n))
                  for n in native_line['notes']]
    if include_events:
        operations += [dict(op='create_event', line_id=line_id, event=copy.deepcopy(e))
                       for e in native_line['events']]
    return operations


def _ease(t, kind):
    if kind == 'linear': return t
    if kind == 'ease_in_sine': return 1 - math.cos(t * math.pi / 2)
    if kind == 'ease_out_sine': return math.sin(t * math.pi / 2)
    if kind == 'ease_in_out_sine': return (1 - math.cos(math.pi * t)) / 2
    degree = 2 if 'quad' in kind else 3
    if kind.startswith('ease_in_out_'):
        return 2 ** (degree - 1) * t ** degree if t < .5 else 1 - (-2 * t + 2) ** degree / 2
    if kind.startswith('ease_in_'): return t ** degree
    return 1 - (1 - t) ** degree


def _evaluate(events, kind, at, default):
    affecting, inherited = [], []
    for e in events:
        if e['kind'] != kind: continue
        start, end = fraction(e['start_beat']), fraction(e['end_beat'])
        v = e['value']
        a = v['value'] if v['type'] == 'constant' else v['start']
        b = v['value'] if v['type'] == 'constant' else v['end']
        if start <= at <= end:
            t = float((at - start) / (end - start))
            affecting.append(a if v['type'] == 'constant' else
                             a + (b - a) * _ease(t, v['easing']['type']))
        elif at > end:
            inherited.append((end, b))
    # Native EventEvaluationResult chooses largest value for overlapping affecting
    # events, then latest end time for inherited events. Equal inherited times are
    # ambiguous: overlap findings below require author review.
    if affecting: return max(affecting)
    return max(inherited, key=lambda p: p[0])[1] if inherited else default


def validate(native, max_contacts=2, *, audio_duration=None, aspect_ratio=16/9):
    """Schema + hold-aware contact budget + sampled hit geometry findings.

    Contact budget conservatively reserves one finger per active hold and one per
    head, including drag/flick. It is a safety screen, not playability proof. Only
    supported easing families and explicit notes are accepted; curve tracks need
    native compilation before this check. Motion during approach needs video QA.
    """
    findings, records = [], []
    def add(severity, code, path, message, at=None):
        row = dict(severity=severity, code=code, path=path, message=message)
        if at is not None: row['beat'] = float(at)
        findings.append(row)
    try:
        if isinstance(max_contacts, bool) or not isinstance(max_contacts, int) or not 1 <= max_contacts <= 10:
            raise ValueError('max_contacts must be 1..10')
        finite(aspect_ratio, 'aspect_ratio', .2, 5)
        if audio_duration is not None: finite(audio_duration, 'audio_duration', 0)
        if not isinstance(native, dict) or native.get('format') != 6:
            raise ValueError('Expected native format 6')
        finite(native['offset'], 'offset')
        bpm_list = native['bpm_list']
        if not isinstance(bpm_list, list) or not bpm_list or fraction(bpm_list[0]['beat']) != 0:
            raise ValueError('BPM map must begin at beat zero')
        previous = None
        for point in bpm_list:
            at = fraction(point['beat']); finite(point['bpm'], 'bpm', 0.000001)
            if previous is not None and at <= previous:
                raise ValueError('BPM entries must be strictly increasing')
            previous = at
        if not isinstance(native['lines'], list) or not native['lines']:
            raise ValueError('Chart requires lines')
    except (KeyError, ValueError, TypeError) as error:
        return dict(valid=False, findings=[dict(severity='error', code='schema', path='chart', message=str(error))])

    height = 1350 / aspect_ratio
    def visit(lines, ancestors=(), prefix='lines', depth=0):
        if depth > 32:
            add('error', 'hierarchy_depth', prefix, 'Hierarchy exceeds 32 levels'); return
        for i, current in enumerate(lines):
            path = f'{prefix}[{i}]'
            try:
                if not isinstance(current, dict) or not isinstance(current['name'], str):
                    raise ValueError('Line requires name')
                if not isinstance(current['events'], list) or not isinstance(current['notes'], list) or not isinstance(current['children'], list):
                    raise ValueError('Line notes/events/children must be arrays')
                if current.get('curve_note_tracks'):
                    raise ValueError('Compile generated curve tracks natively before validation')
                for j, e in enumerate(current['events']):
                    v = e['value']
                    if v['type'] == 'constant':
                        expected = event(e['kind'], e['start_beat'], e['end_beat'], v['value'])
                    elif v['type'] == 'transition':
                        expected = event(e['kind'], e['start_beat'], e['end_beat'], v['start'], v['end'], v['easing']['type'])
                    else: raise ValueError('Unknown event value type')
                    if e != expected: raise ValueError(f'Event {j} has unsupported fields or noncanonical beats')
                for k in EVENT_KINDS:
                    ordered = sorted([e for e in current['events'] if e['kind'] == k], key=lambda e: fraction(e['start_beat']))
                    last_end = None
                    for e in ordered:
                        start, end = fraction(e['start_beat']), fraction(e['end_beat'])
                        if last_end is not None and start < last_end:
                            add('warning', 'event_overlap', path, f'{k} tracks overlap; native evaluation takes maximum affecting value', start)
                        last_end = max(last_end or end, end)
            except (KeyError, ValueError, TypeError, IndexError) as error:
                add('error', 'schema', path, str(error)); continue
            chain = ancestors + (current,)
            identities = set()
            for j, n in enumerate(current['notes']):
                np = f'{path}.notes[{j}]'
                try:
                    expected = note(n['kind'], n['beat'], n['x'], duration=n.get('hold_beat'), above=n['above'], speed=n['speed'])
                    if n != expected: raise ValueError('Unsupported note fields or noncanonical beat representation')
                    at = fraction(n['beat']); tail = at + fraction(n.get('hold_beat', 0))
                    key = (at, n['above'], n['x'])
                    if key in identities: add('error', 'duplicate_note', np, 'Same line, beat, side and x', at)
                    identities.add(key)
                    records.append((at, tail, np, n, chain))
                    if len(records) > MAX_NOTES:
                        raise ValueError('Chart exceeds authoring note cap')
                    for endpoint in set((at, tail)):
                        x, y = n['x'], 0
                        for owner in reversed(chain):
                            es = owner['events']
                            angle = math.radians(_evaluate(es, 'rotation', endpoint, 0))
                            x, y = (x * math.cos(angle) - y * math.sin(angle) + _evaluate(es, 'x', endpoint, 0),
                                    x * math.sin(angle) + y * math.cos(angle) + _evaluate(es, 'y', endpoint, 0) * height / 900)
                        if abs(x) > 675 or abs(y) > height / 2:
                            add('warning', 'offscreen_hit', np, f'Endpoint world center ({x:.1f},{y:.1f}) outside viewport', endpoint)
                        if _evaluate(current['events'], 'opacity', endpoint, 0) <= 0:
                            add('warning', 'invisible_line', np, 'Judge line invisible at endpoint', endpoint)
                        if _evaluate(current['events'], 'speed', endpoint, 10) <= 0:
                            add('warning', 'nonpositive_scroll', np, 'Line has zero/negative scroll at endpoint', endpoint)
                    head_seconds = seconds_at(at, bpm_list, native['offset'])
                    tail_seconds = seconds_at(tail, bpm_list, native['offset'])
                    if head_seconds < 0 or audio_duration is not None and tail_seconds > audio_duration:
                        add('error', 'outside_audio', np, f'Note occupies {head_seconds:.4f}..{tail_seconds:.4f} seconds', at)
                except (KeyError, ValueError, TypeError, IndexError) as error:
                    add('error', 'schema', np, str(error))
            visit(current['children'], chain, path + '.children', depth + 1)
    visit(native['lines'])
    # Sweep all lines globally. Releases precede heads at the same exact beat.
    points = {}
    for at, tail, path, n, chain in records:
        p = points.setdefault(at, dict(heads=[], releases=0))
        p['heads'].append(path)
        if tail > at:
            points.setdefault(tail, dict(heads=[], releases=0))['releases'] += 1
    active = maximum = 0
    holds_at = {}
    for at, tail, path, n, chain in records:
        if tail > at: holds_at[at] = holds_at.get(at, 0) + 1
    for at, p in sorted(points.items()):
        active -= p['releases']
        required = active + len(p['heads'])
        maximum = max(maximum, required)
        if required > max_contacts:
            add('error', 'contact_budget', 'chart', f'{active} held contacts + {len(p["heads"])} heads exceed {max_contacts}', at)
        active += holds_at.get(at, 0)
    return dict(valid=not any(f['severity'] == 'error' for f in findings),
                note_count=len(records), maximum_conservative_contacts=maximum,
                contact_model='active holds plus simultaneous heads, release before head',
                findings=findings)



def plan_live(context, section, line_id, *, append_notes=None, transform=None,
              event_updates=None, append_events=None, max_contacts=2):
    """Compile ONE guarded live-editor transaction, without applying it.

    Requires full-chart read_section (0..1000001, no line filter), matching context.
    Supports every note kind, range transforms, explicit event-ID replacement and
    append. Curve tracks and unsupported easing fail closed. Maximum 1000 edits.
    Returned validation covers unchanged notes/other lines/active holds too.
    """
    guard = {k: context[k] for k in ('session', 'revision')}
    if any(section[k] != guard[k] for k in guard):
        raise ValueError('Context and section revisions differ; read again')
    if section.get('start_beat') != 0 or section.get('end_beat', 0) < 1000001:
        raise ValueError('Read the full chart before planning live edits')
    if len(section['notes']) != context['note_count'] or len(section['events']) != context['event_count']:
        raise ValueError('Section appears filtered or incomplete')
    if section.get('curve_tracks'):
        raise ValueError('Live plan does not handle generated curve tracks')
    line_rows = {r['id']: r for r in section['lines']}
    if line_id not in line_rows: raise ValueError('Unknown line_id')
    prospective = {key: line(row['name'], [], []) for key, row in line_rows.items()}
    notes_by_id = {r['id']: copy.deepcopy(r) for r in section['notes']}
    events_by_id = {r['id']: copy.deepcopy(r) for r in section['events']}
    operations = []
    if transform is not None:
        for row in notes_by_id.values():
            if row['line_id'] != line_id: continue
            updated = transform_notes([row['note']], **transform)[0]
            if updated != row['note']:
                operations.append(dict(op='update_note', id=row['id'], note=updated))
                row['note'] = updated
    touched = set()
    for update in event_updates or []:
        ident = update['id']
        if ident in touched: raise ValueError('Each event may be updated once')
        touched.add(ident)
        if ident not in events_by_id or events_by_id[ident]['line_id'] != line_id:
            raise ValueError('Event update must belong to target line')
        events_by_id[ident]['event'] = copy.deepcopy(update['event'])
        operations.append(dict(op='update_event', id=ident, event=copy.deepcopy(update['event'])))
    for row in notes_by_id.values(): prospective[row['line_id']]['notes'].append(row['note'])
    for row in events_by_id.values(): prospective[row['line_id']]['events'].append(row['event'])
    for n in append_notes or []:
        prospective[line_id]['notes'].append(copy.deepcopy(n))
        operations.append(dict(op='create_note', line_id=line_id, note=copy.deepcopy(n)))
    for e in append_events or []:
        prospective[line_id]['events'].append(copy.deepcopy(e))
        operations.append(dict(op='create_event', line_id=line_id, event=copy.deepcopy(e)))
    if not 1 <= len(operations) <= 1000:
        raise ValueError('Plan must contain 1..1000 edits; split authored phrases after reading fresh state')
    roots, seen = [], set()
    for key, row in line_rows.items():
        parent = row.get('parent_id')
        if parent is None: roots.append(prospective[key])
        elif parent in prospective: prospective[parent]['children'].append(prospective[key])
        else: raise ValueError('Unknown line parent')
        # Detect disconnected cycles before serializing nested dictionaries.
        node = key; ancestry = set()
        while node is not None:
            if node in ancestry: raise ValueError('Line hierarchy cycle')
            ancestry.add(node); node = line_rows[node].get('parent_id')
    native = chart(roots, offset=context['offset'], bpm_list=context['bpm_list'])
    report = validate(native, max_contacts, audio_duration=context.get('audio_duration_seconds'))
    if not report['valid']:
        raise ValueError('Prospective chart validation failed: ' + json.dumps(report['findings'][:10]))
    return dict(**guard, operations=operations, validation=report)


def apply_live(bridge, plan):
    """Apply a preflighted plan once. Save is separate; failures are never retried.

    This explicit mutating helper is only for a user-authorized live edit. Server's
    call_editor can be supplied as bridge via a closure; MCP remains preferred.
    """
    context = bridge('get_context', {})
    if 'error' in context: raise ValueError(context['error'])
    if any(context[k] != plan[k] for k in ('session', 'revision')):
        raise ValueError('Chart changed since planning; regenerate plan')
    result = bridge('apply_edits', {k: plan[k] for k in ('session', 'revision', 'operations')})
    if 'error' in result: raise ValueError(result['error'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    c = subs.add_parser('compile', help='compile editable pattern specification to native chart')
    c.add_argument('input', type=Path); c.add_argument('output', type=Path)
    v = subs.add_parser('validate', help='validate a format-6 native chart without edits')
    v.add_argument('input', type=Path)
    for p in (c, v):
        p.add_argument('--max-contacts', type=int, default=2)
        p.add_argument('--audio-duration', type=float)
    args = parser.parse_args(argv)
    try:
        source = json.loads(args.input.read_text())
        native = compile_spec(source) if args.command == 'compile' else source
        report = validate(native, args.max_contacts, audio_duration=args.audio_duration)
        print(json.dumps(report, indent=2))
        if not report['valid']: return 2
        if args.command == 'compile':
            # Never overwrite an existing artifact, even when it was input.
            with args.output.open('x') as handle:
                json.dump(native, handle, indent=2); handle.write('\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
