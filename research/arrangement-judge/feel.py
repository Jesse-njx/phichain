"""Feel (手感) v1: how common a passage's hand pattern is in official charts, given its rhythm.

1. player.py finds the cheapest fingering per play style ("two": index fingers, "four":
   index + middle per hand). The chart's arrangement decides which hand/finger plays each
   note group; the rhythm does not depend on the arrangement.
2. Each note group becomes a token: the hands used and fingers per hand ("L", "L+R", "L2"). Four
   consecutive groups form a pattern, mirrored to a canonical form.
3. Counting only (no model): P(pattern | rhythm) from official train-split charts, where
   rhythm = the four groups' kinds (number of press notes, or drag-only) and the three gaps
   between them in speed buckets. Backoff to coarser rhythm when a rhythm is rare.
4. Feel of a window = mean surprisal of its patterns; p_feel compares it with official
   validation windows. A player picks the style that suits the passage best, so the window's
   p_feel is the best (largest) over play styles.

python3 feel.py fingering   # simulate every official chart (runs/feel/fingering)
python3 feel.py check       # counts, reference, checks -> runs/feel/result.json
"""
import collections
import gzip
import json
import math
import multiprocessing
import pathlib
import sys

import numpy as np

from player import play

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "runs/feel"
STYLES = ("two", "four")
GAP_EDGES = (.07, .1, .14, .2, .3)  # seconds between consecutive note groups
GAP_LABELS = ("<0.07s", "0.07-0.1s", "0.1-0.14s", "0.14-0.2s", "0.2-0.3s", ">0.3s")
N = 4
ALPHA = 30.0  # chosen on held-out calibration: official notes over the validation 95th percentile 3.5%, random-x notes 15.5%
FLAGS = True
SHAPE_RATIO = 1.4


def gap_bucket(dt):
    return int(np.searchsorted(GAP_EDGES, dt))


def kind(group_notes):
    presses = sum(1 for ty in group_notes if ty != 2)
    return "d" if presses == 0 else str(min(presses, 3))


def hand_token(fingers):
    """Hands used and how many fingers each: "L", "R", "L+R", "L2+R"; "X" marks a note no finger could take.
    Which finger of a hand (index or middle) is a cost tie, so it is not part of the token."""
    used = collections.defaultdict(set); miss = False
    for f in fingers:
        if f is None:
            miss = True
        else:
            used[f[0]].add(f)
    parts = [h + (str(len(used[h])) if len(used[h]) > 1 else "") for h in "LR" if used[h]]
    return "+".join(parts + (["X"] if miss else [])) or "X"


def mirror_token(tok):
    return "+".join(sorted(tok.translate(str.maketrans("LR", "RL")).split("+"), key=lambda p: (p[0] not in "L", p)))


def sequence(tokens, records):
    """Per note group with a press (tap, hold head or flick): (time, kind, hand token, group index).

    Drag-only groups are left out: one finger slides through them and which hand does it
    is a cost tie, not a choice the arrangement forces. Drags inside a press group do not
    change its token. Kind gets an "h" when an earlier hold is still held (the other hand
    plays alone) and a "d" when drags occur in this group or since the previous press group
    (a hand may be busy sliding). Both are rhythm facts, not placement."""
    seq, groups = [], []
    for t in tokens:  # same grouping as player.groups_of
        if not groups or t[0] - groups[-1][0][0] > 1e-3:
            groups.append([])
        groups[-1].append(t)
    hold_ends, drags_since = [], False
    for gi, (g, r) in enumerate(zip(groups, records)):
        t = g[0][0]
        held = any(end > t + 1e-3 for end in hold_ends)
        hold_ends += [n[0] + n[3] for n in g if n[1] == 3]
        drags_since = drags_since or any(n[1] == 2 for n in g)
        fingers = [f for _, k, f in r["assign"] if k != "drag"]
        if not fingers:
            continue
        flags = ("h" if held and FLAGS else "") + ("d" if drags_since and FLAGS else "")
        seq.append((t, kind([n[1] for n in g]) + flags, hand_token(fingers), gi))
        drags_since = False
    return seq


def patterns(seq):
    """(end index, rhythm key, canonical pattern) for every N consecutive groups."""
    out = []
    for i in range(N - 1, len(seq)):
        win = seq[i - N + 1:i + 1]
        kinds = tuple(w[1] for w in win)
        raw = [win[j + 1][0] - win[j][0] for j in range(N - 1)]
        gaps = tuple(gap_bucket(g) for g in raw)
        pat = tuple(w[2] for w in win)
        mir = tuple(mirror_token(p) for p in pat)
        out.append((i, kinds, gaps, min(pat, mir), rhythm_shape(raw)))
    return out


def rhythm_shape(raw):
    """Which gaps are as short as the fastest one ("s", within SHAPE_RATIO) and which are longer ("l").
    Uneven rhythm resets hand alternation, so the backoff keeps this shape."""
    m = max(min(raw), 1e-3)
    return "".join("s" if g <= SHAPE_RATIO * m else "l" for g in raw)


class Counts:
    """Backoff chain: kinds -> kinds + rhythm shape -> + fastest gap -> + all three gaps."""
    def __init__(self):
        self.full = collections.defaultdict(collections.Counter)
        self.fast = collections.defaultdict(collections.Counter)
        self.shape = collections.defaultdict(collections.Counter)
        self.kinds = collections.defaultdict(collections.Counter)
        self.fastest = collections.defaultdict(collections.Counter)  # v1 backoff, kept for comparison
        self.use_shape = True

    def add(self, kinds, gaps, pat, shape):
        self.fastest[(kinds, min(gaps))][pat] += 1
        self.full[(kinds, gaps)][pat] += 1
        self.fast[(kinds, shape, min(gaps))][pat] += 1
        self.shape[(kinds, shape)][pat] += 1
        self.kinds[kinds][pat] += 1

    def surprisal(self, kinds, gaps, pat, shape):
        c3 = self.kinds.get(kinds, {})
        p = (c3.get(pat, 0) + 1) / (sum(c3.values()) + len(c3) + 1)
        chain = (((self.shape, (kinds, shape)), (self.fast, (kinds, shape, min(gaps))), (self.full, (kinds, gaps)))
                 if self.use_shape else ((self.fastest, (kinds, min(gaps))), (self.full, (kinds, gaps))))
        for table, key in chain:
            c = table.get(key, {})
            p = (c.get(pat, 0) + ALPHA * p) / (sum(c.values()) + ALPHA)
        return -math.log(p)


def _finger_chart(path):
    d = json.load(gzip.open(path, "rt"))
    tokens = [t for run in d["runs"] for t in run["tokens"]]
    out = dict(chart_id=d["chart_id"], split=d["split"], constant=d["constant"], styles={})
    for style in (*STYLES, "free"):
        cost, rec = play(tokens, style)
        out["styles"][style] = dict(cost=cost, seq=sequence(tokens, rec),
                                    parts={k: sum(r["cost"][k] for r in rec) for k in rec[0]["cost"]},
                                    seconds=tokens[-1][0] - tokens[0][0])
    return out


def fingering():
    (OUT / "fingering").mkdir(parents=True, exist_ok=True)
    paths = sorted((ROOT / "processed/charts").glob("*.json.gz"))
    with multiprocessing.Pool() as pool:
        for r in pool.imap_unordered(_finger_chart, paths):
            name = r["chart_id"].replace(":", ".")
            with gzip.open(OUT / "fingering" / f"{name}.json.gz", "wt") as f:
                json.dump(r, f)
            print("done", r["chart_id"], flush=True)


def load_fingering():
    return [json.load(gzip.open(p, "rt")) for p in sorted((OUT / "fingering").glob("*.json.gz"))]


def fit_counts(charts):
    counts = {s: Counts() for s in STYLES}
    for c in charts:
        if c["split"] != "train":
            continue
        for s in STYLES:
            for _, kinds, gaps, pat, shape in patterns(c["styles"][s]["seq"]):
                counts[s].add(kinds, gaps, pat, shape)
    return counts


def window_feel(counts, tokens):
    """Mean surprisal per style and the worst patterns, for one window played on its own."""
    out = {}
    for s in STYLES:
        _, rec = play(tokens, s)
        seq = sequence(tokens, rec)
        pats = patterns(seq)
        if not pats:
            out[s] = None
            continue
        sur = [counts[s].surprisal(k, g, p, sh) for _, k, g, p, sh in pats]
        worst = sorted(range(len(pats)), key=lambda j: -sur[j])[:3]
        out[s] = dict(mean=float(np.mean(sur)),
                      worst=[dict(time_s=round(seq[pats[j][0] - N + 1][0], 3), pattern=list(seq[i][2] for i in range(pats[j][0] - N + 1, pats[j][0] + 1)),
                                  gaps=[GAP_LABELS[b] for b in pats[j][2]],
                                  surprisal=round(sur[j], 2)) for j in worst])
    return out


class Reference:
    def __init__(self, values):
        self.values = np.sort(np.asarray(values, float))

    def p(self, v):  # share of official windows with at least this much surprisal
        return (len(self.values) - np.searchsorted(self.values, v, side="left") + 1) / (len(self.values) + 1)


def tokens_of_window(w):
    return [[n["time"], n["type"], n["x"], n["duration"]] for n in w["notes"]]


def score(counts, refs, tokens):
    f = window_feel(counts, tokens)
    ps = {s: (float(refs[s].p(f[s]["mean"])) if f[s] else None) for s in STYLES}
    valid = [p for p in ps.values() if p is not None]
    return dict(p_feel=max(valid) if valid else None, p_by_style=ps, detail=f)


def auroc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None]) + .5 * (pos[:, None] == neg[None])).mean())


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def pattern_table(counts):
    """Two-finger single-note runs at an even speed: which hand patterns official charts produce."""
    table = {}
    for b, label in enumerate(GAP_LABELS):
        c = counts["two"].full.get((("1",) * N, (b,) * (N - 1)), collections.Counter())
        total = sum(c.values())
        if not total:
            continue
        named = collections.Counter()
        for pat, n in c.items():
            named["".join(t if len(t) == 1 else "(" + t + ")" for t in pat)] += n
        table[label] = dict(count=total, share={k: round(v / total, 3) for k, v in named.most_common(8)})
    return table


def shape_table(counts):
    """Two-finger single-note runs whose fastest gap is <= 0.1 s, by rhythm shape (s = fastest, l = longer)."""
    table = {}
    for shape in ("sss", "ssl", "sls", "lss", "sll", "lsl", "lls"):
        c = collections.Counter()
        for b in range(2):
            c.update(counts["two"].fast.get((("1",) * N, shape, b), {}))
        total = sum(c.values())
        named = collections.Counter()
        for pat, n in c.items():
            named["".join(t if len(t) == 1 else "(" + t + ")" for t in pat)] += n
        table[shape] = dict(count=total, share={k: round(v / total, 3) for k, v in named.most_common(6)})
    return table


def pattern_surprisals(counts, tokens, style):
    _, rec = play(tokens, style)
    return [(sh, counts[style].surprisal(k, g, p, sh)) for _, k, g, p, sh in patterns(sequence(tokens, rec))]


def by_rhythm(counts, test, rng):
    """Per-pattern surprisal, official vs random x, split into even ("sss") and uneven rhythm; v1 vs v2 backoff."""
    out = {}
    for use_shape in (False, True):
        for s in STYLES:
            counts[s].use_shape = use_shape
        off, rnd = collections.defaultdict(list), collections.defaultdict(list)
        r2 = np.random.default_rng(rng)
        for w in test:
            tk = tokens_of_window(w)
            rk = [[a, b, float(r2.uniform(.05, .95)), d] for a, b, _, d in tk]
            for sh, v in pattern_surprisals(counts, tk, "two"):
                off["even" if sh == "sss" else "uneven"].append(v)
            for sh, v in pattern_surprisals(counts, rk, "two"):
                rnd["even" if sh == "sss" else "uneven"].append(v)
        out["shape_backoff" if use_shape else "v1_backoff"] = {
            k: dict(official_mean=float(np.mean(off[k])), random_mean=float(np.mean(rnd[k])),
                    auroc=auroc(-np.array(off[k]), -np.array(rnd[k])), patterns=len(off[k])) for k in ("even", "uneven")}
    for s in STYLES:
        counts[s].use_shape = True
    return out


def check():
    sys.path.insert(0, str(ROOT))
    from build_dataset import pure_notes, segments, windows_of
    from judge_model import load_windows
    import train_judge as T
    charts = load_fingering()
    counts = fit_counts(charts)
    result = {}
    # 1. simulator sanity: cost per second should rise with the chart constant
    result["cost_per_second_vs_constant_spearman"] = {
        s: spearman([c["styles"][s]["cost"] / c["styles"][s]["seconds"] for c in charts], [c["constant"] for c in charts])
        for s in (*STYLES, "free")}
    result["charts_two_finger_needs_more_fingers"] = sum(c["styles"]["two"]["parts"]["miss"] > 0 for c in charts)
    result["patterns_train"] = {s: sum(sum(v.values()) for v in counts[s].kinds.values()) for s in STYLES}
    # 2. the LRLR / LLRR table
    result["two_finger_single_note_patterns"] = pattern_table(counts)
    result["two_finger_uneven_rhythm_patterns"] = shape_table(counts)
    # 3. reference from validation windows
    splits = load_windows()
    val = [window_feel(counts, tokens_of_window(w)) for w in splits["validation"]]
    refs = {s: Reference([v[s]["mean"] for v in val if v[s]]) for s in STYLES}
    (OUT / "reference.json").write_text(json.dumps({s: refs[s].values.tolist() for s in STYLES}) + "\n")
    # 4. held-out official vs random x vs generator (same timing and types)
    rng = np.random.default_rng(7)
    test, pool = splits["test"], T.load_pool(ROOT / "runs/pool", "test")
    off, rnd, gen, rows = [], [], [], []
    for w, p in zip(test, pool):
        tk = tokens_of_window(w)
        o = score(counts, refs, tk); off.append(o["p_feel"])
        rows.append(dict(id=w["id"], **o))
        r = [[a, b, float(rng.uniform(.05, .95)), d] for a, b, _, d in tk]
        rnd.append(score(counts, refs, r)["p_feel"])
        for c in p["candidates"]:
            if c["lock"] == 0:
                g = [[a, b, x / 127, d] for (a, b, _, d), x in zip(tk, c["bins"])]
                gen.append(score(counts, refs, g)["p_feel"])
    skipped = dict(official=sum(v is None for v in off), random=sum(v is None for v in rnd), generator=sum(v is None for v in gen))
    off, rnd, gen = ([v for v in a if v is not None] for a in (off, rnd, gen))
    rows = [r for r in rows if r["p_feel"] is not None]
    result["test_windows_without_patterns"] = skipped  # drag-only or fewer than four press groups
    result["test"] = dict(official_median_p=float(np.median(off)), official_flagged=float(np.mean(np.array(off) < .05)),
                          random_x_median_p=float(np.median(rnd)), random_x_flagged=float(np.mean(np.array(rnd) < .05)),
                          generator_median_p=float(np.median(gen)), generator_flagged=float(np.mean(np.array(gen) < .05)),
                          auroc_official_vs_random_x=auroc(off, rnd), auroc_official_vs_generator=auroc(off, gen),
                          windows=len(off), generator_windows=len(gen))
    result["pattern_surprisal_by_rhythm"] = by_rhythm(counts, test, 11)
    rows.sort(key=lambda r: r["p_feel"])
    result["test_lowest_feel"] = rows[:6]
    # 5. AI studies (charts/silent)
    silent = pathlib.Path("/Users/jesse/Projects/PhiChain/charts/silent")
    items = [("silent-180-sixteenths", silent / "silent-180-sixteenths/pez-export/chart-official.json")]
    items += [(p.parts[-4] + "/" + p.parts[-3], p) for p in sorted(silent.glob("silent-150-*/*/pez-export/chart.json"))]
    studies = {}
    for name, path in items:
        notes = pure_notes(json.loads(path.read_text(encoding="utf-8-sig")))
        ws = windows_of(notes, segments(notes))
        sc = []
        for w in ws:
            t0 = w[0]["time"]
            sc.append(score(counts, refs, [[n["time"] - t0, n["type"], min(1, max(0, n["x"])), n["duration"]] for n in w]))
        ps = [s["p_feel"] for s in sc if s["p_feel"] is not None]
        studies[name] = dict(windows=len(ps), median_p=float(np.median(ps)) if ps else None,
                             flagged=float(np.mean(np.array(ps) < .05)) if ps else None,
                             worst=min(sc, key=lambda s: s["p_feel"] if s["p_feel"] is not None else 9) if sc else None)
    result["ai_studies"] = studies
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    summary = {k: v for k, v in result.items() if k not in ("test_lowest_feel", "ai_studies", "two_finger_single_note_patterns")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for k, v in studies.items():
        print(f"{k:45s} windows={v['windows']:2d} median_p={v['median_p']} flagged={v['flagged']}")


if __name__ == "__main__":
    {"fingering": fingering, "check": check}[sys.argv[1]]()
