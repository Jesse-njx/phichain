"""Project official IN notes to one line and build intact, song-disjoint windows.

Angle means the oriented approach normal, in screen space. It is checked over
the final 250 ms, not a claim about the entire visible animation or hand comfort.
"""
import bisect
import collections
import gzip
import hashlib
import json
import math
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent
CONFIG = dict(angle_degrees=20, approach_seconds=0.25, approach_samples=6,
              x_scale=0.05625, aspect_ratio=16/9, bins=128,
              hold_x_tolerance=1/128, minimum_notes=16, maximum_notes=128,
              maximum_seconds=12, gap_seconds=2.5, split_seed=20261102)


class Events:
    def __init__(self, events, factor, component="start", version=3):
        self.events = sorted(events, key=lambda e: e["startTime"])
        self.starts = [e["startTime"] * factor for e in self.events]
        self.factor, self.component, self.version = factor, component, version

    def value(self, time):
        if not self.events:
            return 0.0
        i = max(0, bisect.bisect_right(self.starts, time)-1)
        e = self.events[i]
        if self.component == "value":
            return e["value"]
        if self.version == 1 and self.component in ("x", "y"):
            def decode(v):
                return math.floor(v/1000)/880 if self.component == "x" else (v % 1000)/530
            a, b = decode(e["start"]), decode(e["end"])
        else:
            keys = {"x": ("start", "end"), "y": ("start2", "end2")}
            ka, kb = keys.get(self.component, ("start", "end"))
            a, b = e.get(ka, 0), e.get(kb, 0)
        duration = (e["endTime"] - e["startTime"]) * self.factor
        phase = max(0, min(1, (time-self.starts[i])/duration)) if duration > 0 else 1
        return a + (b-a)*phase

    def times(self, start, end):
        lo, hi = bisect.bisect_left(self.starts, start), bisect.bisect_right(self.starts, end)
        points = [start, end]
        for e in self.events[max(0, lo-1):hi]:
            for key in ("startTime", "endTime"):
                t = e[key]*self.factor
                if start < t < end:
                    points.extend([max(start, t-1e-7), t])
        return points


def oriented_angle(rotation, above, velocity):
    angle = rotation + (0 if above else 180) + (0 if velocity > 0 else 180)
    return abs((angle+180) % 360-180)


def convert_chart(chart):
    assert chart["formatVersion"] in (1, 3)
    output = []
    for li, line in enumerate(chart["judgeLineList"]):
        factor = 1.875 / line["bpm"]
        x = Events(line["judgeLineMoveEvents"], factor, "x", chart["formatVersion"])
        y = Events(line["judgeLineMoveEvents"], factor, "y", chart["formatVersion"])
        rot = Events(line["judgeLineRotateEvents"], factor)
        speed = Events(line["speedEvents"], factor, "value")
        for side in ("notesAbove", "notesBelow"):
            for ni, note in enumerate(line[side]):
                t = note["time"]*factor
                duration = note["holdTime"]*factor if note["type"] == 3 else 0
                lateral = note["positionX"]*CONFIG["x_scale"]
                def position(at):
                    r = math.radians(rot.value(at))
                    return x.value(at)+lateral*math.cos(r), y.value(at)+lateral*math.sin(r)*CONFIG["aspect_ratio"]
                px, py = position(t)
                first = max(0, t-CONFIG["approach_seconds"])
                points = {first+(t-first)*i/(CONFIG["approach_samples"]-1) for i in range(CONFIG["approach_samples"])}
                points.update(rot.times(first, t)); points.update(speed.times(first, t))
                failures = set()
                maximum_angle = 0
                for at in sorted(points):
                    velocity = speed.value(at)*(1 if note["type"] == 3 else note.get("speed", 1))
                    if abs(velocity) < 1e-8:
                        failures.add("zero_approach_speed")
                    angle = oriented_angle(rot.value(at), side == "notesAbove", velocity)
                    maximum_angle = max(angle, maximum_angle)
                    if angle > CONFIG["angle_degrees"]+1e-6:
                        failures.add("approach_angle")
                geometry_ok = not failures
                if not (0 <= px <= 1 and 0 <= py <= 1):
                    failures.add("offscreen_contact")
                if duration > 0:
                    points = set(x.times(t, t+duration)+rot.times(t, t+duration))
                    points.update(t+duration*i/max(1, math.ceil(duration*20)) for i in range(math.ceil(duration*20)+1))
                    hold_x = [position(at)[0] for at in sorted(points)]
                    if max(abs(v-px) for v in hold_x) > CONFIG["hold_x_tolerance"]:
                        failures.add("moving_hold_not_representable")
                output.append(dict(id=f"{li}:{side}:{ni}", time=t+chart.get("offset", 0),
                                   type=note["type"], duration=duration, x=px, source_y=py,
                                   source_bpm=line["bpm"], angle_max=maximum_angle,
                                   angle_eligible=geometry_ok, exclusions=sorted(failures)))
    return sorted(output, key=lambda n: (n["time"], n["id"]))


def groups_of(notes):
    groups = []
    for note in notes:
        if not groups or abs(groups[-1][0]["time"]-note["time"]) > 1e-5:
            groups.append([])
        groups[-1].append(note)
    return groups


def intact_runs(notes):
    runs, run, active = [], [], []
    for group in groups_of(notes):
        t = group[0]["time"]
        active = [n for n in active if n["time"]+n["duration"] > t+1e-5]
        reason = None
        if any(n["exclusions"] for n in group):
            reason = "ineligible_group"
        elif any(n["exclusions"] for n in active):
            reason = "ineligible_hold_active"
        # Conservative lower-bound screens; not an official engine or comfort proof.
        fresh = [n for n in group if n["type"] in (1, 3)]
        if len(fresh)+len(active) > 2:
            reason = "fresh_hits_plus_active_holds_over_two"
        taps = [n for n in group if n["type"] == 1]
        if len(taps)>1 and min(abs(a["x"]-b["x"]) for i,a in enumerate(taps) for b in taps[i+1:]) < 2/128:
            reason = "projected_tap_collision"
        # More than two widely separated instantaneous requirements cannot be two contacts.
        locations = sorted(n["x"] for n in group+active)
        clusters = []
        for location in locations:
            if not clusters or location-clusters[-1] > 2/128:
                clusters.append(location)
        if len(clusters) > 2:
            reason = "more_than_two_separated_contacts"
        if run and t-run[-1][0]["time"] > CONFIG["gap_seconds"]:
            runs.append(run); run = []
        if reason:
            for n in group:
                n["window_exclusion"] = reason
            if run:
                runs.append(run); run = []
        else:
            run.append(group)
        active.extend(n for n in group if n["type"] == 3 and n["duration"] > 0)
    if run:
        runs.append(run)
    return runs


def make_windows(notes):
    windows = []
    for run in intact_runs(notes):
        for start in range(len(run)):
            # Starts roughly half a window apart, with no unseen hold occupancy.
            if start and sum(len(g) for g in run[:start]) % 48 >= len(run[start-1]):
                continue
            t0 = run[start][0]["time"]
            if any(n["time"] < t0-1e-5 and n["time"]+n["duration"] > t0+1e-5 for n in notes if n["type"] == 3):
                continue
            end, size = start, 0
            while end < len(run) and size+len(run[end]) <= CONFIG["maximum_notes"] and run[end][0]["time"]-t0 <= CONFIG["maximum_seconds"]:
                size += len(run[end]); end += 1
            chosen = [n for g in run[start:end] for n in g]
            if len(chosen) < CONFIG["minimum_notes"]:
                continue
            last_time = chosen[-1]["time"]
            if any(n["time"]+n["duration"] > last_time+1e-5 for n in chosen):
                continue
            windows.append(chosen)
    return windows


def main():
    manifest = json.loads((ROOT/"manifest.json").read_text())
    folder = ROOT/"processed"; folder.mkdir(exist_ok=True)
    (folder/"charts").mkdir(exist_ok=True)
    ids = sorted({r["song_id"] for r in manifest}); random.Random(CONFIG["split_seed"]).shuffle(ids)
    nval = round(len(ids)*0.1)
    splits = {song: ("validation" if i<nval else "test" if i<2*nval else "train") for i,song in enumerate(ids)}
    rows, windows_all = [], []
    for idx, record in enumerate(manifest):
        path = ROOT/record["local_path"]
        data = path.read_bytes(); assert hashlib.sha256(data).hexdigest() == record["sha256"]
        chart = json.loads(data)
        notes = convert_chart(chart)
        windows = make_windows(notes)
        used = {n["id"] for window in windows for n in window}
        split = splits[record["song_id"]]
        counts = dict(collections.Counter(reason for n in notes for reason in n["exclusions"]))
        merged = [n for n in notes if n["angle_eligible"] and "offscreen_contact" not in n["exclusions"]]
        basename = record["source_path"].split('/')[0]
        result = dict(song_id=record["song_id"], source_sha256=record["sha256"],
                      representation="single horizontal line; normalized screen-space x; absolute seconds",
                      all_note_audit=notes, merged_notes=merged)
        with gzip.open(folder/"charts"/(basename+".json.gz"), "wt") as out:
            json.dump(result, out, ensure_ascii=False, separators=(",", ":"))
        for i, window in enumerate(windows):
            windows_all.append(dict(id=f'{record["song_id"]}:{i}', song_id=record["song_id"], split=split,
                                    difficulty=float(record["constant"] or 14), bpm=chart["judgeLineList"][0]["bpm"],
                                    notes=[{k:n[k] for k in ("id", "time", "type", "duration", "x")} for n in window]))
        rows.append(dict(song_id=record["song_id"], split=split, raw=len(notes),
                         angle_retained=sum(n["angle_eligible"] for n in notes), merged=len(merged),
                         representation_eligible=sum(not n["exclusions"] for n in notes),
                         windows=len(windows), unique_window_notes=len(used), exclusions=counts))
        if (idx+1) % 25 == 0:
            print("Preprocessed", idx+1, "charts; windows", len(windows_all), flush=True)
    with gzip.open(folder/"windows.json.gz", "wt") as out:
        json.dump(windows_all, out, separators=(",", ":"))
    stats = dict(config=CONFIG, songs=len(rows), source_manifest_sha256=hashlib.sha256((ROOT/"manifest.json").read_bytes()).hexdigest(),
                 totals={key:sum(row[key] for row in rows) for key in ("raw", "angle_retained", "merged", "representation_eligible", "windows", "unique_window_notes")},
                 splits={s:dict(songs=sum(r["split"]==s for r in rows), songs_with_windows=sum(r["split"]==s and r["windows"]>0 for r in rows),
                                windows=sum(r["windows"] for r in rows if r["split"]==s), unique_notes=sum(r["unique_window_notes"] for r in rows if r["split"]==s)) for s in ("train", "validation", "test")},
                 caveat="Feasibility screens are conservative heuristics, not verified human two-finger fingering.", charts=rows)
    (folder/"stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2)+"\n")
    (folder/"splits.json").write_text(json.dumps(splits, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k:v for k,v in stats.items() if k!='charts'}, indent=2), flush=True)


if __name__ == "__main__":
    main()
