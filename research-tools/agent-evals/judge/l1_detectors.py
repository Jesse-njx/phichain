"""L1: measured chart properties, comparable across native and official charts.

Motion windows use the definitions of research/judgment-line-study/cadence.py so
results line up with the existing study: half-second windows, 0.05 s sampling,
per-line variation aggregated across lines with max, never sum.

Everything here is a measurement. Nothing here is a quality score. Which metrics
may stop a candidate is decided from backtest evidence, in gates.json.
"""
from collections import Counter
import json
import math
from statistics import median, pstdev
import sys

from chartmodel import CANVAS_H, CANVAS_W, load

STEP = 0.05
WINDOW = 0.5
SAMPLES = 10
LOW = (0.015, 2.0, 0.05)  # travel (screen), turn (degrees), alpha
HIGH = (0.12, 18.0, 0.30)
ASPECT = 16 / 9
CHORD_S = 0.005
FAST_STEP_S = 0.300  # Same limit as the run02 comparison.
SEGMENT_S = 4.0
BEAM = 48


def line_visible(x, y, r):
    a = math.radians(r)
    distance = abs((x - 0.5) * ASPECT * math.sin(a) - (y - 0.5) * math.cos(a))
    reach = 0.5 * ASPECT * abs(math.sin(a)) + 0.5 * abs(math.cos(a))
    return distance <= reach + 0.005


def pct(flags):
    return round(100 * sum(flags) / len(flags), 2) if flags else None


def quantile(values, q):
    if not values:
        return None
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def rnd(value, digits=3):
    return None if value is None else round(value, digits)


def line_windows(line, first, bins):
    """Return per-window (travel, turn, alpha) variation and presence for one line."""
    activity = [[0.0, 0.0, 0.0] for _ in range(bins)]
    present = [False] * bins
    prev = None
    for k in range(bins * SAMPLES + 1):
        t = first + k * STEP
        x, y, r, alpha = line.pose(t)
        on = line_visible(x, y, r)
        vis = alpha > 0.05 and on
        if prev is not None:
            px, py, pr, pa, pon, pvis = prev
            b = (k - 1) // SAMPLES
            dr = (r - pr + 90) % 180 - 90
            if pvis and vis:
                angle = math.radians(pr + dr / 2)
                normal = -(x - px) * ASPECT * math.sin(angle) + (y - py) * math.cos(angle)
                activity[b][0] += abs(normal)
                activity[b][1] += abs(dr)
            if pon and on and (pvis or vis):
                activity[b][2] += abs(alpha - pa)
            if pvis or vis:
                present[b] = True
        prev = (x, y, r, alpha, on, vis)
    return activity, present


def exceeds(row, limit):
    return any(row[i] >= limit[i] for i in range(3))


def longest_run(flags):
    best = now = 0
    for f in flags:
        now = now + 1 if f else 0
        best = max(best, now)
    return best


def motion_metrics(chart, first, last):
    bins = int(math.floor((last - first) / WINDOW))
    if bins < 1:
        return {}, {}
    carriers = {n.line for n in chart.notes if first <= n.t <= last}
    carrier_any = [[0.0] * 3 for _ in range(bins)]
    bg_any = [[0.0] * 3 for _ in range(bins)]
    carrier_present = [False] * bins
    bg_present = [False] * bins
    moving_lines = [0] * bins
    moving_bg_lines = [0] * bins
    judging = [False] * bins
    for n in chart.notes:
        if n.end < first or n.t > last:
            continue
        for b in range(max(0, int((n.t - first) // WINDOW)), min(bins - 1, int((n.end - first) // WINDOW)) + 1):
            judging[b] = True

    for line in chart.lines:
        is_carrier = line.index in carriers
        activity, present = line_windows(line, first, bins)
        target = carrier_any if is_carrier else bg_any
        for b in range(bins):
            for i in range(3):
                target[b][i] = max(target[b][i], activity[b][i])
            if is_carrier:
                carrier_present[b] |= present[b]
            else:
                bg_present[b] |= present[b]
            if exceeds(activity[b], LOW):
                moving_lines[b] += 1
                if not is_carrier:
                    moving_bg_lines[b] += 1

    carrier_motion = [exceeds(r, LOW) for r in carrier_any]
    bg_motion = [exceeds(r, LOW) for r in bg_any]
    motion = [a or b for a, b in zip(carrier_motion, bg_motion)]
    strong = [exceeds(a, HIGH) or exceeds(b, HIGH) for a, b in zip(carrier_any, bg_any)]
    active_still = [j and not c for j, c in zip(judging, carrier_motion)]
    active_all_still = [j and not m for j, m in zip(judging, motion)]

    onsets = [i for i in range(bins) if carrier_motion[i] and (i == 0 or not carrier_motion[i - 1])]
    gaps = [(b - a) * WINDOW for a, b in zip(onsets, onsets[1:])]
    busy = [c for c, m in zip(moving_bg_lines, bg_motion) if m]

    metrics = {
        "carrier_motion_pct": pct(carrier_motion),
        "background_motion_pct": pct(bg_motion),
        "any_motion_pct": pct(motion),
        "strong_motion_pct": pct(strong),
        "background_present_pct": pct(bg_present),
        "judging_carrier_motion_pct": pct([c for c, j in zip(carrier_motion, judging) if j]),
        "longest_carrier_still_during_play_s": longest_run(active_still) * WINDOW,
        "longest_all_still_during_play_s": longest_run(active_all_still) * WINDOW,
        "carrier_response_gap_p90_s": rnd(quantile(gaps, 0.9)),
        "bg_lines_moving_together_median": rnd(median(busy)) if busy else 0.0,
        "bg_two_plus_lines_moving_pct": pct([c >= 2 for c in moving_bg_lines]),
        "bg_three_plus_lines_moving_pct": pct([c >= 3 for c in moving_bg_lines]),
    }
    series = {"motion": motion, "strong": strong, "moving_lines": moving_lines}
    return metrics, series


def fresh_groups(chart, first, last):
    """Fresh finger obligations grouped into near-simultaneous onsets, in native px."""
    by_line = {l.index: l for l in chart.lines}
    heads = []
    for n in chart.notes:
        if n.kind == "drag" or not first <= n.t <= last:
            continue
        hx, hy = by_line[n.line].head(n)
        heads.append((n.t, (hx - 0.5) * CANVAS_W, (hy - 0.5) * CANVAS_H))
    groups = []
    for h in heads:
        if groups and h[0] - groups[-1][0][0] <= CHORD_S:
            groups[-1].append(h)
        else:
            groups.append([h])
    return groups


def two_finger_route(groups):
    """Minimum total travel for two fingers: a lower bound on required hand movement.

    Chords wider than two use their outermost members. Returns one record per finger
    move: (time, seconds since that finger's last hit, signed dx, distance px).
    """
    if not groups:
        return []
    # A state is (finger A position, finger B position, last-hit times), with its cost and history link.
    states = [(0.0, None, None, -1e9, -1e9, None)]
    for group in groups:
        t = group[0][0]
        pts = sorted(((g[1], g[2]) for g in group), key=lambda p: p[0])
        if len(pts) > 2:
            pts = [pts[0], pts[-1]]
        expanded = {}
        for state in states:
            cost, a, b, ta, tb, _ = state
            if len(pts) == 1:
                options = [(pts[0], b, t, tb, [(a, ta, pts[0])]), (a, pts[0], ta, t, [(b, tb, pts[0])])]
            else:
                options = [
                    (pts[0], pts[1], t, t, [(a, ta, pts[0]), (b, tb, pts[1])]),
                    (pts[1], pts[0], t, t, [(a, ta, pts[1]), (b, tb, pts[0])]),
                ]
            for na, nb, nta, ntb, moved in options:
                delta = sum(math.dist(p, q) for p, _, q in moved if p is not None)
                key = (na, nb)
                total = cost + delta
                if key not in expanded or total < expanded[key][0]:
                    records = [
                        (t, t - w, q[0] - p[0], math.dist(p, q))
                        for p, w, q in moved
                        if p is not None
                    ]
                    expanded[key] = (total, na, nb, nta, ntb, (state, records))
        states = sorted(expanded.values(), key=lambda s: s[0])[:BEAM]
    route = []
    node = states[0]
    while node[5] is not None:
        parent, records = node[5]
        route.extend(records)
        node = parent
    route.reverse()
    return route


def hand_metrics(chart, first, last):
    groups = fresh_groups(chart, first, last)
    span = max(last - first, 1e-6)
    onsets = len(groups)
    if onsets < 2:
        return {"fresh_onsets_per_s": rnd(onsets / span)}, []

    centres = [(sum(h[1] for h in g) / len(g), g[0][0]) for g in groups]
    steps = [abs(b[0] - a[0]) for a, b in zip(centres, centres[1:]) if b[1] - a[1] <= FAST_STEP_S]

    route = two_finger_route(groups)
    fast = [r for r in route if r[1] <= FAST_STEP_S * 2]
    moves = [r[3] for r in fast]
    per_second = sum(r[3] for r in route) / span

    # Direction changes along each finger cannot be recovered from a flat move list,
    # so measure them on the onset centre path, which needs no hand assignment.
    signs = [
        b[0] - a[0]
        for a, b in zip(centres, centres[1:])
        if b[1] - a[1] <= FAST_STEP_S and abs(b[0] - a[0]) >= 50
    ]
    turns = [1 if x * y < 0 else 0 for x, y in zip(signs, signs[1:])]

    xs = [h[1] for g in groups for h in g]
    metrics = {
        "fresh_onsets_per_s": rnd(onsets / span),
        "onset_step_median_px": rnd(median(steps)) if steps else None,
        "onset_step_under50_pct": pct([s < 50 for s in steps]),
        "onset_step_200plus_pct": pct([s >= 200 for s in steps]),
        "required_travel_px_per_s": rnd(per_second, 1),
        "required_move_median_px": rnd(median(moves), 1) if moves else None,
        "required_move_under50_pct": pct([m < 50 for m in moves]),
        "required_move_200plus_pct": pct([m >= 200 for m in moves]),
        "direction_change_pct": pct(turns),
        "x_spread_iqr_px": rnd(quantile(xs, 0.75) - quantile(xs, 0.25), 1),
    }
    return metrics, route


def section_metrics(chart, first, last, route, motion_series):
    """Do successive stretches differ in what the player and the eye receive?"""
    span = last - first
    count = int(span // SEGMENT_S)
    if count < 2:
        return {}
    groups = fresh_groups(chart, first, last)
    rows = []
    for i in range(count):
        a = first + i * SEGMENT_S
        b = a + SEGMENT_S
        onsets = sum(a <= g[0][0] < b for g in groups)
        travel = sum(r[3] for r in route if a <= r[0] < b) / SEGMENT_S
        xs = [h[1] for g in groups for h in g if a <= h[0] < b]
        spread = quantile(xs, 0.75) - quantile(xs, 0.25) if xs else 0.0
        lo, hi = int(i * SEGMENT_S / WINDOW), int((i + 1) * SEGMENT_S / WINDOW)
        moving = motion_series.get("moving_lines", [])[lo:hi]
        line_activity = sum(moving) / len(moving) if moving else 0.0
        rows.append((onsets / SEGMENT_S, travel, spread, line_activity))

    def cv(values):
        mean = sum(values) / len(values)
        return pstdev(values) / mean if mean > 1e-9 else 0.0

    return {
        "section_density_cv": rnd(cv([r[0] for r in rows])),
        "section_travel_cv": rnd(cv([r[1] for r in rows])),
        "section_spread_cv": rnd(cv([r[2] for r in rows])),
        "section_line_activity_cv": rnd(cv([r[3] for r in rows])),
    }


def approach_metrics(chart, inside):
    """Note approach speed at the judgment moment, in screen heights per second."""
    by_line = {l.index: l for l in chart.lines}
    # One official speed unit moves a note 0.6 screen heights per second (cadence.py).
    # Hold heads keep their own serialized speed factor out of this measure.
    rates = [
        abs(by_line[n.line].v.at(n.t)) * 0.6 * (1.0 if n.kind == "hold" else abs(n.speed))
        for n in inside
    ]
    return {"approach_heights_per_s_median": rnd(median(rates))} if rates else {}


def analyze(path_or_chart, start=None, end=None):
    """Measure a chart, or the stretch between start and end seconds."""
    chart = load(path_or_chart) if isinstance(path_or_chart, str) else path_or_chart
    notes = chart.notes
    if start is not None or end is not None:
        lo = start if start is not None else notes[0].t
        hi = end if end is not None else max(n.end for n in notes)
        inside = [n for n in notes if lo <= n.t <= hi]
    else:
        inside = notes
    if not inside:
        return {"notes": 0, "span_s": 0, "metrics": {}, "kinds": {}}
    first = min(n.t for n in inside)
    last = max(n.end for n in inside)
    motion, series = motion_metrics(chart, first, last)
    hands, route = hand_metrics(chart, first, last)
    sections = section_metrics(chart, first, last, route, series)
    return {
        "notes": len(inside),
        "span_s": round(last - first, 3),
        "lines": len(chart.lines),
        "kinds": dict(Counter(n.kind for n in inside)),
        "metrics": {**hands, **approach_metrics(chart, inside), **motion, **sections},
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    s = float(args[1]) if len(args) > 1 else None
    e = float(args[2]) if len(args) > 2 else None
    print(json.dumps(analyze(args[0], s, e), indent=2, ensure_ascii=False))
