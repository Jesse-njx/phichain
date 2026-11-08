"""Independently check processed/ against the per-chart files and source checksums."""
import collections
import gzip
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
EPS = 1e-4


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    windows = json.load(gzip.open(ROOT / "processed/windows.json.gz", "rt"))
    splits = json.loads((ROOT / "processed/splits.json").read_text())
    dates = {s["song_id"]: s["released"] for s in json.loads((ROOT / "provenance/release-dates.json").read_text())["songs"]}
    problems, info = collections.Counter(), collections.Counter()
    charts = {}
    for c in manifest:
        doc = json.load(gzip.open(ROOT / "processed/charts" / (c["chart_id"].replace(":", ".") + ".json.gz"), "rt"))
        if c["level"] == "AT":
            raw = (ROOT / "raw" / c["source_path"]).read_bytes()
            problems["at_checksum"] += hashlib.sha256(raw).hexdigest() != doc["source_sha256"] or len(raw) != c["bytes"]
        # Completeness against the original file, computed without the converter.
        src = json.loads((ROOT / "raw" / c["source_path"]).read_bytes() if c["level"] == "AT"
                         else (ROOT.parent / "arrangement-training/raw" / c["source_path"]).read_bytes())
        expected = sorted(round(n["time"] * 1.875 / line["bpm"] + src["offset"], 3)
                          for line in src["judgeLineList"] for side in ("notesAbove", "notesBelow") for n in line[side])
        got = sorted(round(t[0], 3) for r in doc["runs"] for t in r["tokens"])
        problems["chart_note_count_or_time_mismatch"] += len(expected) != len(got) or any(abs(a - b) > 2e-3 for a, b in zip(expected, got))
        problems["release_before_cutoff"] += dates[c["song_id"]] < "2024-01-01"
        charts[c["chart_id"]] = doc
    per_song_split = collections.defaultdict(set)
    for w in windows:
        doc = charts[w["chart_id"]]
        per_song_split[w["song_id"]].add(w["split"])
        problems["split_mismatch"] += splits[w["song_id"]] != w["split"]
        toks = w["tokens"]; t0 = w["start_s"]; t1 = t0 + toks[-1][0]
        problems["unsorted"] += any(b[0] < a[0] - 1e-9 for a, b in zip(toks, toks[1:]))
        problems["size"] += not (16 <= len(toks) <= 128) or toks[-1][0] > 12 + EPS
        problems["hold_cut_at_end"] += any(t[0] + t[3] > toks[-1][0] + EPS for t in toks)
        info["windows_with_offscreen_x"] += any(not 0 <= t[2] <= 1 for t in toks)
        problems["type"] += any(t[1] not in (1, 2, 3, 4) or (t[1] != 3 and t[3]) for t in toks)
        # Completeness: every chart note in [t0, t1] is in the window.
        run_notes = [t for r in doc["runs"] for t in r["tokens"] if t0 - EPS <= t[0] <= t1 + EPS]
        problems["count_mismatch"] += len(run_notes) != len(toks)
        problems["hold_cut_at_start"] += any(t[1] == 3 and t[0] < t0 - EPS < t0 + EPS < t[0] + t[3] for r in doc["runs"] for t in r["tokens"])
    problems["song_in_two_splits"] = sum(len(v) > 1 for v in per_song_split.values())
    result = dict(windows=len(windows), charts=len(charts), problems=dict(problems), info=dict(info), ok=not any(problems.values()))
    (ROOT / "processed/verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
