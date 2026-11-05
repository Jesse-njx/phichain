"""Benchmark AI-written charts against official IN charts with the judgement layers.

Compares like with like:
- whole-song AI charts against whole official charts
- excerpts against official slices of the nearest length (10, 13 or 30 s)

The comparison group is official IN at constant 15.0 and above, because AI briefs target
the top of the difficulty range. All official IN is kept as a second reference.

Being inside the official range does not mean a chart is good, and being outside does not
mean it is bad. No score is produced. Results go to results.json and summary.md.
"""
from concurrent.futures import ProcessPoolExecutor
import csv
import json
from pathlib import Path
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
from chartmodel import load  # noqa: E402
from l0_validity import check  # noqa: E402
from l1_detectors import analyze, quantile  # noqa: E402

ROOT = HERE.parents[3]
STUDY = ROOT / "research" / "judgment-line-study"
LENGTHS = (10.0, 13.0, 30.0)
SLICES = 6
EXCERPT_LIMIT = 45.0
MIN_SPAN = 8.0
HIGH_CONSTANT = 15.0
NAMED = ("AbsoluTe disoRdeR", "Der Schneid", "Entrance to the Chaos", "Fractured Angel", "Non-Melodic Ragez (MUG Edit)", "QZKago Requiem", "Verrückt", "What do you want more than a Happy ending?")

HE = "charts/happy-ending/"
OV = "charts/override/"
XT = "charts/xterfusion/"
SI = "charts/silent/"
# (id, path, recorded user verdict, axes the study is meant to test)
FULL = ("hand", "line", "approach", "structure")
HAND = ("hand", "approach", "structure")
AI = [
    ("he-sol-run01", HE + "happy-ending-sol-baseline/run-01/project/chart.json", "unknown", FULL),
    ("he-presentation-r01", HE + "happy-ending-sol-baseline/presentation-revision-01/project/chart.json", "rejected", FULL),
    ("he-run02", HE + "happy-ending-guided-run02/project/chart.json", "rejected", FULL),
    ("he-run03", HE + "happy-ending-performance-run03/project/chart.json", "rejected", FULL),
    ("he-five-A", HE + "happy-ending-five-authors/A/project/chart.json", "rejected", FULL),
    ("he-five-B", HE + "happy-ending-five-authors/B/project/chart.json", "rejected", FULL),
    ("he-five-C", HE + "happy-ending-five-authors/C/project/chart.json", "rejected", FULL),
    ("he-five-D", HE + "happy-ending-five-authors/D/project/chart.json", "rejected", FULL),
    ("he-five-E", HE + "happy-ending-five-authors/E/project/chart.json", "rejected", FULL),
    ("he-full-c", HE + "happy-ending-full-c-revision/full/project/chart.json", "pending", FULL),
    ("override-sol-in163", OV + "override-sol-in163/project/chart.json", "unknown", FULL),
    ("override-sol-in163-perf", OV + "override-sol-in163-performance/project/chart.json", "pending", FULL),
    ("override-three-a", OV + "override-three-2026-11-02/a/project/chart.json", "rejected", FULL),
    ("override-three-b", OV + "override-three-2026-11-02/b/project/chart.json", "rejected", FULL),
    ("override-three-c", OV + "override-three-2026-11-02/c/project/chart.json", "rejected", FULL),
    ("xterfusion-first", XT + "Xterfusion/chart.json", "unknown", FULL),
    ("xterfusion-sol", XT + "Xterfusion-Sol-20261102/project/chart.json", "rejected", FULL),
    ("xterfusion-audio-only", XT + "xterfusion-audio-only-run01/full/project/chart.json", "pending", FULL),
    ("climax-A", HE + "happy-ending-climax-diagnostics/A/project/chart.json", "rejected", FULL),
    ("climax-B", HE + "happy-ending-climax-diagnostics/B/project/chart.json", "rejected", FULL),
    ("climax-C-initial", HE + "happy-ending-climax-diagnostics/history/C-before-orientation-fix/project/chart.json", "rejected", FULL),
    ("climax-C-orientation", HE + "happy-ending-climax-diagnostics/history/C-before-ensemble/project/chart.json", "rejected", FULL),
    ("climax-C-ensemble", HE + "happy-ending-climax-diagnostics/C/project/chart.json", "approved", FULL),
    ("iris-original", XT + "xterfusion-iris-study/project/chart.json", "rejected", FULL),
    ("iris-revision-D", XT + "xterfusion-iris-study/calibration/D/project/chart.json", "pending", FULL),
    ("escapement-transfer", "charts/other/line-phrase-transfer/project/chart.json", "unknown", FULL),
    ("entrance-transfer", "charts/other/entrance-in-transfer/project/chart.json", "unknown", FULL),
    ("silent-180-wide-travel", SI + "silent-180-sixteenths/project/chart.json", "approved", HAND),
    ("silent-180-arrangement", SI + "silent-180-arrangement/project/chart.json", "unknown", HAND),
    ("silent-150-style-one", SI + "silent-150-two-styles/style-one/project/chart.json", "accepted", HAND),
    ("silent-150-style-two", SI + "silent-150-two-styles/style-two/project/chart.json", "accepted", HAND),
    ("silent-150-tech", SI + "silent-150-four-key/tech/project/chart.json", "accepted", HAND),
    ("silent-150-speed", SI + "silent-150-four-key/speed/project/chart.json", "accepted", HAND),
    ("silent-150-stream", SI + "silent-150-four-key/stream/project/chart.json", "accepted", HAND),
    ("silent-150-jack", SI + "silent-150-four-key/jack/project/chart.json", "corrected", HAND),
]
EXCLUDED = {
    "charts/other/projects/stardust-ray-in": "human-charted official source",
    "charts/other/entrance-study, poseidon-study": "official imports",
    "charts/other/rrharil-at-scroll-130": "community chart with a speed change",
    "charts/other/poseidon-pure-configuration": "adaptation that keeps existing note timing",
    "override-gesture-sample": "under 8 s of play",
    "speed-revision-01, Iris calibration B and C, override pilot": "near-duplicates of included charts",
}
AXIS_PREFIX = {
    "hand": ("fresh_onsets", "onset_", "required_", "direction_", "x_spread", "section_density", "section_travel", "section_spread"),
    "line": ("carrier_", "background_", "any_motion", "strong_", "judging_", "longest_", "bg_", "section_line"),
    "approach": ("approach_",),
}
HEADLINE = [
    "fresh_onsets_per_s", "required_move_median_px", "required_move_under50_pct", "required_travel_px_per_s",
    "approach_heights_per_s_median", "carrier_motion_pct", "background_motion_pct", "strong_motion_pct",
    "bg_two_plus_lines_moving_pct", "longest_carrier_still_during_play_s", "section_travel_cv", "section_line_activity_cv",
]


def axis_of(metric):
    for axis, prefixes in AXIS_PREFIX.items():
        if metric.startswith(prefixes):
            return axis
    return "structure"


def constants():
    table = {}
    for row in csv.reader((ROOT / "research/overnight-study/corpus/difficulty.tsv").open(), delimiter="\t"):
        if len(row) >= 4:
            table[row[0]] = float(row[3])
    return table


def measure_official(record):
    chart = load(str(STUDY / "sources" / f"{record['id']}.json"))
    first, last = chart.notes[0].t, max(n.end for n in chart.notes)
    out = {"whole": analyze(chart)["metrics"]}
    for length in LENGTHS:
        rows = []
        if last - first > length:
            step = (last - first - length) / (SLICES - 1)
            for i in range(SLICES):
                a = first + i * step
                result = analyze(chart, a, a + length)
                if result["notes"] >= 10:
                    rows.append(result["metrics"])
        out[str(int(length))] = rows
    return {**record, **out}


def measure_ai(item):
    case, path, verdict, axes = item
    report = analyze(str(ROOT / path))
    return {"id": case, "path": path, "verdict": verdict, "axes": axes, "l0": check(str(ROOT / path)), **report}


def band(rows):
    names = {k for r in rows for k in r}
    out = {}
    for name in names:
        values = sorted(r[name] for r in rows if r.get(name) is not None)
        if values:
            out[name] = {"values": values, "p05": quantile(values, 0.05), "p50": quantile(values, 0.5), "p95": quantile(values, 0.95)}
    return out


def percentile(value, values):
    below = sum(v < value for v in values)
    ties = sum(v == value for v in values)
    return round(100 * (below + ties / 2) / len(values), 1)


def compare(metrics, bands, axes):
    flags, percentiles = [], {}
    for name, value in metrics.items():
        entry = bands.get(name)
        if value is None or entry is None:
            continue
        percentiles[name] = percentile(value, entry["values"])
        if axis_of(name) in axes and not entry["p05"] <= value <= entry["p95"]:
            flags.append(name)
    return flags, percentiles


def strip(bands):
    return {k: {x: round(v[x], 3) for x in ("p05", "p50", "p95")} | {"n": len(v["values"])} for k, v in bands.items()}


def fmt(value):
    if value is None:
        return "–"
    return f"{value:.0f}" if abs(value) >= 100 else f"{value:.2f}".rstrip("0").rstrip(".")


def main():
    records = [r for r in json.loads((STUDY / "inventory.json").read_text())["charts"] if r["difficulty"] == "IN"]
    table = constants()
    for record in records:
        record["constant"] = table.get(record["song_id"])
    with ProcessPoolExecutor() as pool:
        official = list(pool.map(measure_official, records, chunksize=4))
        ai = list(pool.map(measure_ai, AI, chunksize=1))
    high = [o for o in official if (o["constant"] or 0) >= HIGH_CONSTANT]
    known = sum(o["constant"] is not None for o in official)

    groups = {"high": high, "all": official}
    bands = {}
    for name, rows in groups.items():
        bands[name] = {"whole": band([r["whole"] for r in rows])}
        for length in LENGTHS:
            key = str(int(length))
            bands[name][key] = band([s for r in rows for s in r[key]])

    def scope(span):
        if span >= EXCERPT_LIMIT:
            return "whole"
        return str(int(min(LENGTHS, key=lambda v: abs(v - span))))

    # How often official charts themselves leave the band sets the base rate for a flag.
    self_flags = {"whole": [], "excerpt": []}
    for o in high:
        self_flags["whole"].append(len(compare(o["whole"], bands["high"]["whole"], FULL)[0]))
        for s in o["13"]:
            self_flags["excerpt"].append(len(compare(s, bands["high"]["13"], FULL)[0]))

    for row in ai:
        row["comparable"] = row["span_s"] >= MIN_SPAN and bool(row["metrics"])
        row["scope"] = scope(row["span_s"])
        if row["comparable"]:
            row["flags"], row["percentile_high"] = compare(row["metrics"], bands["high"][row["scope"]], row["axes"])
            row["flags_all_in"], _ = compare(row["metrics"], bands["all"][row["scope"]], row["axes"])

    named = [
        {"title": o["title"], "constant": o["constant"], "metrics": o["whole"], "flags": compare(o["whole"], bands["high"]["whole"], FULL)[0]}
        for o in official if o["title"] in NAMED
    ]
    result = {
        "official": {"in_charts": len(official), "with_constant": known, "high_constant": len(high), "high_threshold": HIGH_CONSTANT},
        "excluded": EXCLUDED,
        "bands_high": {k: strip(v) for k, v in bands["high"].items()},
        "official_self_flags": {k: {"median": median(v), "p90": quantile(v, 0.9), "n": len(v)} for k, v in self_flags.items()},
        "named_official": named,
        "ai": ai,
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    write_summary(result)
    print((HERE / "summary.md").read_text())


def write_summary(result):
    ai = [r for r in result["ai"] if r["comparable"]]
    lines = ["# Benchmark: AI-written charts against official IN", ""]
    info = result["official"]
    lines += [
        f"Comparison group: {info['high_constant']} official IN charts at constant {info['high_threshold']}+ (of {info['in_charts']} IN, {info['with_constant']} with a known constant).",
        "Values inside the official range are not evidence of quality. No score is produced.",
        "",
        f"Base rate: an official chart itself gets {result['official_self_flags']['whole']['median']:g} flags (whole, median), "
        f"{result['official_self_flags']['excerpt']['median']:g} (13 s slice, median).",
        "",
    ]

    def table(title, rows, whole):
        lines.append(f"## {title}")
        lines.append("")
        names = ["required_move_median_px", "required_move_under50_pct", "fresh_onsets_per_s", "approach_heights_per_s_median", "carrier_motion_pct", "background_motion_pct", "strong_motion_pct", "bg_two_plus_lines_moving_pct"]
        short = ["move px", "<50px %", "hits/s", "approach", "carrier %", "bg %", "strong %", "2+ bg %"]
        lines.append("| Chart | Verdict | L0 | " + " | ".join(short) + " | Flags |")
        lines.append("|" + "---|" * (len(short) + 4))
        band_rows = result["bands_high"]["whole" if whole else "13"]
        lines.append(f"| **Official p05..p95** | | | " + " | ".join(f"{fmt(band_rows[n]['p05'])}..{fmt(band_rows[n]['p95'])}" for n in names) + " | |")
        lines.append(f"| **Official median** | | | " + " | ".join(fmt(band_rows[n]["p50"]) for n in names) + " | |")
        for row in rows:
            m = row["metrics"]
            lines.append(f"| {row['id']} | {row['verdict']} | {'pass' if row['l0']['pass'] else 'FAIL'} | " + " | ".join(fmt(m.get(n)) for n in names) + f" | {len(row['flags'])} |")
        lines.append("")

    whole = [r for r in ai if r["scope"] == "whole"]
    band_whole = result["bands_high"]["whole"]
    lines += ["## Whole songs: what separates AI from official", "", f"{len(whole)} AI charts. A metric's official base rate is about 10%, by construction.", "",
              "| Metric | Official p05..p95 | AI median | AI below | AI above |", "|---|---|---|---|---|"]
    rows = []
    for name, entry in band_whole.items():
        values = [r["metrics"][name] for r in whole if r["metrics"].get(name) is not None]
        if values:
            rows.append((sum(v < entry["p05"] for v in values), sum(v > entry["p95"] for v in values), name, entry, median(values)))
    for low, high, name, entry, mid in sorted(rows, key=lambda r: -(r[0] + r[1])):
        lines.append(f"| {name} | {fmt(entry['p05'])}..{fmt(entry['p95'])} | {fmt(mid)} | {low} | {high} |")
    lines += ["", "## Flags by recorded verdict", "", "| Verdict | Scope | Charts | Flags, min / median / max |", "|---|---|---|---|"]
    for scope_name, subset in (("whole", whole), ("excerpt", [r for r in ai if r["scope"] != "whole"])):
        for verdict in sorted({r["verdict"] for r in subset}):
            counts = [len(r["flags"]) for r in subset if r["verdict"] == verdict]
            lines.append(f"| {verdict} | {scope_name} | {len(counts)} | {min(counts)} / {median(counts):g} / {max(counts)} |")
    lines.append("")

    table("Whole songs", whole, True)
    table("Excerpts (band shown is 13 s; flags use the nearest length)", [r for r in ai if r["scope"] != "whole"], False)

    lines += ["## Named official charts, whole", "", "| Chart | Constant | move px | <50px % | hits/s | approach | carrier % | bg % | strong % | 2+ bg % | Flags |", "|" + "---|" * 11]
    for row in result["named_official"]:
        m = row["metrics"]
        names = ["required_move_median_px", "required_move_under50_pct", "fresh_onsets_per_s", "approach_heights_per_s_median", "carrier_motion_pct", "background_motion_pct", "strong_motion_pct", "bg_two_plus_lines_moving_pct"]
        lines.append(f"| {row['title']} | {row['constant']} | " + " | ".join(fmt(m.get(n)) for n in names) + f" | {len(row['flags'])} |")
    lines += ["", "## Excluded", ""] + [f"- {k}: {v}" for k, v in result["excluded"].items()] + [""]
    (HERE / "summary.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
