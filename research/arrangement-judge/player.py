"""Simulated player: the cheapest finger assignment for a pure-configuration chart, per play style.

No learning. A beam search over finger states finds, for each play-style profile, the
assignment of notes to fingers with the lowest total cost. Costs are hand-set physical
penalties; they are a difficulty measure, and the resulting hand sequence is the input to
the feel statistics (feel.py).

Game rules used (from the project owner):
- Every note's judgment region is about 0.15 screen widths wide (+-0.075 around the note),
  measured from an in-game screenshot.
- Tap, hold head and flick need their own finger. A hold keeps that finger until it ends.
- Drags need a touching finger in range; one finger covers every drag within 0.15.
- Crossing hands is free up to 0.1 screen widths; beyond that it is penalized.
- Ring fingers carry a major penalty. Thumbs are not modeled.

Notes are [time_s, type, x, hold_s] tokens (type 1 Tap, 2 Drag, 3 Hold, 4 Flick).
"""
import itertools

J = 0.075
CROSS_FREE = 0.1
PROFILES = {
    "two": ("L0", "R0"),                          # two index fingers
    "four": ("L0", "L1", "R0", "R1"),             # index + middle per hand
    "free": ("L0", "L1", "L2", "R0", "R1", "R2"),  # adds ring fingers, penalized
}
HOME = {"L0": .35, "L1": .25, "L2": .15, "R0": .65, "R1": .75, "R2": .85}
SPAN = {(0, 1): .2, (1, 2): .15, (0, 2): .3}  # max distance between fingers of one hand, by rank
W = dict(move=1.0, drag_move=.5, speed=2.5, repress=1.0, tau=.09, flick_repress=.5, cross=2.0, ring=3.0,
         order=4.0, span=4.0, miss_press=20.0, miss_drag=5.0, side=.05)
SIDE_HOME = {"L": .3, "R": .7}  # tiny preference for the near hand, so equal-cost choices are not arbitrary
BEAM = 32
EPS = 1e-3


def groups_of(tokens):
    groups = []
    for t in tokens:
        if not groups or t[0] - groups[-1][0][0] > EPS:
            groups.append([])
        groups[-1].append(t)
    return groups


def targets_of(group):
    """Press targets (tap/hold/flick) and drag clusters, as (kind, lo, hi, hold_s, note indices)."""
    press, drags = [], []
    for i, (_, ty, x, d) in enumerate(group):
        if ty == 2:
            drags.append((x, i))
        else:
            press.append(["flick" if ty == 4 else "press", x - J, x + J, d if ty == 3 else 0.0, [i]])
    drags.sort()
    clusters = []
    for x, i in drags:
        if clusters and x - clusters[-1][2] <= 2 * J:
            clusters[-1][2] = x; clusters[-1][3].append(i)
        else:
            clusters.append([x, x, x, [i]])
    out = list(press)
    for first, _, last, idx in clusters:
        lo, hi = last - J, first + J
        for p in out:  # a drag inside a pressing finger's region is covered by that finger
            if p[0] != "drag" and max(lo, p[1]) <= min(hi, p[2]):
                p[1], p[2] = max(lo, p[1]), min(hi, p[2]); p[4] = p[4] + idx
                break
        else:
            out.append(["drag", lo, hi, 0.0, idx])
    return out


class State:
    __slots__ = ("f", "hand", "last", "cost", "hist")

    def __init__(self, f, hand, last, cost, hist):
        self.f, self.hand, self.last, self.cost, self.hist = f, hand, last, cost, hist


def play(tokens, profile="two"):
    """Return (total cost, per-group records) for the cheapest assignment found."""
    names = PROFILES[profile]
    hand_of = [n[0] for n in names]; rank_of = [int(n[1]) for n in names]
    # finger: (x, t_last_used, t_last_press, busy_until)
    start = State(tuple((HOME[n], -10.0, -10.0, -10.0) for n in names), {"L": HOME["L0"], "R": HOME["R0"]},
                  {"L": None, "R": None}, 0.0, None)
    beam = [start]
    groups = groups_of(tokens)
    for gi, group in enumerate(groups):
        t = group[0][0]
        tg = targets_of(group)
        nxt = {}
        for s in beam:
            busy = [k for k, f in enumerate(s.f) if f[3] > t + EPS]
            free = [k for k in range(len(names)) if k not in busy]
            todo, covered = [], []
            for target in tg:  # drags already under a holding finger cost nothing
                holder = next((k for k in busy if target[0] == "drag" and target[1] <= s.f[k][0] <= target[2]), None)
                if holder is not None:
                    covered.append((tuple(target[4]), "drag", names[holder]))
                    continue
                todo.append(target)
            k = len(todo)
            pool = free + [None] * max(0, k - len(free))
            for perm in set(itertools.permutations(pool, k)):
                parts = dict(move=0.0, repress=0.0, cross=0.0, ring=0.0, shape=0.0, miss=0.0)
                f = list(s.f); used = []
                for target, fi in zip(todo, perm):
                    kind, lo, hi, hold, _ = target
                    if fi is None:
                        parts["miss"] += W["miss_drag"] if kind == "drag" else W["miss_press"]
                        continue
                    x0, tl, tp, _ = f[fi]
                    nx = min(max(x0, lo), hi)
                    v = abs(nx - x0) / max(t - tl, .02)
                    parts["move"] += (W["drag_move"] if kind == "drag" else W["move"]) * (v / W["speed"]) ** 2
                    if kind != "drag":
                        w = W["flick_repress"] if kind == "flick" else W["repress"]
                        parts["repress"] += w * (W["tau"] / max(t - tp, .02)) ** 2
                        parts["move"] += W["side"] * abs(nx - SIDE_HOME[hand_of[fi]])
                        tp = t
                    if rank_of[fi] == 2:
                        parts["ring"] += W["ring"]
                    f[fi] = (nx, t, tp, t + hold if hold > 0 else -10.0)
                    used.append(fi)
                # hand shape among fingers anchored now (pressing now or holding)
                anchored = set(used) | set(busy)
                for h in "LR":
                    hs = [i for i in anchored if hand_of[i] == h]
                    for a, b in itertools.combinations(hs, 2):
                        ra, rb = rank_of[a], rank_of[b]
                        if ra == rb:
                            continue
                        lo_r, hi_r = (a, b) if ra < rb else (b, a)
                        gap = f[hi_r][0] - f[lo_r][0]  # higher rank sits outward: left for L, right for R
                        wrong = gap if h == "L" else -gap
                        if wrong > .02:
                            parts["shape"] += W["order"] * (1 + wrong / .05)
                        span = SPAN[(min(ra, rb), max(ra, rb))]
                        if abs(gap) > span:
                            parts["shape"] += W["span"] * (1 + (abs(gap) - span) / .05)
                hand = dict(s.hand); last = dict(s.last)
                for h in "LR":
                    hs = [i for i in used if hand_of[i] == h]
                    if hs:
                        hand[h] = sum(f[i][0] for i in hs) / len(hs)
                        last[h] = names[hs[-1]]
                xl = max([hand["L"]] + [f[i][0] for i in anchored if hand_of[i] == "L"])
                xr = min([hand["R"]] + [f[i][0] for i in anchored if hand_of[i] == "R"])
                if xl - xr > CROSS_FREE:
                    parts["cross"] += W["cross"] * (1 + (xl - xr - CROSS_FREE) / .1)
                total = sum(parts.values())
                assign = tuple((tuple(target[4]), target[0], None if fi is None else names[fi])
                               for target, fi in zip(todo, perm)) + tuple(covered)
                key = (tuple((round(x / .02), b > t + EPS) for x, _, _, b in f), last["L"], last["R"])
                cost = s.cost + total
                if key not in nxt or cost < nxt[key].cost:
                    nxt[key] = State(tuple(f), hand, last, cost, (s.hist, gi, assign, parts))
        beam = sorted(nxt.values(), key=lambda s: s.cost)[:BEAM]
    best = beam[0]
    records, h = [], best.hist
    while h is not None:
        h, gi, assign, parts = h
        records.append(dict(time=groups[gi][0][0], notes=len(groups[gi]), assign=assign, cost=parts))
    records.reverse()
    return best.cost, records
