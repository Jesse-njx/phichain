"""L0: is this a structurally valid, physically possible chart?

Errors are objective defects and fail the candidate. Warnings are review prompts.
Passing L0 says nothing about quality.

Calibration: every error rule must pass the 327 official IN charts (calibrate_l0.py).
Official charts really do contain duplicate notes, up to 9 simultaneous obligations and
a few heads judged on lines parked off screen (at most 3.76% of a chart's notes), so
those cannot be universal errors. Finger limits apply only when a brief states one.
"""
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys

from chartmodel import load

KINDS = {"tap", "drag", "hold", "flick"}
EPS = 1e-6
CHORD_S = 0.005
MAX_OFFSCREEN_SHARE = 0.05  # Official maximum is 3.76%.


def media_seconds(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def find_audio(chart_path):
    folder = Path(chart_path).parent
    for name in ("music.ogg", "music.mp3", "music.wav", "song.ogg", "song.mp3"):
        if (folder / name).exists():
            return folder / name
    return None


def max_contacts(notes):
    """Simultaneous finger obligations. Taps and flicks occupy an instant, Holds their span.

    Drags are excluded: a Drag can be collected by a finger already on the path.
    """
    edges = []
    for n in notes:
        if n.kind == "drag":
            continue
        edges.append((n.t - CHORD_S / 2, 1))
        edges.append((max(n.end, n.t + CHORD_S / 2), -1))
    edges.sort(key=lambda e: (e[0], e[1]))
    now = peak = 0
    for _, delta in edges:
        now += delta
        peak = max(peak, now)
    return peak


def check(path, max_fingers=None, audio_seconds=None):
    errors, warnings = [], []

    def err(code, detail):
        errors.append({"code": code, "detail": detail})

    def warn(code, detail, count=1):
        warnings.append({"code": code, "detail": detail, "count": count})

    try:
        chart = load(path)
    except Exception as exc:  # A chart that cannot load is the L0 result, not a crash.
        return {"pass": False, "errors": [{"code": "unloadable", "detail": repr(exc)}], "warnings": [], "stats": {}}

    notes = chart.notes
    if not notes:
        err("no_notes", "chart has no notes")

    channels = ("x", "y", "r", "a", "v")
    event_count = 0
    for line in chart.lines:
        for key in channels:
            rows = getattr(line, key).rows
            event_count += len(rows)
            for i, (a, b, s, e, _) in enumerate(rows):
                if not all(math.isfinite(v) for v in (a, b, s, e)):
                    err("non_finite_event", f"line {line.index} {key} row {i}")
                # Extracted official data has some of these; native output must not.
                report = err if chart.format == "native" else warn
                if b < a - EPS:
                    report("reversed_event", f"line {line.index} {key} at {a:.3f}s")
                if i and a < rows[i - 1][1] - 1e-4:
                    report("overlapping_event", f"line {line.index} {key} at {a:.3f}s")

    seen = Counter()
    offscreen = hidden = 0
    for line in chart.lines:
        for n in line.notes:
            if n.kind not in KINDS:
                err("bad_note_kind", n.kind)
            if not all(math.isfinite(v) for v in (n.t, n.end, n.x, n.speed)):
                err("non_finite_note", f"line {line.index} at {n.t}")
                continue
            if n.t < -EPS:
                err("negative_note_time", f"line {line.index} at {n.t:.3f}s")
            if n.kind == "hold" and n.end <= n.t + EPS:
                err("empty_hold", f"line {line.index} at {n.t:.3f}s")
            if n.kind != "hold" and n.end > n.t + EPS:
                err("duration_on_non_hold", f"line {line.index} at {n.t:.3f}s")
            seen[(line.index, round(n.t, 4), round(n.x, 5), n.kind, n.above)] += 1
            hx, hy = line.head(n)
            if not (-0.02 <= hx <= 1.02 and -0.02 <= hy <= 1.02):
                offscreen += 1
            if line.a.at(n.t) <= 0.01:
                hidden += 1
    dupes = sum(c - 1 for c in seen.values() if c > 1)
    if dupes:
        warn("duplicate_notes", f"{dupes} exact duplicates", dupes)
    if offscreen:
        detail = f"{offscreen} of {len(notes)} note heads judged outside the screen"
        if offscreen / len(notes) > MAX_OFFSCREEN_SHARE:
            err("offscreen_head", detail)
        else:
            warn("offscreen_head", detail, offscreen)
    if hidden:
        warn("hidden_carrier_hit", "notes judged on a line at opacity <= 1%; deliberate in some official charts", hidden)

    contacts = max_contacts(notes)
    if max_fingers is not None and contacts > max_fingers:
        err("too_many_contacts", f"{contacts} simultaneous obligations, limit {max_fingers}")
    elif contacts > 4:
        warn("many_contacts", f"{contacts} simultaneous obligations")

    last = max((n.end for n in notes), default=0.0)
    if audio_seconds is None:
        audio = find_audio(path)
        audio_seconds = media_seconds(audio) if audio else None
    if audio_seconds is None:
        warn("audio_unchecked", "no audio found beside the chart; note range not checked against it")
    elif last > audio_seconds + 0.05:
        err("notes_after_audio", f"last contact {last:.3f}s, audio {audio_seconds:.3f}s")

    if chart.format == "native":
        for line in chart.lines:
            if line.notes and not line.v.rows:
                warn("no_speed_event", f"line {line.index} carries notes without speed events")

    return {
        "pass": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "format": chart.format,
            "lines": len(chart.lines),
            "events": event_count,
            "notes": len(notes),
            "kinds": dict(Counter(n.kind for n in notes)),
            "max_contacts": contacts,
            "last_contact_s": round(last, 3),
            "audio_s": audio_seconds,
        },
    }


if __name__ == "__main__":
    result = check(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["pass"] else 1)
