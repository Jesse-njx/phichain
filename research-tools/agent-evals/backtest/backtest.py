"""Check whether L0 and L1 agree with recorded user verdicts.

HYPOTHESES below were fixed before any labelled chart was evaluated. Metrics outside
this list are reported in the table but cannot become gates from this backtest,
because choosing among many metrics after seeing a small sample would overfit.

A gate only ever stops a candidate before user review. It can never approve one.
A hypothesis becomes a gate only if a threshold exists that:
  1. rejects no user-passed chart on that axis,
  2. is no stricter than the official p05 (floor) or p95 (ceiling) band edge, and
  3. catches at least half of the user-failed charts on that axis, and
  4. has at least MIN_FAILED user-failed charts on that axis.

Rule 4 was added after the first run, in which a single failed chart would otherwise
have created a gate. It only makes adoption stricter.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
from l0_validity import check  # noqa: E402
from l1_detectors import analyze  # noqa: E402

ROOT = HERE.parents[3]
MIN_FAILED = 3
HYPOTHESES = [
    {"metric": "required_move_under50_pct", "axis": "hand", "direction": "ceiling", "why": "Hands can stay nearly still (run02 finding)."},
    {"metric": "required_move_median_px", "axis": "hand", "direction": "floor", "why": "Typical required move is too small."},
    {"metric": "required_travel_px_per_s", "axis": "hand", "direction": "floor", "why": "Too little total hand movement."},
    {"metric": "any_motion_pct", "axis": "line", "direction": "floor", "why": "Lines rest through most of the passage."},
    {"metric": "strong_motion_pct", "axis": "line", "direction": "floor", "why": "Line motion is imperceptible (run02 finding)."},
    {"metric": "judging_carrier_motion_pct", "axis": "line", "direction": "floor", "why": "Receiver is stiff during play (Iris, Override findings)."},
    {"metric": "longest_all_still_during_play_s", "axis": "line", "direction": "ceiling", "why": "Long dead stretches during play (run02 finding)."},
    {"metric": "bg_two_plus_lines_moving_pct", "axis": "line", "direction": "floor", "why": "One line dancing rather than an ensemble (C finding)."},
    {"metric": "approach_heights_per_s_median", "axis": "approach", "direction": "floor", "why": "Slow note approach (Iris, Happy Ending speed findings)."},
]


def evaluate(hypothesis, rows, bands):
    metric, axis, direction = hypothesis["metric"], hypothesis["axis"], hypothesis["direction"]
    passed = [r for r in rows if r.get(axis) == "pass" and r["l1"].get(metric) is not None]
    failed = [r for r in rows if r.get(axis) == "fail" and r["l1"].get(metric) is not None]
    overall = [r for r in rows if r.get(axis) is None and r.get("overall") == "fail" and r["l1"].get(metric) is not None]
    edge = bands["excerpt"].get(metric, {}).get("p05" if direction == "floor" else "p95")
    pass_values = [r["l1"][metric] for r in passed]
    limits = list(pass_values) + ([edge] if edge is not None else [])
    threshold = None
    if limits:
        threshold = min(limits) if direction == "floor" else max(limits)

    def caught(row):
        value = row["l1"][metric]
        return value < threshold if direction == "floor" else value > threshold

    catches = [r["id"] for r in failed if threshold is not None and caught(r)]
    extra = [r["id"] for r in overall if threshold is not None and caught(r)]
    missed = [r["id"] for r in failed if r["id"] not in catches]
    if not passed:
        status = "no_passed_sample"
    elif not failed:
        status = "no_failed_sample"
    elif 2 * len(catches) >= len(failed):
        status = "provisional_gate" if len(failed) >= MIN_FAILED else "weak_signal"
    else:
        status = "report_only"
    return {
        **hypothesis,
        "threshold": threshold,
        "official_edge": edge,
        "passed_n": len(passed),
        "failed_n": len(failed),
        "caught": catches,
        "missed": missed,
        "also_caught_overall_fail": extra,
        "passed_values": {r["id"]: r["l1"][metric] for r in passed},
        "failed_values": {r["id"]: r["l1"][metric] for r in failed},
        "status": status,
    }


def main():
    labels = json.loads((HERE / "labels.json").read_text())
    bands = json.loads((HERE.parent / "bands" / "official-in.json").read_text())
    rows = []
    # Blind review results from L2 add labels here as they arrive.
    for extra in sorted((HERE / "labels.d").glob("*.json")) if (HERE / "labels.d").exists() else []:
        labels["cases"] += json.loads(extra.read_text())["cases"]
    for case in labels["cases"] + labels["unlabelled"]:
        path = ROOT / case["path"]
        if not path.exists():
            print("MISSING", case["id"], case["path"])
            continue
        span = labels["slices"].get(case.get("slice"), (case.get("start"), case.get("end")))
        result = analyze(str(path), span[0], span[1])
        rows.append({**case, "l0": check(str(path)), "l1": result["metrics"], "notes": result["notes"], "span_s": result["span_s"]})
    gates = [evaluate(h, rows, bands) for h in HYPOTHESES]
    out = {
        "rows": [{k: v for k, v in r.items() if k != "evidence"} for r in rows],
        "hypotheses": gates,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    (HERE.parent / "judge" / "gates.json").write_text(json.dumps({
        "generated_by": "backtest/backtest.py",
        "note": "Provisional. Small labelled sample. Gates stop candidates; they never approve them.",
        "gates": [{k: g[k] for k in ("metric", "axis", "direction", "threshold", "status", "why")} for g in gates if g["status"] == "provisional_gate"],
    }, indent=1))

    print(f"L0 failures: {[(r['id'], [e['code'] for e in r['l0']['errors']]) for r in rows if not r['l0']['pass']]}")
    for g in gates:
        print(f"\n{g['metric']} [{g['axis']} {g['direction']}] -> {g['status']}; threshold {g['threshold']}, official edge {g['official_edge']}")
        print(f"  pass: {g['passed_values']}")
        print(f"  fail: {g['failed_values']}")
        print(f"  caught {g['caught']}; missed {g['missed']}; overall-fail also caught {g['also_caught_overall_fail']}")


if __name__ == "__main__":
    main()
