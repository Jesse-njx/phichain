"""Format-neutral chart model for the judgement layers. Standard library only.

Loads native PhiChain charts (`format` + `lines`) and official Phigros charts
(`formatVersion` + `judgeLineList`) into one representation:

- time is in seconds
- screen coordinates are normalized, x and y in 0..1, y up
- opacity is 0..1
- note x is in fractions of the screen width from the line pivot

Native canvas is 1350x900, centred. The official importer's positionX/18 equals
native x/1350, so note offsets are directly comparable across formats.
"""
from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
import json
import math
from pathlib import Path

CANVAS_W = 1350.0
CANVAS_H = 900.0
KINDS = {1: "tap", 2: "drag", 3: "hold", 4: "flick"}


def ease(name, u):
    u = max(0.0, min(1.0, u))
    if name in (None, "linear"):
        return u
    family = name.split("_")[-1]

    def incoming(v):
        if family == "sine":
            return 1 - math.cos(v * math.pi / 2)
        if family in ("quad", "cubic", "quart", "quint"):
            return v ** {"quad": 2, "cubic": 3, "quart": 4, "quint": 5}[family]
        if family == "expo":
            return 0.0 if v == 0 else 2 ** (10 * v - 10)
        if family == "circ":
            return 1 - math.sqrt(max(0.0, 1 - v * v))
        if family == "back":
            return 2.70158 * v ** 3 - 1.70158 * v * v
        if family == "elastic":
            return v if v in (0, 1) else -(2 ** (10 * v - 10)) * math.sin((v * 10 - 10.75) * 2 * math.pi / 3)
        if family == "bounce":
            q = 1 - v
            if q < 1 / 2.75:
                z = 7.5625 * q * q
            elif q < 2 / 2.75:
                q -= 1.5 / 2.75
                z = 7.5625 * q * q + 0.75
            elif q < 2.5 / 2.75:
                q -= 2.25 / 2.75
                z = 7.5625 * q * q + 0.9375
            else:
                q -= 2.625 / 2.75
                z = 7.5625 * q * q + 0.984375
            return 1 - z
        raise ValueError(f"unsupported easing {name}")

    if name.startswith("ease_in_out_"):
        return incoming(u * 2) / 2 if u < 0.5 else 1 - incoming(2 - 2 * u) / 2
    if name.startswith("ease_out_"):
        return 1 - incoming(1 - u)
    if name.startswith("ease_in_"):
        return incoming(u)
    raise ValueError(f"unsupported easing {name}")


class Channel:
    """Piecewise channel. Before the first event and in gaps it holds the nearest earlier value."""

    def __init__(self, rows, default=0.0):
        self.rows = sorted(rows, key=lambda r: r[0])
        self.starts = [r[0] for r in self.rows]
        self.default = default

    def at(self, t):
        if not self.rows:
            return self.default
        i = bisect_right(self.starts, t) - 1
        if i < 0:
            return self.rows[0][2]
        a, b, x, y, e = self.rows[i]
        if t >= b or b <= a:
            return y
        return x + (y - x) * ease(e, (t - a) / (b - a))


@dataclass
class Note:
    t: float
    end: float
    kind: str
    x: float  # fraction of screen width from the pivot
    above: bool
    speed: float
    line: int
    beat: float = 0.0


@dataclass
class Line:
    index: int
    name: str
    x: Channel
    y: Channel
    r: Channel
    a: Channel
    v: Channel
    notes: list = field(default_factory=list)

    def pose(self, t):
        return self.x.at(t), self.y.at(t), self.r.at(t), max(0.0, min(1.0, self.a.at(t)))

    def head(self, note):
        """Normalized screen position of a note head at its judgment time."""
        x, y, r, _ = self.pose(note.t)
        rad = math.radians(r)
        return x + note.x * math.cos(rad), y + note.x * (CANVAS_W / CANVAS_H) * math.sin(rad)


@dataclass
class Chart:
    source: str
    format: str
    lines: list
    beat_seconds: object
    raw: dict

    @property
    def notes(self):
        return sorted((n for l in self.lines for n in l.notes), key=lambda n: n.t)


def beat_value(triple):
    whole, num, den = triple
    return float(whole + Fraction(int(num), int(den))) if den else float(whole)


def native_clock(bpm_list):
    rows = sorted(((beat_value(r["beat"]), float(r["bpm"])) for r in bpm_list), key=lambda r: r[0])
    points = []
    seconds = 0.0
    for i, (beat, bpm) in enumerate(rows):
        if i:
            seconds += (beat - rows[i - 1][0]) * 60 / rows[i - 1][1]
        points.append((beat, seconds, bpm))
    starts = [p[0] for p in points]

    def to_seconds(beat):
        b, s, bpm = points[max(0, bisect_right(starts, beat) - 1)]
        return s + (beat - b) * 60 / bpm

    return to_seconds


def from_native(doc, source=""):
    clock = native_clock(doc["bpm_list"])
    lines = []

    def visit(raw):
        rows = {k: [] for k in ("x", "y", "rotation", "opacity", "speed")}
        for ev in raw.get("events", []):
            if ev["kind"] not in rows:
                continue
            a, b = clock(beat_value(ev["start_beat"])), clock(beat_value(ev["end_beat"]))
            val = ev["value"]
            if val["type"] == "constant":
                start = end = float(val["value"])
                easing = None
            else:
                start, end = float(val["start"]), float(val["end"])
                easing = val.get("easing", {}).get("type")
                # Non-standard easings (custom, steps, ...) are approximated as linear.
                if not (isinstance(easing, str) and easing.startswith("ease_")):
                    easing = None
            rows[ev["kind"]].append((a, b, start, end, easing))

        def norm(key, f):
            return [(a, b, f(s), f(e), z) for a, b, s, e, z in rows[key]]

        index = len(lines)
        line = Line(
            index,
            raw.get("name", ""),
            Channel(norm("x", lambda v: v / CANVAS_W + 0.5), 0.5),
            Channel(norm("y", lambda v: v / CANVAS_H + 0.5), 0.5),
            Channel(norm("rotation", float), 0.0),
            Channel(norm("opacity", lambda v: v / 255), 0.0),
            # Official speed = native speed * 2/9 (phichain-format from_phichain.rs).
            Channel(norm("speed", lambda v: v * 2 / 9), 10.0 * 2 / 9),
        )
        for n in raw.get("notes", []):
            beat = beat_value(n["beat"])
            hold = n.get("hold_beat")
            t = clock(beat)
            end = clock(beat + beat_value(hold)) if hold else t
            line.notes.append(Note(t, end, n["kind"], float(n["x"]) / CANVAS_W, bool(n.get("above", True)), float(n.get("speed", 1.0)), index, beat))
        lines.append(line)
        for child in raw.get("children", []):
            visit(child)

    for raw in doc["lines"]:
        visit(raw)
    return Chart(source, "native", lines, clock, doc)


def from_official(doc, source=""):
    version = doc.get("formatVersion", 3)
    lines = []
    for index, raw in enumerate(doc["judgeLineList"]):
        fac = 1.875 / raw["bpm"]
        xs, ys, rs, als, vs = [], [], [], [], []
        for e in raw.get("judgeLineMoveEvents", []):
            a, b = max(-1.0, e["startTime"] * fac), e["endTime"] * fac
            s, t = e["start"], e["end"]
            if version == 1:
                xs.append((a, b, math.floor(s / 1000 + 0.5) / 880, math.floor(t / 1000 + 0.5) / 880, None))
                ys.append((a, b, (s % 1000) / 530, (t % 1000) / 530, None))
            else:
                xs.append((a, b, s, t, None))
                ys.append((a, b, e.get("start2", 0.0), e.get("end2", 0.0), None))
        for e in raw.get("judgeLineRotateEvents", []):
            rs.append((max(-1.0, e["startTime"] * fac), e["endTime"] * fac, e["start"], e["end"], None))
        for e in raw.get("judgeLineDisappearEvents", []):
            als.append((max(-1.0, e["startTime"] * fac), e["endTime"] * fac, e["start"], e["end"], None))
        for e in raw.get("speedEvents", []):
            vs.append((max(-1.0, e["startTime"] * fac), e["endTime"] * fac, e["value"], e["value"], None))
        line = Line(index, f"L{index}", Channel(xs, 0.5), Channel(ys, 0.5), Channel(rs), Channel(als), Channel(vs, 1.0))
        for above, key in ((True, "notesAbove"), (False, "notesBelow")):
            for n in raw.get(key, []):
                t = n["time"] * fac
                line.notes.append(Note(t, (n["time"] + n.get("holdTime", 0)) * fac, KINDS[n["type"]], n["positionX"] / 18, above, n.get("speed", 1.0), index))
        lines.append(line)
    return Chart(source, "official", lines, None, doc)


def load(path):
    path = Path(path)
    doc = json.loads(path.read_text())
    if "judgeLineList" in doc:
        return from_official(doc, str(path))
    if "lines" in doc and "bpm_list" in doc:
        return from_native(doc, str(path))
    raise ValueError(f"{path}: unrecognized chart format")
