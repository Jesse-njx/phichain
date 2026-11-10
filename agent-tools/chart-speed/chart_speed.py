#!/usr/bin/env python3
"""Compile chart-specific scroll equations once; generate variants without an LLM."""

import argparse
import bisect
import copy
import hashlib
import io
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import types
import unicodedata
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES = ROOT.parent / 'deployments/chart-speed/profiles'
DEFAULT_OUTPUTS = ROOT.parent / 'deployments/chart-speed/outputs'
SIDES = ('notesAbove', 'notesBelow')
ANIMATIONS = ('judgeLineMoveEvents', 'judgeLineRotateEvents', 'judgeLineDisappearEvents')


class ProfileError(ValueError):
    pass


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ProfileError(f'{label} must be a finite number')
    return value


def fields(value, required, optional=(), label='object'):
    if not isinstance(value, dict):
        raise ProfileError(f'{label} must be an object')
    missing, extra = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ProfileError(f'{label}: missing {sorted(missing)}, unknown {sorted(extra)}')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    return json.loads(data.decode('utf-8-sig'), parse_constant=lambda x: (_ for _ in ()).throw(ProfileError(f'Invalid JSON number: {x}')))


class Scroll:
    """Official-v3 constant-speed segments. Integrals are in official floor units."""

    def __init__(self, events, bpm):
        if not isinstance(events, list) or not events:
            raise ProfileError('Each line needs a nonempty speedEvents array')
        self.events, self.starts, self.floors = events, [], []
        self.unit = 1.875 / number(bpm, 'BPM') if bpm > 0 else 0
        if not self.unit:
            raise ProfileError('BPM must be positive')
        cursor, area = 0, 0.0
        for event in events:
            for k in ('startTime', 'endTime', 'value'):
                number(event[k], f'speed event {k}')
            start, end = event['startTime'], event['endTime']
            if start != cursor or end < start:
                raise ProfileError('Speed events must be ordered, contiguous, nonnegative-duration and start at zero')
            self.starts.append(start)
            self.floors.append(area)
            area += (end-start) * event['value'] * self.unit
            if not math.isfinite(area):
                raise ProfileError('Scroll integral overflow')
            cursor = end
        self.end = cursor
        if self.end <= 0 or events[-1]['endTime'] <= events[-1]['startTime']:
            raise ProfileError('Speed timeline needs a positive-duration final segment')

    def index(self, tick):
        number(tick, 'scroll timestamp')
        if tick < 0 or tick > self.end:
            raise ProfileError('Note/constraint lies outside the covered scroll timeline')
        return max(0, bisect.bisect_right(self.starts, tick)-1)

    def floor(self, tick):
        i = self.index(tick)
        return self.floors[i] + (tick-self.starts[i]) * self.events[i]['value'] * self.unit


def validate_chart(chart):
    if not isinstance(chart, dict) or chart.get('formatVersion') != 3:
        raise ProfileError('Only official formatVersion 3 is supported; native/RPE inputs need an explicit prior export')
    number(chart['offset'], 'offset')
    lines = chart['judgeLineList']
    if not isinstance(lines, list) or not lines:
        raise ProfileError('judgeLineList must be a nonempty array')
    count = 0
    for i, line in enumerate(lines):
        bpm = number(line['bpm'], f'line {i} BPM')
        scroll = Scroll(line['speedEvents'], bpm)
        for channel in ANIMATIONS:
            if not isinstance(line.get(channel), list):
                raise ProfileError(f'line {i}: missing {channel}')
            for event in line[channel]:
                keys = ('startTime', 'endTime', 'start', 'end')
                if channel == 'judgeLineMoveEvents':
                    keys += ('start2', 'end2')
                for key in keys:
                    number(event[key], f'line {i} {channel}.{key}')
                # Some official files carry backwards constant-zero opacity
                # records. Keep these opaque source records exactly; they do
                # not describe a negative-alpha note-visibility transition.
                harmless_zero = channel == 'judgeLineDisappearEvents' and event['start'] == event['end'] == 0
                if event['endTime'] < event['startTime'] and not harmless_zero:
                    raise ProfileError(f'line {i}: reversed animation event range')
        for side in SIDES:
            if not isinstance(line.get(side), list):
                raise ProfileError(f'line {i}: missing {side}')
            for note in line[side]:
                if type(note['type']) is not int or note['type'] not in (1, 2, 3, 4):
                    raise ProfileError('Unknown note type')
                if note.get('isFake') or note.get('fake'):
                    raise ProfileError('Fake-note extensions are not supported')
                for key in ('time', 'holdTime', 'positionX', 'speed', 'floorPosition'):
                    number(note[key], f'note {key}')
                # Official charts contain zero-speed Holds. Preserve them; a
                # zero Hold is not an invalid duration or an ordinary note with
                # a zero distance multiplier. No normalization is performed.
                if note['speed'] < 0 or (note['speed'] == 0 and note['type'] != 3) or note['holdTime'] < 0 or (note['type'] == 3 and note['holdTime'] <= 0):
                    raise ProfileError('Invalid note speed or Hold duration')
                scroll.index(note['time'])
                scroll.index(note['time']+note['holdTime'])
                count += 1
    return count


def validate_policy(policy, chart):
    fields(policy, ('multiplier_range', 'lines', 'transparent_tails', 'review'), ('preserve_windows',), 'policy')
    limits = policy['multiplier_range']
    if not isinstance(limits, list) or len(limits) != 2:
        raise ProfileError('multiplier_range requires [minimum, maximum]')
    low, high = [number(x, 'multiplier bound') for x in limits]
    if not 0 < low <= 1 <= high:
        raise ProfileError('Multiplier range must be positive and contain X=1')
    if type(policy['transparent_tails']) is not bool or not isinstance(policy['review'], str) or not policy['review'].strip():
        raise ProfileError('transparent_tails must be boolean and review must describe the actual evidence/limits')
    rules = policy['lines']
    if not isinstance(rules, list) or len(rules) != len(chart['judgeLineList']):
        raise ProfileError('Provide exactly one explicit rule per original line')
    seen = set()
    for rule in rules:
        fields(rule, ('line', 'gain', 'reason'), ('events','note_gains'), 'line rule')
        i = rule['line']
        if type(i) is not int or not 0 <= i < len(rules) or i in seen:
            raise ProfileError('Line indices must be unique and cover the whole chart')
        seen.add(i)
        if not isinstance(rule['reason'], str) or not rule['reason'].strip():
            raise ProfileError('Every line rule needs a reason')
        gains = [number(rule['gain'], 'line gain')]
        overrides = rule.get('events', [])
        if not isinstance(overrides, list):
            raise ProfileError('events overrides must be an array')
        indices = set()
        for override in overrides:
            fields(override, ('event', 'gain', 'reason'), label='event override')
            j = override['event']
            if type(j) is not int or not 0 <= j < len(chart['judgeLineList'][i]['speedEvents']) or j in indices:
                raise ProfileError('Invalid or duplicate speed event index')
            if not isinstance(override['reason'], str) or not override['reason'].strip():
                raise ProfileError('Event overrides need a reason')
            indices.add(j)
            gains.append(number(override['gain'], 'event gain'))
        note_gains = rule.get('note_gains', [])
        if not isinstance(note_gains,list):
            raise ProfileError('note_gains must be an array')
        if note_gains and any(gains):
            raise ProfileError('Per-note gains require an unchanged line scroll timeline')
        note_addresses = set()
        for note_rule in note_gains:
            fields(note_rule,('side','note','gain','reason'),label='note gain')
            side,n = note_rule['side'],note_rule['note']
            if side not in SIDES or type(n) is not int or not 0 <= n < len(chart['judgeLineList'][i][side]):
                raise ProfileError('Invalid per-note gain address')
            if (side,n) in note_addresses:
                raise ProfileError('Duplicate per-note gain address')
            note_addresses.add((side,n))
            if chart['judgeLineList'][i][side][n]['type'] == 3:
                raise ProfileError('Hold head approach cannot be independently scaled by the note.speed field')
            if not isinstance(note_rule['reason'],str) or not note_rule['reason'].strip():
                raise ProfileError('Every per-note gain requires reviewed evidence')
            value = number(note_rule['gain'],'note gain')
            if any(not math.isfinite(1+value*(x-1)) or 1+value*(x-1) <= 0 for x in limits):
                raise ProfileError('A note speed factor becomes nonpositive or nonfinite')
        for gain in gains:
            if any(not math.isfinite(1+gain*(x-1)) or 1+gain*(x-1) <= 0 for x in limits):
                raise ProfileError('An affine factor becomes nonpositive or nonfinite within multiplier_range')
    windows = policy.get('preserve_windows', [])
    if not isinstance(windows, list):
        raise ProfileError('preserve_windows must be an array')
    for window in windows:
        fields(window, ('line', 'side', 'note', 'from', 'to', 'reason'), label='preserved note window')
        i, side, n = window['line'], window['side'], window['note']
        if type(i) is not int or not 0 <= i < len(rules) or side not in SIDES:
            raise ProfileError('Invalid preserved note address')
        notes = chart['judgeLineList'][i][side]
        if type(n) is not int or not 0 <= n < len(notes):
            raise ProfileError('Invalid preserved note index')
        start, end = number(window['from'], 'window start'), number(window['to'], 'window end')
        if not 0 <= start < end <= notes[n]['time']:
            raise ProfileError('Preserved windows must precede the note head, in line-local official ticks')
        if not isinstance(window['reason'], str) or not window['reason'].strip():
            raise ProfileError('Preserved windows need a reason')


def transparent_tails(chart):
    """Persist already-authored final zero opacity, including hidden negative-time carriers."""
    out, repaired = copy.deepcopy(chart), []
    for i, line in enumerate(out['judgeLineList']):
        events = line['judgeLineDisappearEvents']
        if not events:
            raise ProfileError(f'line {i}: no opacity intent; cannot infer a safe transparency repair')
        if any(a['startTime'] > b['startTime'] for a,b in zip(events, events[1:])):
            raise ProfileError('Opacity events must be ordered for tail repair')
        final = events[-1]
        if final['end'] != 0:
            raise ProfileError(f'line {i}: final opacity is not zero; provide an explicit reviewed fade before compiling')
        horizon = max(1_000_000_000, line['speedEvents'][-1]['endTime'])
        if final['start'] == 0 and final['endTime'] >= horizon:
            continue
        start = max(0, final['endTime'])
        # Existing nonzero interpolation is never trimmed or retimed.
        if start >= horizon:
            raise ProfileError('Final fade ends beyond the supported opacity horizon')
        events.append({'startTime':start, 'endTime':horizon, 'start':0.0, 'end':0.0})
        repaired.append({'line':i, 'from_tick':start, 'to_tick':horizon})
    return out, repaired


def check_preserved(base, out, policy):
    """Piecewise-linear distance equality: endpoints + every speed boundary suffice."""
    for window in policy.get('preserve_windows', []):
        i, side, index = window['line'], window['side'], window['note']
        oldline, newline = base['judgeLineList'][i], out['judgeLineList'][i]
        a, b = Scroll(oldline['speedEvents'], oldline['bpm']), Scroll(newline['speedEvents'], newline['bpm'])
        old, new = oldline[side][index], newline[side][index]
        points = {window['from'], window['to']}
        points.update(t for t in a.starts if window['from'] < t < window['to'])
        if old['type'] == 3 and not math.isclose(old['speed'],new['speed'],rel_tol=1e-11,abs_tol=1e-10):
            raise ProfileError(f'Protected Hold length conflict on line {i}, {side}[{index}]')
        for t in points:
            old_distance = (old['floorPosition']-a.floor(t)) * (old['speed'] if old['type'] != 3 else 1)
            new_distance = (new['floorPosition']-b.floor(t)) * (new['speed'] if new['type'] != 3 else 1)
            if not math.isclose(old_distance,new_distance,rel_tol=1e-11,abs_tol=1e-8):
                raise ProfileError(f'Protected trajectory conflict on line {i}, {side}[{index}], tick {t:g}; shared-line speed rules cannot satisfy this window')


def transform(base, policy, multiplier):
    validate_chart(base)
    validate_policy(policy, base)
    x = number(multiplier, 'multiplier')
    low, high = policy['multiplier_range']
    if not low <= x <= high:
        raise ProfileError(f'Multiplier {x:g} outside compiled range [{low:g}, {high:g}]')
    out = copy.deepcopy(base)
    if x == 1:
        return out
    for rule in policy['lines']:
        i = rule['line']
        oldline, newline = base['judgeLineList'][i], out['judgeLineList'][i]
        overrides = {v['event']:v['gain'] for v in rule.get('events', [])}
        gains = [overrides.get(j,rule['gain']) for j in range(len(oldline['speedEvents']))]
        for note_rule in rule.get('note_gains', []):
            note = newline[note_rule['side']][note_rule['note']]
            note['speed'] = number(note['speed']*(1+note_rule['gain']*(x-1)), 'output note speed')
        if not any(gains):
            continue
        oldscroll = Scroll(oldline['speedEvents'], oldline['bpm'])
        factors = [1+gain*(x-1) for gain in gains]
        for j,event in enumerate(newline['speedEvents']):
            event['value'] = number(event['value']*factors[j], 'output speed')
        newscroll = Scroll(newline['speedEvents'], newline['bpm'])
        for j,event in enumerate(newline['speedEvents']):
            event['floorPosition'] = newscroll.floors[j]
        for side in SIDES:
            for old,new in zip(oldline[side],newline[side]):
                # Retain authored landing offsets (and source f32 residuals), rather
                # than silently snapping every floorPosition onto the integral.
                delta = newscroll.floor(old['time'])-oldscroll.floor(old['time'])
                new['floorPosition'] = number(old['floorPosition']+delta, 'output floorPosition')
                if old['type'] == 3:
                    new['speed'] = number(old['speed']*factors[oldscroll.index(old['time'])], 'output Hold speed')
    validate_chart(out)
    check_preserved(base,out,policy)
    verify_invariants(base,out,policy)
    return out


def verify_invariants(base, out, policy=None):
    """Everything except scroll values/floors and absolute Hold speed is invariant."""
    normalized = copy.deepcopy(out)
    if len(base['judgeLineList']) != len(out['judgeLineList']):
        raise ProfileError('Line structure changed')
    allowed_notes = {(r['line'],n['side'],n['note']) for r in (policy or {}).get('lines',[]) for n in r.get('note_gains',[])}
    for line_index,(old,new) in enumerate(zip(base['judgeLineList'],normalized['judgeLineList'])):
        if len(old['speedEvents']) != len(new['speedEvents']):
            raise ProfileError('Speed-event structure changed')
        for a,b in zip(old['speedEvents'],new['speedEvents']):
            for key in ('value','floorPosition'):
                if key in a: b[key] = a[key]
                else: b.pop(key,None)
        for side in SIDES:
            if len(old[side]) != len(new[side]):
                raise ProfileError('Note membership changed')
            for note_index,(a,b) in enumerate(zip(old[side],new[side])):
                b['floorPosition'] = a['floorPosition']
                if a['type'] == 3 or (line_index,side,note_index) in allowed_notes: b['speed'] = a['speed']
    if normalized != base:
        raise ProfileError('Non-scroll fields changed')


def validate_recipe(recipe):
    fields(recipe, ('schema_version','id','name','aliases','source','source_sha256','music','illustration','metadata','policy'), label='recipe')
    if recipe['schema_version'] != 1 or type(recipe['schema_version']) is not int:
        raise ProfileError('Unsupported recipe schema_version')
    if not isinstance(recipe['id'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',recipe['id']):
        raise ProfileError('id must be a lowercase filename-safe slug')
    if not isinstance(recipe['name'],str) or not recipe['name'].strip():
        raise ProfileError('name must be nonempty')
    if not isinstance(recipe['aliases'],list) or not all(isinstance(s,str) and s.strip() for s in recipe['aliases']):
        raise ProfileError('aliases must contain nonempty strings')
    if not isinstance(recipe['metadata'],dict) or not all(isinstance(k,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',k) for k in recipe['metadata']):
        raise ProfileError('metadata must be an object with original credits/level')
    if not isinstance(recipe['source_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',recipe['source_sha256']):
        raise ProfileError('source_sha256 must pin the reviewed source bytes')


def compile_profile(recipe_path, profiles):
    recipe = decode(recipe_path.read_bytes())
    validate_recipe(recipe)
    source_path = (recipe_path.parent/recipe['source']).resolve()
    source_bytes = source_path.read_bytes()
    if digest(source_bytes) != recipe['source_sha256']:
        raise ProfileError('Reviewed source hash changed; review/recompile instead of applying stale indices')
    source = decode(source_bytes)
    count = validate_chart(source)
    validate_policy(recipe['policy'],source)
    baseline, repairs = transparent_tails(source) if recipe['policy']['transparent_tails'] else (source,[])
    # All supported equations and protected-window differences are affine in X.
    # Checking interval endpoints checks positivity and exact geometry constraints
    # throughout the interval; it is not a human readability certification.
    for x in set([1,*recipe['policy']['multiplier_range']]):
        transform(baseline,recipe['policy'],x)
    baseline_bytes = json_bytes(baseline)
    files = {'source.json':source_bytes,'baseline.json':baseline_bytes}
    media = {}
    origin_paths = [str(source_path)]
    for field,extensions in [('music',('.ogg','.mp3','.wav','.flac')),('illustration',('.png','.jpg','.jpeg'))]:
        asset = (recipe_path.parent/recipe[field]).resolve()
        if asset.suffix.lower() not in extensions:
            raise ProfileError(f'Unsupported {field} extension')
        filename = field+asset.suffix.lower()
        files[filename] = asset.read_bytes()
        media[field] = filename
        origin_paths.append(str(asset))
    manifest = {k:recipe[k] for k in ('schema_version','id','name','aliases','metadata','policy')}
    manifest.update(media=media, origin_paths=origin_paths, hashes={k:digest(v) for k,v in files.items()},
                    notes=count, lines=len(source['judgeLineList']), opacity_repairs=repairs,
                    identity='X=1 reproduces baseline.json, including separately recorded opacity-tail repairs')
    files['manifest.json'] = json_bytes(manifest)
    profiles.mkdir(parents=True,exist_ok=True)
    destination = profiles/recipe['id']
    if destination.exists():
        raise ProfileError(f'Compiled profile already exists: {destination}; use a new versioned id')
    temporary = Path(tempfile.mkdtemp(prefix='.compile-',dir=profiles))
    try:
        for name,data in files.items():
            (temporary/name).write_bytes(data)
        # Never intentionally replace an existing profile or rewrite its baseline.
        destination.mkdir()
        try:
            for path in temporary.iterdir():
                if path.name != 'manifest.json': os.replace(path,destination/path.name)
            os.replace(temporary/'manifest.json',destination/'manifest.json')
        except BaseException:
            shutil.rmtree(destination)
            raise
    finally:
        shutil.rmtree(temporary)
    return destination,manifest


def normalized_name(value):
    return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())


def catalog(profiles):
    result = []
    if not profiles.exists(): return result
    for path in sorted(profiles.glob('*/manifest.json')):
        if path.parent.name.startswith('.'): continue
        manifest = decode(path.read_bytes())
        result.append((path.parent,manifest))
    return result


def load_profile(name, profiles):
    matches = [(p,m) for p,m in catalog(profiles)
               if normalized_name(name) in {normalized_name(s) for s in [m['id'],m['name'],*m['aliases']]}]
    if len(matches) != 1:
        raise ProfileError(f'Expected one compiled profile for {name!r}, found {len(matches)}; run list')
    path,manifest = matches[0]
    if manifest['schema_version'] != 1:
        raise ProfileError('Unsupported compiled profile version')
    files = {}
    for filename,expected in manifest['hashes'].items():
        if Path(filename).name != filename or filename in ('.','..') or '\\' in filename:
            raise ProfileError('Invalid compiled asset path')
        data = (path/filename).read_bytes()
        if digest(data) != expected:
            raise ProfileError(f'Compiled asset hash changed: {filename}')
        files[filename] = data
    for filename in ('source.json','baseline.json',*manifest['media'].values()):
        if filename not in files:
            raise ProfileError('Compiled bundle is incomplete')
    baseline = decode(files['baseline.json'])
    validate_chart(baseline)
    validate_policy(manifest['policy'],baseline)
    return path,manifest,baseline,files


def make_package(chart_bytes, manifest, files, multiplier):
    meta = dict(manifest['metadata'])
    meta.update(name=f"{manifest['name']} · Scroll {multiplier*100:g}%",chart='chart.json',
                music=manifest['media']['music'],illustration=manifest['media']['illustration'])
    info = ''.join(f'{key}: {json.dumps(value,ensure_ascii=False)}\n' for key,value in meta.items())
    members = {'chart.json':chart_bytes,'info.yml':info.encode()}
    for filename in manifest['media'].values(): members[filename] = files[filename]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(members.items()):
            entry = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry,data)
    return buffer.getvalue()


def publish(path, data, force=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.scroll-',dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor,'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if force: os.replace(temporary,path)
        else: os.link(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_reviewed_rule(source_bytes, rule_bytes, multiplier):
    """Apply a pinned sidecar to an official original, with a true raw 1x bypass.

    The identity route intentionally does not parse the chart or rule, call the
    transformer, validate timelines, or repair opacity. It also works for source
    formats that non-identity transformations cannot currently support.
    """
    x = number(multiplier, 'multiplier')
    if x == 1:
        return source_bytes
    if rule_bytes is None:
        raise ProfileError('A reviewed rule is required for non-1x output')
    rule = decode(rule_bytes)
    if rule.get('schema_version') == 2:
        if digest(source_bytes) != rule.get('source_sha256'):
            raise ProfileError('Reviewed source hash changed; do not apply stale rule indices')
        return json_bytes(approach_module().apply(decode(source_bytes),rule,x,types.SimpleNamespace(**globals())))
    fields(rule, ('schema_version', 'source_sha256', 'policy'), ('metadata',), 'reviewed rule')
    if type(rule['schema_version']) is not int or rule['schema_version'] != 1:
        raise ProfileError('Unsupported reviewed rule schema_version')
    if digest(source_bytes) != rule['source_sha256']:
        raise ProfileError('Reviewed source hash changed; do not apply stale rule indices')
    base = decode(source_bytes)
    validate_chart(base)
    validate_policy(rule['policy'], base)
    if rule['policy']['transparent_tails']:
        base, _ = transparent_tails(base)
    return json_bytes(transform(base, rule['policy'], x))


def approach_module():
    global _APPROACH_MODULE
    if '_APPROACH_MODULE' not in globals():
        spec=importlib.util.spec_from_file_location('chart_speed_approach',Path(__file__).with_name('approach_speed.py'))
        _APPROACH_MODULE=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_APPROACH_MODULE)
    return _APPROACH_MODULE


def apply_file(source, rule, multiplier, output, force=False):
    """Source JSON + reviewed sidecar -> variant JSON; no media or LLM needed."""
    if output.suffix.lower() != '.json':
        raise ProfileError('apply outputs chart JSON; package unchanged media separately')
    for original in (source, rule):
        if original is not None and (output.resolve() == original.resolve() or
                (original.exists() and output.exists() and output.samefile(original))):
            raise ProfileError('Output cannot replace the original chart or rule')
    source_bytes = source.read_bytes()
    # Even a missing or malformed sidecar must not interfere with raw 1x output.
    rule_bytes = rule.read_bytes() if multiplier != 1 and rule is not None else None
    payload = apply_reviewed_rule(source_bytes, rule_bytes, multiplier)
    reused = output.exists() and output.read_bytes() == payload
    if output.exists() and not reused and not force:
        raise ProfileError(f'Output exists: {output}; use --force to replace a generated variant')
    if not reused:
        publish(output, payload, force)
    return {'output':str(output.resolve()), 'multiplier':multiplier,
            'original_byte_bypass':multiplier == 1, 'source_sha256':digest(source_bytes),
            'output_sha256':digest(payload), 'reused':reused}


def generate(name, multiplier, profiles=DEFAULT_PROFILES, output=None, force=False, dry_run=False):
    bundle,manifest,baseline,files = load_profile(name,profiles)
    chart = transform(baseline,manifest['policy'],multiplier)
    data = files['baseline.json'] if multiplier == 1 else json_bytes(chart)
    percent = format(multiplier*100,'.12g')
    output = output or DEFAULT_OUTPUTS/manifest['id']/f"{manifest['id']}-scroll-{percent}.pez"
    if output.suffix.lower() not in ('.json','.pez'):
        raise ProfileError('Output must be .json or .pez')
    # No force flag permits changing a bundle, including by symlink or hardlink.
    resolved = output.resolve()
    if profiles.resolve() == resolved or profiles.resolve() in resolved.parents:
        raise ProfileError('Output cannot be inside the compiled profile registry')
    for source in map(Path,manifest['origin_paths']):
        if resolved == source.resolve() or (source.exists() and output.exists() and output.samefile(source)):
            raise ProfileError('Output cannot replace an original chart or media asset')
    payload = data if output.suffix.lower()=='.json' else make_package(data,manifest,files,multiplier)
    reused = False
    if output.exists():
        for path in bundle.iterdir():
            if path.is_file() and output.samefile(path):
                raise ProfileError('Output aliases a compiled input')
        reused = output.read_bytes() == payload
        if not force and not reused:
            raise ProfileError(f'Output exists: {output}; use --force to replace a generated variant')
    result = {'name':manifest['name'],'multiplier':multiplier,'lines':len(chart['judgeLineList']),
              'notes':manifest['notes'],'source_sha256':manifest['hashes']['source.json'],
              'baseline_sha256':manifest['hashes']['baseline.json'],'chart_sha256':digest(data),
              'opacity_tails':len(manifest['opacity_repairs']),'output':str(output.resolve()),
              'dry_run':dry_run,'reused':reused,'note_membership_and_judgment_times_unchanged':True,
              'review':manifest['policy']['review']}
    if not dry_run:
        if not reused: publish(output,payload,force)
        result['output_sha256'] = digest(payload)
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ('apply','compile','generate','list','-h','--help'):
        argv.insert(0,'generate')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    apply_parser = sub.add_parser('apply',help='Apply a pinned sidecar to original JSON; 1x copies bytes without parsing')
    apply_parser.add_argument('source',type=Path)
    apply_parser.add_argument('--rule',type=Path)
    apply_parser.add_argument('--multiplier','--speed',type=float,required=True)
    apply_parser.add_argument('--output','-o',type=Path,required=True)
    apply_parser.add_argument('--force',action='store_true')
    compile_parser = sub.add_parser('compile',help='Compile an explicitly reviewed recipe into an immutable baseline bundle')
    compile_parser.add_argument('recipe',type=Path)
    generate_parser = sub.add_parser('generate',help='Generate from a compiled chart name/alias; no model or editor required')
    generate_parser.add_argument('chart')
    generate_parser.add_argument('--multiplier','--speed',type=float,required=True,help='Factor: 1.3 means 130%%, not 1.3 BPM')
    generate_parser.add_argument('--output','-o',type=Path)
    generate_parser.add_argument('--force',action='store_true')
    generate_parser.add_argument('--dry-run',action='store_true')
    list_parser = sub.add_parser('list',help='List compiled chart profiles')
    for p in (compile_parser,generate_parser,list_parser):
        p.add_argument('--profiles',type=Path,default=DEFAULT_PROFILES)
    args = parser.parse_args(argv)
    try:
        if args.command == 'apply':
            result = apply_file(args.source,args.rule,args.multiplier,args.output,args.force)
        elif args.command == 'compile':
            path,manifest = compile_profile(args.recipe.resolve(),args.profiles.resolve())
            result = {'profile':str(path),'name':manifest['name'],'notes':manifest['notes'],
                      'lines':manifest['lines'],'opacity_tails':len(manifest['opacity_repairs'])}
        elif args.command == 'list':
            result = [{'id':m['id'],'name':m['name'],'aliases':m['aliases'],
                       'multiplier_range':m['policy']['multiplier_range']} for _,m in catalog(args.profiles)]
        else:
            result = generate(args.chart,args.multiplier,args.profiles,args.output,args.force,args.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError,OverflowError,zipfile.BadZipFile) as error:
        print(f'error: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
