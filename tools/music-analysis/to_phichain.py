#!/usr/bin/env python3
"""Visualize analysis JSON in an EMPTY live PhiChain project via existing MCP tools."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
LAYERS = {
    "low_percussive": "Low percussion", "mid_percussive": "Mid percussion",
    "high_percussive": "High percussion", "harmonic_texture": "Harmonic texture",
    "tonal_ridge": "Tonal ridge", "drums": "Drums estimate", "bass": "Bass estimate",
    "vocals": "Vocals estimate", "other": "Other stem",
}
REASONS = {
    "attack": "Attack evidence", "coincident": "Coincident layers",
    "repeated": "Repeated layer activity", "prominent": "Prominent local layer",
    "sustain": "Sustain / hold evidence", "pitch_change": "Tonal change",
    "other": "Other / unclassified reason",
}


def reason_groups(note):
    groups = set()
    for reason in note.get("reasons", []):
        if reason.startswith("Omitted:"):
            continue
        key = ("attack" if reason == "Audible-attack evidence" else
               "coincident" if reason.startswith("Coincident evidence:") else
               "repeated" if reason == "Repeated activity in this acoustic layer" else
               "prominent" if reason.startswith("Prominent acoustic layer") else
               "sustain" if reason.startswith("Stable dominant tonal ridge") else
               "pitch_change" if reason.startswith("Dominant tonal-ridge change") else "other")
        groups.add(key)
    return sorted(groups, key=list(REASONS).index) or ["other"]


def finite(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite in [{low}, {high}]")
    return value


def read_analysis(path):
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != 1:
        raise ValueError("Expected analysis schema_version 1")
    duration = finite(data["source"]["duration_seconds"], "duration", .1, 1200)
    seen, selected = set(), []
    for note in data["decisions"]:
        if not isinstance(note.get("id"), str) or note["id"] in seen:
            raise ValueError("Duplicate or missing decision ID")
        seen.add(note["id"])
        if not isinstance(note.get("selected"), bool):
            raise ValueError("selected must be boolean")
        if not note["selected"]:
            continue
        t = finite(note["time_seconds"], "time", 0, duration)
        end = finite(note["end_seconds"], "end", t, duration)
        finite(note["intensity"], "intensity", 0, 100)
        if t >= duration or note["suggested_type"] not in ("tap", "hold"):
            raise ValueError("Invalid note type or time")
        if note["suggested_type"] == "hold" and end <= t:
            raise ValueError("Hold end must follow start")
        if note.get("layer") not in LAYERS or not isinstance(note.get("reasons"), list) or not all(isinstance(r, str) for r in note["reasons"]):
            raise ValueError("Unknown layer or invalid reasons")
        selected.append(note)
    if not selected:
        raise ValueError("Analysis contains no selected decisions")
    data = {**data, "selected_notes": sorted(selected, key=lambda n: (n["time_seconds"], n["id"]))}
    for region in data.get("climax_regions", []):
        start = finite(region["start_seconds"], "climax start", 0, duration)
        end = finite(region["end_seconds"], "climax end", start, duration)
        if end <= start:
            raise ValueError("Climax must have a positive duration")
    return data


def summary(data):
    notes = data["selected_notes"]
    reasons = Counter(key for n in notes for key in reason_groups(n))
    layers = Counter(n["layer"] for n in notes)
    return {"selected_decisions": len(notes), "layers": dict(layers), "reason_categories": dict(reasons),
            "layer_tracks": len(layers), "reason_tracks": len(reasons),
            "reason_view_objects": sum(reasons.values()),
            "reason_view_note": "Multi-label diagnostic view: one decision appears once in each applicable reason track."}


def beat_number(beat):
    return beat[0] + beat[1] / beat[2]


def beat_array(value):
    value = Fraction(round(value * 10000), 10000)
    whole = math.floor(value)
    part = value - whole
    return [whole, part.numerator, part.denominator]


def audio_to_beat(seconds, bpm_list, offset_ms):
    remaining = seconds - offset_ms / 1000
    if remaining < 0:
        return remaining * bpm_list[0]["bpm"] / 60
    for index, point in enumerate(bpm_list):
        start = beat_number(point["beat"])
        end = beat_number(bpm_list[index + 1]["beat"]) if index + 1 < len(bpm_list) else math.inf
        length = (end - start) * 60 / point["bpm"]
        if remaining <= length:
            return start + remaining * point["bpm"] / 60
        remaining -= length
    raise ValueError("Invalid BPM map")


def plan(data, context, group_by):
    notes = data["selected_notes"]
    catalog = LAYERS if group_by == "layer" else REASONS
    groups = {n["layer"] for n in notes} if group_by == "layer" else {g for n in notes for g in reason_groups(n)}
    keys = [k for k in catalog if k in groups]
    if len(keys) > 6:
        raise ValueError("More than six tracks would overlap at native note width; use layer grouping")
    pitch = 1200 / len(keys)
    spread = min(45, max(0, (pitch - 180) / 2))
    tracks = [{"key": key, "name": f"{i + 1:02} / {catalog[key]} / intensity L>R",
               "center": (i - (len(keys) - 1) / 2) * pitch} for i, key in enumerate(keys)]
    convert = lambda t: audio_to_beat(t, context["bpm_list"], context["offset"])
    rows = []
    for n in notes:
        for group in [n["layer"]] if group_by == "layer" else reason_groups(n):
            start = convert(n["time_seconds"])
            end = convert(n["end_seconds"])
            rows.append({"decision_id": n["id"], "track": keys.index(group),
                         "kind": n["suggested_type"], "beat": beat_array(start),
                         "hold_beat": beat_array(end - start), "x": round((n["intensity"] - 50) / 50 * spread, 4)})
    # Only the shared judgment line brightens in climax regions. No extra notes
    # or score objects are used for section indication.
    duration = data["source"]["duration_seconds"]
    points = sorted({0.0, duration, *(r[k] for r in data.get("climax_regions", []) for k in ("start_seconds", "end_seconds"))})
    opacity = []
    for a, b in zip(points, points[1:]):
        high = any(r["start_seconds"] <= (a + b) / 2 < r["end_seconds"] for r in data.get("climax_regions", []))
        opacity.append({"start": beat_array(convert(a)), "end": beat_array(convert(b)), "value": 230 if high else 65})
    if len(rows) + len(tracks) * 5 + len(opacity) > 19000:
        raise ValueError("Visualization exceeds the live editor object limit")
    return {"tracks": tracks, "rows": rows, "opacity": opacity,
            "range_start": beat_array(min(0, convert(0))), "range_end": beat_array(convert(duration) + 4),
            "intensity_spread": spread, "group_by": group_by}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_target(data, context, expected_project):
    if Path(context.get("project_path", "")).resolve() != Path(expected_project).resolve():
        raise ValueError("Open project differs from --project; no edits made")
    if context.get("note_count") != 0 or len(context.get("lines", [])) > 1:
        raise ValueError("Open a NEW EMPTY experiment project (at most one default line). Existing work is never replaced")
    music = Path(context.get("music_path") or "")
    expected_hash = data["source"].get("decoded_sha256") or data["source"]["sha256"]
    if not music.is_file() or digest(music) != expected_hash:
        raise ValueError("Project music does not match the analysis PCM. Create the experiment using the analysis folder's audio.wav")
    if abs(context["audio_duration_seconds"] - data["source"]["duration_seconds"]) > .01:
        raise ValueError("Live audio duration differs from analysis")


def execute(data, endpoint, project, group_by, apply=False, save=False, title=None, bridge=None, adapter=None):
    if bridge is None:
        sys.path.insert(0, str(ROOT / "tools/phichain-mcp"))
        import server
        from agent_server import AgentServer
        bridge = lambda name, args: server.call_editor(endpoint, name, args)
        adapter = AgentServer(endpoint)
    def checked(response):
        if "error" in response:
            raise ValueError(str(response["error"]))
        return response
    context = checked(bridge("get_context", {}))
    check_target(data, context, project)
    guards = {k: context[k] for k in ("session", "revision")}
    checked(adapter.execute("chart_templates", {}))
    snapshot = checked(bridge("authoring_read", guards))
    if snapshot["document"]["notes"] or snapshot["document"]["curve_tracks"]:
        raise ValueError("Live project contains authored objects")
    prepared = plan(data, context, group_by)
    prepared["title"] = title or f"Audio analysis / {group_by}"
    args = {**guards, "source": Path(__file__).with_name("visualize.js").read_text(),
            "input": prepared, "dry_run": True, "label": f"Visualize audio analysis by {group_by}"}
    dry_run = checked(adapter.execute("chart_script", args))
    receipt = {"analysis_id": data["analysis_id"], "analysis_source_sha256": data["source"]["sha256"],
               "project_path": str(Path(project).resolve()), "group_by": group_by,
               "summary": summary(data), "tracks": prepared["tracks"],
               "intensity_x_range": [-prepared["intensity_spread"], prepared["intensity_spread"]],
               "dry_run": dry_run, "applied": False}
    if not apply:
        return receipt
    latest = checked(bridge("get_context", {}))
    check_target(data, latest, project)
    if any(latest[k] != guards[k] for k in guards):
        raise ValueError("Editor changed after dry run; no commit attempted. Rerun from fresh state")
    commit = checked(adapter.execute("chart_script", {**args, "dry_run": False}))
    receipt.update(applied=True, commit=commit)
    current = checked(bridge("get_context", {}))
    if current["session"] != guards["session"] or current["revision"] != commit["revision"] or current["note_count"] != len(prepared["rows"]) or len(current["lines"]) != len(prepared["tracks"]):
        raise ValueError("Commit returned, but verification differs. Inspect live state before retrying; do not duplicate the import")
    created = commit.get("created_ids", {})
    receipt["note_index"] = [{"native_note_id": created.get(f"new:viz_note:{i}"),
                              "decision_id": row["decision_id"], "track": prepared["tracks"][row["track"]]["key"]}
                             for i, row in enumerate(prepared["rows"])]
    receipt["decisions"] = {n["id"]: {k: n[k] for k in ("time_seconds", "end_seconds", "intensity", "layer", "reasons", "suggested_type")}
                            for n in data["selected_notes"]}
    receipt["verified_context"] = current
    if save:
        receipt["save"] = checked(bridge("save", {k: current[k] for k in guards}))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--summary", action="store_true", help="Count layer/reason tracks without contacting the editor")
    parser.add_argument("--group-by", choices=("layer", "reason"), default="layer")
    parser.add_argument("--endpoint", type=Path)
    parser.add_argument("--project", type=Path, help="Exact expected path of the EMPTY live experiment project")
    parser.add_argument("--title")
    parser.add_argument("--apply", action="store_true", help="Validate, then commit as one undo entry")
    parser.add_argument("--save", action="store_true", help="Save the imported live project; requires --apply")
    parser.add_argument("--receipt", type=Path, help="New JSON evidence/index file; required for --apply")
    args = parser.parse_args()
    try:
        data = read_analysis(args.analysis)
        if args.summary:
            print(json.dumps(summary(data), indent=2)); return
        if not args.endpoint or not args.project:
            raise ValueError("Supply --endpoint and --project, or use --summary")
        if args.save and not args.apply:
            raise ValueError("--save requires --apply")
        if args.apply and not args.receipt:
            raise ValueError("--apply requires --receipt to retain native-ID evidence")
        if args.receipt and args.receipt.exists():
            raise ValueError("Receipt already exists; choose a new file")
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
        result = execute(data, args.endpoint, args.project, args.group_by, args.apply, args.save, args.title)
        if args.receipt:
            args.receipt.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({k: result[k] for k in ("applied", "project_path", "group_by", "summary", "tracks")}, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Visualization stopped: {error}\n")


if __name__ == "__main__":
    main()
