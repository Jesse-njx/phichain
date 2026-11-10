import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import convert


def note(kind=1, time=32, x=2, hold=0):
    return {"type": kind, "time": time, "positionX": x, "holdTime": hold,
            "speed": 99, "floorPosition": -123}


def event(start=0, end=32, a=0, b=0):
    return {"startTime": start, "endTime": end, "start": a, "end": b}


def line(bpm=120, above=None, below=None, move=None, rotation=None):
    return {"bpm": bpm, "notesAbove": above or [], "notesBelow": below or [],
            "judgeLineMoveEvents": move or [], "judgeLineRotateEvents": rotation or [],
            "judgeLineDisappearEvents": [event(a=0, b=0)], "speedEvents": []}


def chart(*lines):
    return {"formatVersion": 3, "offset": 0.125, "judgeLineList": list(lines)}


class TransformTests(unittest.TestCase):
    def test_rotated_translated_heads_and_mixed_bpm_clocks(self):
        source = chart(
            line(120, [note(time=16)], move=[event(a=.5, b=1)], rotation=[event(a=0, b=180)]),
            line(240, below=[note(3, time=64, x=-3, hold=48)]),
        )
        untouched = copy.deepcopy(source)
        result = convert.flatten(source)
        self.assertEqual(source, untouched)
        self.assertEqual(result["offset"], .125)
        self.assertEqual(len(result["judgeLineList"]), 1)
        receiver = result["judgeLineList"][0]
        self.assertEqual(receiver["notesBelow"], [])
        tap, hold = receiver["notesAbove"]
        self.assertAlmostEqual(tap["positionX"], 4.5)  # Halfway: x=.75, rotation=90.
        self.assertEqual(tap["time"], 16)
        self.assertEqual(hold["positionX"], -3)  # Below does not mirror local x.
        self.assertEqual(hold["time"], 32)
        self.assertEqual(hold["holdTime"], 24)
        self.assertEqual(hold["speed"], 2.2)
        self.assertAlmostEqual(hold["floorPosition"], 1.1)
        self.assertEqual(receiver["speedEvents"][0]["value"], 2.2)
        self.assertEqual(receiver["judgeLineMoveEvents"][0]["start2"], .25)
        self.assertEqual(receiver["judgeLineRotateEvents"][0]["start"], 0)
        self.assertEqual(receiver["judgeLineDisappearEvents"][0]["start"], 1)

    def test_stacks_types_fractional_times_and_holds_are_not_deduplicated(self):
        objects = [note(1, 4421), note(4, 4421), note(2, 4421), note(2, 4421), note(3, 4421.125, hold=112.5)]
        result = convert.flatten(chart(line(175, objects)), speed=3)
        notes = result["judgeLineList"][0]["notesAbove"]
        self.assertEqual([(n["type"], n["time"], n["holdTime"]) for n in notes],
                         [(n["type"], n["time"], n["holdTime"]) for n in objects])
        self.assertEqual([n["speed"] for n in notes], [1, 1, 1, 1, 3])
        self.assertEqual(result["numOfNotes"], 5)
        self.assertEqual(convert.flatten(result, speed=3), result)

    def test_event_boundaries_gaps_unsorted_events_and_empty_channel(self):
        timeline = convert.Timeline([event(20, 20, 4, 5), event(10, 12, 1, 3)], "test", .5)
        self.assertEqual([timeline.at(t) for t in (0, 10, 11, 12, 19, 20, 99)], [.5, 1, 2, 3, 3, 5, 5])
        self.assertEqual(convert.Timeline([], "empty", .5).at(100), .5)

    def test_empty_chart_still_has_exactly_one_line(self):
        result = convert.flatten(chart(line(), line()))
        self.assertEqual(len(result["judgeLineList"]), 1)
        self.assertEqual(result["numOfNotes"], 0)

    def test_reversed_constant_tail_is_a_step_not_an_interpolation(self):
        timeline = convert.Timeline([event(20, 10, 2, 2)], "constant tail", 0)
        self.assertEqual(timeline.at(19), 0)
        self.assertEqual(timeline.at(20), 2)
        self.assertEqual(timeline.at(50), 2)

    def test_invalid_and_unsupported_inputs_fail(self):
        invalid = [None, {"formatVersion": 1}, chart(), chart(None), chart(line(bpm=0)),
                   chart(line(above=[note(5)])), chart(line(above=[note(3)])),
                   chart(line(above=[note(time=float("nan"))])), chart(line(above=[None])),
                   chart(line(move=[event(10, 1, 0, 1)])), chart(line(rotation=[None]))]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(convert.ConversionError):
                convert.flatten(source)
        for speed in (0, -1, float("inf"), float("nan")):
            with self.subTest(speed=speed), self.assertRaises(convert.ConversionError):
                convert.flatten(chart(line()), speed)
        fake = note()
        fake["isFake"] = True
        with self.assertRaises(convert.ConversionError):
            convert.flatten(chart(line(above=[fake])))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.json"
        self.source.write_bytes(convert.json_bytes(chart(line(above=[note(), note(4)]))))

    def call(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
            status = convert.main([str(a) for a in args])
        return status, error.getvalue()

    def test_default_output_and_source_overwrite_protection(self):
        original = self.source.read_bytes()
        self.assertEqual(self.call(self.source)[0], 0)
        output = self.root / "input-pure.json"
        self.assertTrue(output.exists())
        self.assertEqual(self.call(self.source)[0], 1)
        self.assertEqual(self.call(self.source, "--force")[0], 0)
        self.assertEqual(self.call(self.source, self.source, "--force")[0], 1)
        alias = self.root / "alias.json"
        os.link(self.source, alias)
        self.assertEqual(self.call(self.source, alias, "--force")[0], 1)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.root.glob(".pure-*")), [])

    def test_json_to_pez_is_reproducible_and_copies_assets(self):
        music = self.root / "music.ogg"
        music.write_bytes(b"audio fixture")
        output = self.root / "output.pez"
        self.assertEqual(self.call(self.source, output, "--name", "Poseidon AT")[0], 0)
        original = output.read_bytes()
        self.assertEqual(self.call(self.source, output, "--name", "Poseidon AT", "--force")[0], 0)
        self.assertEqual(output.read_bytes(), original)
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("music.ogg"), music.read_bytes())
            self.assertTrue(archive.read("illustration.png").startswith(b"\x89PNG"))
            self.assertIn(b'"Poseidon AT"', archive.read("info.yml"))
            self.assertEqual(len(json.loads(archive.read("chart.json"))["judgeLineList"]), 1)

    def test_pez_preserves_metadata_assets_and_nested_chart_name(self):
        source = self.root / "original.pez"
        members = {"assets/chart.json": self.source.read_bytes(), "info.yml": b'chart: assets/chart.json\nname: Original\n',
                   "music.ogg": b"audio", "cover.png": b"cover", "extra.json": b'{"author":"credit"}'}
        with zipfile.ZipFile(source, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        original = source.read_bytes()
        output = self.root / "new.pez"
        self.assertEqual(self.call(source, output)[0], 0)
        self.assertEqual(source.read_bytes(), original)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), set(members))
            for name, data in members.items():
                if name != "assets/chart.json":
                    self.assertEqual(archive.read(name), data)
        extracted = self.root / "extracted.json"
        self.assertEqual(self.call(source, extracted)[0], 0)
        self.assertEqual(json.loads(extracted.read_text())["numOfNotes"], 2)

    def test_missing_and_ambiguous_audio_fail_without_output(self):
        output = self.root / "new.pez"
        self.assertEqual(self.call(self.source, output)[0], 1)
        self.assertFalse(output.exists())
        (self.root / "music.ogg").write_bytes(b"one")
        (self.root / "song.mp3").write_bytes(b"two")
        self.assertEqual(self.call(self.source, output)[0], 1)
        self.assertFalse(output.exists())
        self.assertEqual(self.call(self.source, output, "--music", self.root / "song.mp3")[0], 0)

    def test_ambiguous_unsafe_and_unsupported_archives_fail_without_output(self):
        output = self.root / "new.pez"
        for members in [
            {"one.json": self.source.read_bytes(), "two.json": self.source.read_bytes()},
            {"../chart.json": self.source.read_bytes()},
            {"chart.json": b'{"formatVersion":1,"judgeLineList":[]}'},
            {"chart.json": b'{"BPMList":[],"judgeLineList":[]}'},
        ]:
            source = self.root / "bad.pez"
            with zipfile.ZipFile(source, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            self.assertEqual(self.call(source, output)[0], 1)
            self.assertFalse(output.exists())

    def test_atomic_output_does_not_replace_existing_file(self):
        output = self.root / "existing.json"
        output.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            convert.write_output(output, {})
        self.assertEqual(output.read_bytes(), b"keep me")
        self.assertEqual(list(self.root.glob(".pure-*")), [])


if __name__ == "__main__":
    unittest.main()
