"""Run L0 and L1 on one chart and write a report for the controller and the user.

    python3 judge.py CHART.json [--start S --end S] [--max-fingers N] [--axes hand,line] [--out report.json]

Outcomes:
    invalid   L0 failed. Do not send to review.
    stopped   A provisional gate in gates.json fired. Do not send to review.
    review    Send to L2 blind review. This is not approval.
"""
import argparse
import json
from pathlib import Path

from l0_validity import check
from l1_detectors import analyze

HERE = Path(__file__).resolve().parent
EXCERPT_LIMIT_S = 45.0
AXES = {
    "hand": ("fresh_onsets", "onset_", "required_", "direction_", "x_spread"),
    "line": ("carrier_", "background_", "any_motion", "strong_", "judging_", "longest_", "bg_", "section_line"),
    "approach": ("approach_",),
}


def axis_of(metric):
    for axis, prefixes in AXES.items():
        if metric.startswith(prefixes):
            return axis
    return "structure"


def judge(path, start=None, end=None, max_fingers=None, axes=("hand", "line", "approach", "structure")):
    l0 = check(str(path), max_fingers=max_fingers)
    report = {"chart": str(path), "range_s": [start, end], "l0": l0, "l1": None, "flags": [], "gates_fired": []}
    if not l0["pass"]:
        return {**report, "outcome": "invalid"}

    l1 = analyze(str(path), start, end)
    report["l1"] = l1
    bands_doc = json.loads((HERE.parent / "bands" / "official-in.json").read_text())
    scope = "excerpt" if l1["span_s"] < EXCERPT_LIMIT_S else "whole"
    bands = bands_doc[scope]
    report["band_scope"] = scope
    for name, value in l1["metrics"].items():
        band = bands.get(name)
        if value is None or band is None or axis_of(name) not in axes:
            continue
        if value < band["p05"] or value > band["p95"]:
            report["flags"].append({"metric": name, "value": value, "official_p05": band["p05"], "official_p50": band["p50"], "official_p95": band["p95"]})

    gates_path = HERE / "gates.json"
    gates = json.loads(gates_path.read_text())["gates"] if gates_path.exists() else []
    for gate in gates:
        value = l1["metrics"].get(gate["metric"])
        if value is None or gate["axis"] not in axes:
            continue
        hit = value < gate["threshold"] if gate["direction"] == "floor" else value > gate["threshold"]
        if hit:
            report["gates_fired"].append({**gate, "value": value})
    return {**report, "outcome": "stopped" if report["gates_fired"] else "review"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chart")
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument("--max-fingers", type=int)
    parser.add_argument("--axes", default="hand,line,approach,structure")
    parser.add_argument("--out")
    args = parser.parse_args()
    report = judge(args.chart, args.start, args.end, args.max_fingers, tuple(args.axes.split(",")))
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text)
    print(f"outcome: {report['outcome']}")
    for error in report["l0"]["errors"]:
        print(f"  L0 error {error['code']}: {error['detail']}")
    for gate in report["gates_fired"]:
        print(f"  gate {gate['metric']} = {gate['value']} ({gate['direction']} {gate['threshold']})")
    for flag in report["flags"]:
        print(f"  outside official p05-p95: {flag['metric']} = {flag['value']} (band {flag['official_p05']}..{flag['official_p95']})")
    return 1 if report["outcome"] == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
