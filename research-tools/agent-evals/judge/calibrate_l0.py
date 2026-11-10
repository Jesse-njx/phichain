"""Run L0 across the official IN corpus. An L0 error must not reject official charts."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

from chartmodel import load
from l0_validity import check

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[2] / "research" / "judgment-line-study"
OUT = HERE.parent / "bands" / "l0-corpus.json"


def run(record):
    path = STUDY / "sources" / f"{record['id']}.json"
    result = check(str(path), audio_seconds=1e9)
    chart = load(str(path))
    outside = []
    for line in chart.lines:
        for note in line.notes:
            x, y = line.head(note)
            if not (-0.02 <= x <= 1.02 and -0.02 <= y <= 1.02):
                outside.append([round(x, 2), round(y, 2)])
    return {
        "id": record["id"],
        "title": record["title"],
        "errors": sorted({e["code"] for e in result["errors"]}),
        "details": [e["detail"] for e in result["errors"]][:2],
        "warnings": sorted({w["code"] for w in result["warnings"]}),
        "max_contacts": result["stats"].get("max_contacts"),
        "notes": result["stats"].get("notes"),
        "outside": len(outside),
        "outside_sample": outside[:4],
    }


def main():
    records = json.loads((STUDY / "inventory.json").read_text())["charts"]
    records = [r for r in records if r["difficulty"] == "IN"]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(run, records, chunksize=4))
    summary = {
        "charts": len(rows),
        "errors": Counter(code for r in rows for code in r["errors"]),
        "warnings": Counter(code for r in rows for code in r["warnings"]),
        "max_contacts": Counter(str(r["max_contacts"]) for r in rows),
        "charts_with_offscreen_heads": sum(bool(r["outside"]) for r in rows),
        "offscreen_share_max": max(r["outside"] / max(1, r["notes"]) for r in rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "failing": [r for r in rows if r["errors"]]}, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    for row in [r for r in rows if r["errors"]][:12]:
        print(row["title"], row["errors"], row["details"], row["outside_sample"])


if __name__ == "__main__":
    main()
