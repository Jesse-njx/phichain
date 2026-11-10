"""Build the pure-arrangement dataset for the arrangement judge.

Selection: official IN and AT charts of songs released on or after --since
(default 2024-01-01, "after 2023"), from the pinned source snapshot used by
research/arrangement-training. IN files are reused from that corpus after a
checksum check; AT files are fetched from the same pinned commit and verified
against the pinned Git tree.

Representation: the pure configuration from agent-tools/pure-configuration
(`flatten`, the converter used for the QQ bot). Every note is kept, on one static
horizontal line, at its head-time horizontal position. Each note is four numbers,
[time_s, type, x, hold_s]: time (relative to the window start in windows), type
(1 Tap, 2 Drag, 3 Hold, 4 Flick), normalized x = 0.5 + positionX / 18 (official
units span 18 across the screen), hold duration in seconds.

Run from anywhere: python3 research/arrangement-judge/build_dataset.py
"""
import argparse
import collections
import gzip
import hashlib
import json
import pathlib
import random
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
CORPUS = ROOT.parent / "arrangement-training"
PURE = ROOT.parents[1] / "tools" / "pure-configuration"
sys.path.insert(0, str(PURE))
from convert import flatten  # noqa: E402

CONFIG = dict(minimum_notes=16, maximum_notes=128, maximum_seconds=12, gap_seconds=2.5,
              window_stride_notes=48, split_seed=20261106,
              split_fractions=dict(validation=.1, test=.1), decimals=5,
              x_units_per_screen=18)
EPS = 1e-5


def blob_sha1(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def fetch(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PhiChain-judge-dataset"}), timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def select(since):
    lock = json.loads((CORPUS / "provenance/source-lock.json").read_text())
    tree = {e["path"]: e for e in json.loads((CORPUS / "provenance/chart-tree.json").read_text())["tree"] if e["type"] == "blob"}
    excluded = {e["source_path"] for e in json.loads((CORPUS / "provenance/excluded-charts.json").read_text())}
    levels = {p[0]: p for line in (CORPUS / "provenance/difficulty.tsv").read_text().splitlines() if (p := line.split("\t"))}
    in_manifest = {r["song_id"]: r for r in json.loads((CORPUS / "manifest.json").read_text())}
    dates = json.loads((ROOT / "provenance/release-dates.json").read_text())["songs"]
    charts = []
    for song in dates:
        if song["released"] < since:
            continue
        sid = song["song_id"]
        for level, column in (("IN", 3), ("AT", 4)):
            path = f"{sid}.0/{level}.json"
            if path not in tree or path in excluded:
                assert level == "AT", "Missing IN chart: " + path
                continue
            constant = levels.get(sid, [])
            charts.append(dict(chart_id=f"{sid}:{level}", song_id=sid, title=song["title"], released=song["released"],
                               level=level, constant=float(constant[column]) if len(constant) > column else None,
                               source_path=path, git_blob_sha1=tree[path]["sha"], bytes=tree[path]["size"],
                               source_url=f'https://raw.githubusercontent.com/{lock["repository"]}/{lock["chart"]["commit"]}/' + urllib.parse.quote(path),
                               corpus_sha256=in_manifest[sid]["sha256"] if level == "IN" else None))
    return lock, charts


def load_raw(chart):
    if chart["level"] == "IN":
        raw = (CORPUS / "raw" / chart["source_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == chart["corpus_sha256"], chart["chart_id"]
        return raw
    local = ROOT / "raw" / chart["source_path"]
    raw = local.read_bytes() if local.exists() else fetch(chart["source_url"])
    assert len(raw) == chart["bytes"] and blob_sha1(raw) == chart["git_blob_sha1"], "Blob mismatch: " + chart["chart_id"]
    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(raw)
    return raw


def pure_notes(source):
    """All notes of the pure configuration, in seconds and normalized x, chronological."""
    pure = flatten(source)
    line = pure["judgeLineList"][0]
    seconds = 1.875 / line["bpm"]
    return [dict(time=n["time"] * seconds + pure["offset"], type=n["type"],
                 x=.5 + n["positionX"] / CONFIG["x_units_per_screen"],
                 duration=n["holdTime"] * seconds if n["type"] == 3 else 0.0)
            for n in line["notesAbove"]]


def groups_of(notes):
    groups = []
    for note in notes:
        if not groups or note["time"] - groups[-1][0]["time"] > EPS:
            groups.append([])
        groups[-1].append(note)
    return groups


def segments(notes):
    """Runs of simultaneous groups, broken only at pauses longer than gap_seconds."""
    runs, run = [], []
    for group in groups_of(notes):
        if run and group[0]["time"] - run[-1][0]["time"] > CONFIG["gap_seconds"]:
            runs.append(run); run = []
        run.append(group)
    if run:
        runs.append(run)
    return runs


def holds_cross(notes, t):
    return any(n["type"] == 3 and n["time"] < t - EPS and n["time"] + n["duration"] > t + EPS for n in notes)


def windows_of(notes, runs):
    """Windows start at group boundaries, about window_stride_notes apart, never inside a hold."""
    out = []
    for run in runs:
        before, last = 0, None
        for start in range(len(run)):
            if start:
                before += len(run[start - 1])
            if last is not None and before - last < CONFIG["window_stride_notes"]:
                continue
            t0 = run[start][0]["time"]
            if holds_cross(notes, t0):
                continue
            end, size = start, 0
            while end < len(run) and size + len(run[end]) <= CONFIG["maximum_notes"] and run[end][0]["time"] - t0 <= CONFIG["maximum_seconds"]:
                size += len(run[end]); end += 1
            chosen = [n for g in run[start:end] for n in g]
            if len(chosen) < CONFIG["minimum_notes"] or any(n["time"] + n["duration"] > chosen[-1]["time"] + EPS for n in chosen):
                continue
            out.append(chosen)
            last = before
    return out


def token(n, t0):
    d = CONFIG["decimals"]
    return [round(n["time"] - t0, d), n["type"], round(n["x"], d), round(n["duration"], d)]


def max_contacts(notes):
    best, active = 0, []
    for group in groups_of(notes):
        t = group[0]["time"]
        active = [n for n in active if n["time"] + n["duration"] > t + EPS]
        best = max(best, len(group) + len(active))
        active.extend(n for n in group if n["type"] == 3 and n["duration"] > 0)
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2024-01-01")
    args = parser.parse_args()
    lock, charts = select(args.since)
    songs = sorted({c["song_id"] for c in charts})
    random.Random(CONFIG["split_seed"]).shuffle(songs)
    nv, nt = round(len(songs) * CONFIG["split_fractions"]["validation"]), round(len(songs) * CONFIG["split_fractions"]["test"])
    split = {s: "validation" if i < nv else "test" if i < nv + nt else "train" for i, s in enumerate(songs)}
    out = ROOT / "processed"; (out / "charts").mkdir(parents=True, exist_ok=True)
    for stale in (out / "charts").glob("*.json.gz"):
        stale.unlink()
    rows, windows = [], []
    for i, chart in enumerate(charts):
        raw = load_raw(chart)
        source = json.loads(raw)
        notes = pure_notes(source)
        runs = segments(notes)
        chart_windows = windows_of(notes, runs)
        meta = dict(chart_id=chart["chart_id"], song_id=chart["song_id"], level=chart["level"], constant=chart["constant"],
                    released=chart["released"], split=split[chart["song_id"]], bpm=source["judgeLineList"][0]["bpm"])
        doc = dict(meta, source_sha256=hashlib.sha256(raw).hexdigest(), token_fields=["time_s", "type", "x", "hold_s"],
                   runs=[dict(start_s=round(r[0][0]["time"], 5), tokens=[token(n, 0) for g in r for n in g]) for r in runs])
        with gzip.open(out / "charts" / (chart["chart_id"].replace(":", ".") + ".json.gz"), "wt") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        for k, w in enumerate(chart_windows):
            windows.append(dict(id=f'{chart["chart_id"]}:{k}', **meta, start_s=round(w[0]["time"], 5),
                                max_contacts=max_contacts(w), tokens=[token(n, w[0]["time"]) for n in w]))
        covered = {id(n) for w in chart_windows for n in w}
        rows.append(dict(meta, notes=len(notes), runs=len(runs), windows=len(chart_windows), window_unique_notes=len(covered),
                         offscreen_x_notes=sum(not 0 <= n["x"] <= 1 for n in notes)))
        print(f'{i+1}/{len(charts)} {chart["chart_id"]} notes {len(notes)} windows {len(chart_windows)} covered {len(covered)}', flush=True)
    with gzip.open(out / "windows.json.gz", "wt") as f:
        json.dump(windows, f, ensure_ascii=False, separators=(",", ":"))
    total = lambda key, rs=rows: sum(r[key] for r in rs)
    stats = dict(config=CONFIG, since=args.since, source=lock, representation="agent-tools/pure-configuration flatten()",
                 charts=len(rows), songs=len(songs), levels=dict(collections.Counter(r["level"] for r in rows)),
                 totals={k: total(k) for k in ("notes", "windows", "window_unique_notes", "offscreen_x_notes")},
                 splits={s: dict(songs=sum(v == s for v in split.values()), charts=sum(r["split"] == s for r in rows),
                                 windows=sum(r["windows"] for r in rows if r["split"] == s),
                                 window_unique_notes=sum(r["window_unique_notes"] for r in rows if r["split"] == s))
                         for s in ("train", "validation", "test")},
                 by_level={lv: {k: total(k, [r for r in rows if r["level"] == lv]) for k in ("notes", "windows", "window_unique_notes")}
                           for lv in ("IN", "AT")},
                 window_max_contacts=dict(sorted(collections.Counter(w["max_contacts"] for w in windows).items())),
                 charts_without_windows=[r["chart_id"] for r in rows if not r["windows"]],
                 per_chart=rows)
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    (out / "splits.json").write_text(json.dumps(dict(sorted(split.items())), ensure_ascii=False, indent=2) + "\n")
    (ROOT / "manifest.json").write_text(json.dumps(charts, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in stats.items() if k not in ("per_chart", "source", "config")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
