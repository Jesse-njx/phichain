#!/usr/bin/env python3
"""Convert official-v3 Phigros charts to one static receiver; Python stdlib only."""

import argparse
import bisect
import json
import math
import os
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
import zipfile
import zlib


class ConversionError(ValueError):
    pass


def number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConversionError(f"{label} must be a number")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ConversionError(f"{label} must be finite" + (" and positive" if positive else ""))
    return value


class Timeline:
    """Latest-start official linear event, clamped in gaps and after its end."""

    def __init__(self, events, label, default):
        if not isinstance(events, list):
            raise ConversionError(f"{label} must be an event array")
        self.events = []
        self.default = default
        for event in events:
            if not isinstance(event, dict):
                raise ConversionError(f"{label} contains a non-object event")
            row = tuple(number(event[k], f"{label}.{k}")
                        for k in ("startTime", "endTime", "start", "end"))
            if row[1] < row[0]:
                if row[2] != row[3]:
                    raise ConversionError(f"{label}: nonconstant event ends before it starts")
                # Some official charts contain reversed constant tails. Their
                # value is unambiguous; treat them as a step at the stated start.
                row = (row[0], row[0], row[2], row[3])
            self.events.append(row)
        self.events.sort(key=lambda row: row[0])
        self.starts = [row[0] for row in self.events]

    def at(self, time):
        index = bisect.bisect_right(self.starts, time) - 1
        if index < 0:
            return self.default
        start_time, end_time, start, end = self.events[index]
        progress = min(1, (time - start_time) / (end_time - start_time)) if end_time > start_time else 1
        return start + (end - start) * progress


def flatten(source, speed=2.2):
    """Return a new official-v3 chart; never modify the source document."""
    number(speed, "scroll speed", positive=True)
    if not isinstance(source, dict) or source.get("formatVersion") != 3:
        raise ConversionError("Only official Phigros formatVersion 3 is supported (not RPE/native/v1)")
    lines = source.get("judgeLineList")
    if not isinstance(lines, list) or not lines:
        raise ConversionError("judgeLineList must contain at least one line")
    if not all(isinstance(line, dict) for line in lines):
        raise ConversionError("judgeLineList contains a non-object line")
    bpm = number(lines[0]["bpm"], "first line BPM", positive=True)
    offset = number(source["offset"], "offset")
    notes = []
    for index, line in enumerate(lines):
        label = f"line {index}"
        line_bpm = number(line["bpm"], f"{label} BPM", positive=True)
        x = Timeline(line.get("judgeLineMoveEvents", []), f"{label} move", 0.5)
        angle = Timeline(line.get("judgeLineRotateEvents", []), f"{label} rotation", 0)
        for side in ("notesAbove", "notesBelow"):
            if not isinstance(line.get(side), list):
                raise ConversionError(f"{label}.{side} must be a note array")
            for note in line[side]:
                if not isinstance(note, dict):
                    raise ConversionError(f"{label}.{side} contains a non-object note")
                kind = note["type"]
                if type(kind) is not int or kind not in (1, 2, 3, 4):
                    raise ConversionError(f"{label}: unknown note type {kind!r}")
                if note.get("isFake") or note.get("fake"):
                    raise ConversionError(f"{label}: fake notes are not supported by official v3")
                time = number(note["time"], f"{label} note time")
                hold = number(note["holdTime"], f"{label} holdTime")
                if hold < 0 or (kind == 3 and hold <= 0):
                    raise ConversionError(f"{label}: Holds require positive duration; negative durations are invalid")
                local_x = number(note["positionX"], f"{label} positionX")
                # Official x units span 18 across the screen. All below notes
                # become above notes; their original local x is not mirrored.
                target_x = 18 * (x.at(time) - 0.5) + local_x * math.cos(math.radians(angle.at(time)))
                # Different source lines may use different BPM clocks. Preserve
                # seconds, not their unrelated local tick values.
                scale = bpm / line_bpm
                target_time = time * scale
                target_hold = hold * scale
                notes.append({
                    "type": kind, "time": number(target_time, "output time"),
                    "holdTime": number(target_hold, "output holdTime"),
                    "positionX": number(target_x, "output positionX"),
                    # Official Hold speed is absolute; other kinds use a factor.
                    "speed": speed if kind == 3 else 1.0,
                    "floorPosition": number(target_time * 1.875 / bpm * speed, "output floorPosition"),
                })
    notes.sort(key=lambda note: note["time"])  # Stable, including simultaneous stacks.
    horizon = max(1_000_000_000, max((n["time"] + n["holdTime"] + 32 for n in notes), default=0))
    constant = lambda value: [{"startTime": 0, "endTime": horizon, "start": value, "end": value}]
    return {
        "formatVersion": 3, "offset": offset, "numOfNotes": len(notes),
        "judgeLineList": [{
            "bpm": bpm, "numOfNotes": len(notes), "numOfNotesAbove": len(notes), "numOfNotesBelow": 0,
            "notesAbove": notes, "notesBelow": [],
            "judgeLineMoveEvents": [{"startTime": 0, "endTime": horizon,
                                     "start": 0.5, "end": 0.5, "start2": 0.25, "end2": 0.25}],
            "judgeLineRotateEvents": constant(0),
            "judgeLineDisappearEvents": constant(1),
            "speedEvents": [{"startTime": 0, "endTime": horizon, "value": speed, "floorPosition": 0}],
        }],
    }


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def load_input(path):
    """Return chart, archive members and chart member name; never extract a ZIP."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8-sig")), None, None
    if path.suffix.lower() != ".pez":
        raise ConversionError("Input must be an official-v3 .json or .pez")
    with zipfile.ZipFile(path) as archive:
        members = {}
        candidates = []
        for info in archive.infolist():
            name = info.filename
            if name in members or "\\" in name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                raise ConversionError(f"Unsafe or duplicate archive member: {name!r}")
            data = archive.read(info)
            members[name] = data
            if name.lower().endswith(".json"):
                try:
                    value = json.loads(data.decode("utf-8-sig"))
                except (ValueError, UnicodeError):
                    continue
                if isinstance(value, dict) and any(k in value for k in ("judgeLineList", "BPMList", "bpm_list")):
                    candidates.append((name, value))
    if len(candidates) != 1:
        raise ConversionError("PEZ must contain exactly one chart JSON; ambiguous or missing charts are not guessed")
    name, chart = candidates[0]
    return chart, members, name


def plain_background():
    """Deterministic solid 16:9 PNG, generated without imaging dependencies."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    pixels = (b"\0" + bytes((7, 13, 16)) * 16) * 9
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def find_asset(directory, stems, extensions, required=False):
    matches = [p for p in directory.iterdir() if p.is_file()
               and p.stem.lower() in stems and p.suffix.lower() in extensions]
    if len(matches) > 1:
        raise ConversionError("Ambiguous assets; specify --music/--illustration: " + ", ".join(p.name for p in matches))
    if matches:
        return matches[0]
    if required:
        raise ConversionError("PEZ output requires --music, or one sibling music/song .ogg/.mp3/.wav/.flac file")
    return None


def package_json(chart, source, music=None, illustration=None, name=None):
    music = music or find_asset(source.parent, ("music", "song"), (".ogg", ".mp3", ".wav", ".flac"), True)
    illustration = illustration or find_asset(source.parent, ("illustration", "cover"), (".png", ".jpg", ".jpeg"))
    if music.suffix.lower() not in (".ogg", ".mp3", ".wav", ".flac"):
        raise ConversionError("Music must be .ogg, .mp3, .wav or .flac")
    if illustration and illustration.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ConversionError("Illustration must be .png, .jpg or .jpeg")
    music_name = "music" + music.suffix.lower()
    image_name = "illustration" + (illustration.suffix.lower() if illustration else ".png")
    meta = {"name": name or f"{source.stem} — Pure Configuration", "level": "Pure Configuration",
            "difficulty": 0.0, "charter": "Source chart / automatic single-line adaptation", "composer": "",
            "illustrator": "" if illustration else "Plain background", "chart": "chart.json",
            "music": music_name, "illustration": image_name, "aspectRatio": 16 / 9,
            "backgroundDim": 0.6, "lineLength": 6.0, "offset": 0.0,
            "holdPartialCover": False, "tip": "One static line; source timing and note types retained. Rating not reassessed."}
    # JSON-quoted scalar values are valid YAML; no YAML parser is needed.
    info = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items()) + "\n"
    return {"chart.json": json_bytes(chart), "info.yml": info.encode("utf-8"),
            music_name: music.read_bytes(), image_name: illustration.read_bytes() if illustration else plain_background()}


def write_output(output, chart, members=None, force=False):
    """Build completely before publishing; existing outputs require explicit --force."""
    descriptor, temporary = tempfile.mkstemp(prefix=".pure-", dir=output.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if members is None:
                handle.write(json_bytes(chart))
            else:
                with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in sorted(members.items()):
                        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        archive.writestr(entry, data)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temp, output)
        else:
            os.link(temp, output)  # Atomic no-clobber, including a racing writer.
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Official-v3 .json or .pez")
    parser.add_argument("output", nargs="?", type=Path, help=".json or .pez; default: <input>-pure.<same extension>")
    parser.add_argument("--music", type=Path, help="Audio for JSON → PEZ; otherwise auto-find music/song beside input")
    parser.add_argument("--illustration", type=Path, help="Cover for JSON → PEZ; otherwise auto-find or use a plain PNG")
    parser.add_argument("--name", help="Title for JSON → PEZ; existing PEZ metadata is preserved")
    parser.add_argument("--speed", type=float, default=2.2, help="Constant official scroll speed (default: 2.2)")
    parser.add_argument("--force", action="store_true", help="Replace an existing output, never an input/asset")
    args = parser.parse_args(argv)
    source = args.input.resolve()
    output = args.output or source.with_name(source.stem + "-pure" + source.suffix.lower())
    try:
        if output.suffix.lower() not in (".json", ".pez"):
            raise ConversionError("Output must end in .json or .pez")
        protected = [source, args.music, args.illustration]
        # Protect auto-discovered assets too, even if --force is given.
        protected.extend(p for p in source.parent.iterdir() if p.suffix.lower() in (".ogg", ".mp3", ".wav", ".flac", ".png", ".jpg", ".jpeg"))
        for path in filter(None, protected):
            if output.resolve() == path.resolve() or (output.exists() and path.exists() and output.samefile(path)):
                raise ConversionError("Output cannot replace the source or an audio/illustration asset")
        if output.exists() and not args.force:
            raise ConversionError(f"Output already exists: {output}; use --force to replace it")
        source_chart, members, chart_name = load_input(source)
        chart = flatten(source_chart, args.speed)
        if (args.music or args.illustration or args.name) and not (members is None and output.suffix.lower() == ".pez"):
            raise ConversionError("--music, --illustration and --name apply only to JSON → PEZ")
        if output.suffix.lower() == ".json":
            members = None
        elif members is None:
            members = package_json(chart, source, args.music, args.illustration, args.name)
        else:
            members[chart_name] = json_bytes(chart)
        write_output(output, chart, members, args.force)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    notes = chart["judgeLineList"][0]["notesAbove"]
    print(f"{output}: {len(notes)} notes, exactly 1 static line, scroll speed {args.speed:g}")
    print("Source timing/types retained; vertical separation and moving Hold contacts flattened.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
