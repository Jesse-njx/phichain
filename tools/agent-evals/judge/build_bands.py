"""Build official reference distributions for L1 from the frozen IN corpus.

Whole-chart measurements compare with whole-song candidates. Short excerpts behave
differently from whole charts, so evenly spaced fixed-length slices supply a separate
band for excerpt candidates. Bands describe official charts; they are not quotas.
"""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

from chartmodel import load
from l1_detectors import analyze, quantile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STUDY = ROOT / "main" / "research" / "judgment-line-study"
OUT = HERE.parent / "bands" / "official-in.json"
SLICE_S = 13.0
SLICES_PER_CHART = 6
QS = {"p05": 0.05, "p25": 0.25, "p50": 0.5, "p75": 0.75, "p95": 0.95}


def measure(record):
    path = STUDY / "sources" / f"{record['id']}.json"
    chart = load(str(path))
    notes = chart.notes
    first, last = notes[0].t, max(n.end for n in notes)
    whole = analyze(chart)
    slices = []
    if last - first > SLICE_S:
        step = (last - first - SLICE_S) / max(1, SLICES_PER_CHART - 1)
        for i in range(SLICES_PER_CHART):
            a = first + i * step
            result = analyze(chart, a, a + SLICE_S)
            if result["notes"] >= 10:
                slices.append(result["metrics"])
    return {"id": record["id"], "title": record["title"], "whole": whole["metrics"], "slices": slices}


def summarize(rows):
    names = sorted({k for r in rows for k in r})
    out = {}
    for name in names:
        values = [r[name] for r in rows if r.get(name) is not None]
        if values:
            out[name] = {"n": len(values), **{k: round(quantile(values, q), 3) for k, q in QS.items()}}
    return out


def main():
    records = json.loads((STUDY / "inventory.json").read_text())["charts"]
    records = [r for r in records if r["difficulty"] == "IN"]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(measure, records, chunksize=4))
    bands = {
        "source": "research/judgment-line-study/sources, IN charts in inventory.json",
        "charts": len(rows),
        "slice_seconds": SLICE_S,
        "slices": sum(len(r["slices"]) for r in rows),
        "whole": summarize([r["whole"] for r in rows]),
        "excerpt": summarize([s for r in rows for s in r["slices"]]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bands, indent=1))
    print(f"{bands['charts']} charts, {bands['slices']} slices -> {OUT}")


if __name__ == "__main__":
    main()
