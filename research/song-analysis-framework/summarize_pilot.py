#!/usr/bin/env python3
"""Reconcile pilot answers into absolute time and compare against a reviewed map.

Read-only. Prints a Markdown digest; writes reconciled.json next to calls.jsonl.
"""
import argparse
import json
import re
from pathlib import Path

GRID = {'bpm': 204.0, 'offset_seconds': 0.348}
# Reviewed working map, 02-SONG-STRUCTURE.md (editor beats, [start,end)).
REVIEWED = [(0, 'lead-in'), (8, 'hook'), (40, 'verse 1'), (104, 'pre-chorus'), (132, 'pickup?'), (136, 'chorus 1'),
            (200, 'hook'), (232, 'verse 2a'), (264, 'verse 2b'), (296, 'turnaround'), (300, 'pickup?'),
            (304, 'chorus 2'), (368, 'climax 3'), (432, 'hook'), (464, 'tail')]
# Current analyzer's automatic texture boundaries (research/note-analysis/override/analysis.json).
ALGO_BOUNDARIES = [0.0, 12.5, 21.5, 38.0, 45.25, 52.75, 59.0, 72.0, 79.0]  # first nine; the rest are loaded if present


def beat_to_s(b):
    return GRID['offset_seconds'] + b * 60 / GRID['bpm']


def s_to_beat(s):
    return (s - GRID['offset_seconds']) * GRID['bpm'] / 60


TIME = re.compile(r'^\s*\[?\s*(?:(\d{1,2}):)?(\d{1,3}(?:\.\d+)?)\s*s?\s*(?:-\s*(?:(\d{1,2}):)?(\d{1,3}(?:\.\d+)?)\s*s?)?\s*\]?\s*[:\-–]?\s*(.*)$')


def parse_lines(text):
    out = []
    for line in text.splitlines():
        m = TIME.match(line)
        if not m or not line.strip():
            continue
        mm, ss, mm2, ss2, rest = m.groups()
        start = (int(mm) * 60 if mm else 0) + float(ss)
        end = ((int(mm2) * 60 if mm2 else 0) + float(ss2)) if ss2 else None
        out.append((start, end, rest.strip()))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pilot_dir', type=Path)
    parser.add_argument('--algo', type=Path, default=None, help='analysis.json of the current analyzer')
    parser.add_argument('--stems', type=Path, default=None, help='override-stem-energy.json (2 s bins, dBFS)')
    parser.add_argument('--config', type=Path, default=None, help='song config JSON; sets the grid and disables the Override reviewed map')
    args = parser.parse_args()
    global REVIEWED, ALGO_BOUNDARIES
    if args.config:
        cfg = json.loads(args.config.read_text())
        GRID['bpm'], GRID['offset_seconds'] = float(cfg['bpm']), float(cfg['offset_seconds'])
        REVIEWED = [(v[0], k) for k, v in cfg['sections'].items()]
        ALGO_BOUNDARIES = []
    stems = json.loads(args.stems.read_text()) if args.stems and args.stems.exists() else None

    def vocal_active(t):
        if not stems:
            return None
        i = min(int(t // 2), len(stems['vocals']) - 1)
        return stems['vocals'][i] > -40
    calls = [json.loads(l) for l in (args.pilot_dir / 'calls.jsonl').read_text().splitlines() if l.strip()]
    by_id = {c['id']: c for c in calls}
    algo = ALGO_BOUNDARIES
    if args.algo and args.algo.exists():
        algo = [s['start_seconds'] for s in json.loads(args.algo.read_text())['sections']]

    print('# Pilot digest\n')
    errors = [c for c in calls if 'error' in c]
    print(f'{len(calls)} calls, {len(errors)} errors, total model time '
          f'{sum(c["elapsed_seconds"] for c in calls):.0f}s, peak memory '
          f'{max(c.get("mlx_peak_memory_bytes", 0) for c in calls) / 1e9:.1f} GB\n')
    for c in errors:
        print('- ERROR', c['id'], c['error'])

    # ---- A1 / D: structure claims in absolute time
    boundaries = []  # (abs_seconds, label, call_id)
    print('\n## Structure claims (A1, D) in absolute seconds / beats\n')
    for cid in ('A1_W1', 'D1_A1_W1s', 'A1_W2', 'D2_A1_W2s', 'A1_W3', 'A1_W4'):
        c = by_id.get(cid)
        if not c or 'answer' not in c:
            continue
        off = c['absolute_offset_seconds'][0]
        print(f'### {cid} (clip {off}–{list(c["clips"].values())[0]["to_seconds"]} s)')
        for start, end, rest in parse_lines(c['answer']):
            a = off + start
            print(f'- {a:7.2f} s / beat {s_to_beat(a):6.1f}: {rest[:150]}')
            boundaries.append((a, rest, cid))
        print()

    # ---- stability: clusters within ±2 s claimed by two different calls
    print('## Boundary clusters (±2 s) and stability\n')
    boundaries.sort()
    clusters = []
    for b in boundaries:
        if clusters and b[0] - clusters[-1][-1][0] <= 2.0:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    print('| abs s | beat | claims | calls | stable | nearest reviewed boundary | nearest analyzer boundary |')
    print('|---:|---:|---:|---|---|---|---|')
    for cl in clusters:
        mid = sum(x[0] for x in cl) / len(cl)
        ids = sorted({x[2] for x in cl})
        rev = min(REVIEWED, key=lambda r: abs(beat_to_s(r[0]) - mid))
        alg = min(algo, key=lambda s: abs(s - mid)) if algo else None
        algtxt = f'{alg:.1f} s ({alg - mid:+.1f} s)' if alg is not None else 'n/a'
        print(f'| {mid:.1f} | {s_to_beat(mid):.1f} | {len(cl)} | {",".join(ids)} | {"yes" if len(ids) > 1 else "no"} | '
              f'{rev[1]} @ beat {rev[0]} ({beat_to_s(rev[0]) - mid:+.1f} s) | {algtxt} |')

    # ---- reviewed map coverage
    print('\n## Reviewed-map boundaries: does any model claim fall within ±2 s?\n')
    print('| beat | s | reviewed label | model claims within ±2 s |')
    print('|---:|---:|---|---|')
    for b, label in REVIEWED:
        s = beat_to_s(b)
        hits = [f'{x[2]}: {x[1][:60]}' for x in boundaries if abs(x[0] - s) <= 2.0]
        print(f'| {b} | {s:.1f} | {label} | {"<br>".join(hits) if hits else "none"} |')

    # ---- A2 entrances
    print('\n## Entrances and exits (A2), absolute seconds\n')
    for w in ('W1', 'W2', 'W3', 'W4'):
        c = by_id.get(f'A2_{w}')
        if not c or 'answer' not in c:
            continue
        off = c['absolute_offset_seconds'][0]
        items = parse_lines(c['answer'])
        print(f'- {w} (+{off} s): ' + '; '.join(f'{off + s:.1f}s {r[:40]}' for s, _, r in items[:40]))

    # ---- A3 energy
    print('\n## Energy ratings (A3) per window, absolute seconds\n')
    energy = []
    for w in ('W1', 'W2', 'W3', 'W4'):
        c = by_id.get(f'A3_{w}')
        if not c or 'answer' not in c:
            continue
        off = c['absolute_offset_seconds'][0]
        for s, e, r in parse_lines(c['answer']):
            m = re.match(r'(\d)', r)
            if m:
                energy.append((off + s, int(m.group(1)), w, r[:60]))
    energy.sort()
    print('| abs s | beat | rating | window | note |')
    print('|---:|---:|---:|---|---|')
    for a, r, w, note in energy:
        print(f'| {a:.1f} | {s_to_beat(a):.0f} | {r} | {w} | {note} |')

    # ---- B per section
    print('\n## Section clips (B1 lead, B2 drums, B3 function)\n')
    for s in ('open', 'verse1', 'pre', 'chorus1', 'hook2', 'verse2a', 'verse2b', 'chorus2', 'climax3', 'hook3'):
        print(f'### {s}')
        for q in ('B1', 'B2', 'B3'):
            c = by_id.get(f'{q}_{s}')
            if c and 'answer' in c:
                print(f'- **{q}**: {c["answer"].strip()[:700]}')
        print()

    # ---- C pairs, A4 lyrics, E
    print('## Pair comparisons (C)\n')
    for cid in ('C1', 'C2', 'C3', 'C4', 'C5', 'C6_control'):
        c = by_id.get(cid)
        if c and 'answer' in c:
            print(f'- **{cid}** {list(c["clips"].keys())}: {c["answer"].strip()[:400]}')
    print('\n## Lyrics (A4): lines per window, and whether the Demucs vocal stem is active at each line\n')
    for w in ('W1', 'W2', 'W3', 'W4'):
        c = by_id.get(f'A4_{w}')
        if c and 'answer' in c:
            off = c['absolute_offset_seconds'][0]
            lines = [l for l in c['answer'].splitlines() if l.strip()]
            parsed = parse_lines(c['answer'])
            on = sum(1 for s_, _, _ in parsed if vocal_active(off + s_))
            print(f'- {w} (+{off} s): {len(lines)} lines, {len(parsed)} timestamped, {on} on active vocal stem, '
                  f'truncated={c["output_may_be_truncated"]}')
            for s_, e_, r in parsed[:14]:
                print(f'    - {off + s_:6.1f}s {"V" if vocal_active(off + s_) else "-"} {r[:60]}')
    if stems:
        print('\n## Measured vocal presence (Demucs vocal stem > -40 dBFS, 2 s bins)\n')
        runs, cur = [], None
        for i, v in enumerate(stems['vocals']):
            act = v > -40
            if cur is None or cur[1] != act:
                if cur: runs.append(cur)
                cur = [i * 2, act, i * 2 + 2]
            else:
                cur[2] = i * 2 + 2
        runs.append(cur)
        print(', '.join(f'{a}–{b}s {"vocal" if act else "no vocal"} (beats {s_to_beat(a):.0f}–{s_to_beat(b):.0f})' for a, act, b in runs))
    c = by_id.get('E1_grid')
    if c and 'answer' in c:
        print(f'\n## Grid check (E)\n\n{c["answer"].strip()[:300]}')

    # ---- protocol v3: generic digest by call-id prefix (sections, pairs in both orders, intensity, grid)
    if any(c['id'].endswith(('_AB', '_BA')) for c in calls):
        print('\n## v3 section clips (VP vocal gate, B3 function, B1 lead, A4 lyrics)\n')
        names = []
        for c in calls:
            if c['id'].startswith('B3_') and c['id'][3:] not in names:
                names.append(c['id'][3:])
        for n in names:
            print(f'### {n}')
            for q in ('VP', 'B3', 'B1', 'A4'):
                c = by_id.get(f'{q}_{n}')
                if c and 'answer' in c:
                    clip = list(c['clips'].values())[0]
                    print(f'- **{q}** ({clip["from_seconds"]}–{clip["to_seconds"]} s): {c["answer"].strip()[:400]}')
            print()
        print('## v3 pairs, both orders\n')
        print('| pair | AB | BA | consistent |')
        print('|---|---|---|---|')
        head = lambda t: t.split('.')[0].split(',')[0].strip().upper()
        for pid in sorted({c['id'][:-3] for c in calls if c['id'].endswith(('_AB', '_BA'))}):
            ab, ba = by_id.get(f'{pid}_AB', {}), by_id.get(f'{pid}_BA', {})
            fa = ab.get('answer', '').strip().split('\n')[0][:40]
            fb = ba.get('answer', '').strip().split('\n')[0][:40]
            if pid.startswith('PI'):
                ok = {head(fa), head(fb)} == {'A', 'B'} or head(fa) == head(fb) == 'EQUAL'
            else:
                ok = bool(fa and fb) and head(fa) == head(fb)
            print(f'| {pid} | {fa} | {fb} | {"yes" if ok else "no"} |')
        c = by_id.get('E1_grid')
        if c and 'answer' in c:
            print(f'\n## Grid check (E)\n\n{c["answer"].strip()[:300]}')

    (args.pilot_dir / 'reconciled.json').write_text(json.dumps({
        'boundary_claims': [{'abs_seconds': round(a, 2), 'beat': round(s_to_beat(a), 2), 'text': t, 'call': cid}
                            for a, t, cid in boundaries],
        'energy': [{'abs_seconds': round(a, 2), 'beat': round(s_to_beat(a), 1), 'rating': r, 'window': w, 'note': n}
                   for a, r, w, n in energy],
        'grid': GRID}, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
