import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_dataset import CONFIG, max_contacts, pure_notes, segments, token, windows_of  # noqa: E402

UNIT = 1.875 / 120  # seconds per official time unit at 120 BPM


def fixture(count=60):
    return {"formatVersion": 3, "offset": 0, "judgeLineList": [{
        "bpm": 120, "judgeLineMoveEvents": [{"startTime": 0, "endTime": 99999, "start": .5, "end": .5, "start2": .2, "end2": .2}],
        "judgeLineRotateEvents": [{"startTime": 0, "endTime": 99999, "start": 0, "end": 0}],
        "judgeLineDisappearEvents": [{"startTime": 0, "endTime": 99999, "start": 1, "end": 1}],
        "speedEvents": [{"startTime": 0, "endTime": 99999, "value": 1}],
        "notesAbove": [{"type": 1, "time": 32 + i * 16, "positionX": (-3 if i % 2 else 3), "holdTime": 0, "speed": 1, "floorPosition": 0}
                       for i in range(count)],
        "notesBelow": []}]}


class PureNoteTests(unittest.TestCase):
    def test_every_note_kept_including_rotated_and_below(self):
        source = fixture()
        line = source["judgeLineList"][0]
        line["judgeLineRotateEvents"][0].update(start=60, end=60)
        line["notesBelow"] = [dict(line["notesAbove"][0], time=40)]
        notes = pure_notes(source)
        self.assertEqual(len(notes), 61)
        self.assertAlmostEqual(notes[0]["x"], .5 + 3 * .5 / 18)  # cos 60 = .5
        self.assertAlmostEqual(notes[0]["time"], 32 * UNIT)

    def test_hold_seconds_and_line_bpm(self):
        source = fixture(20)
        source["judgeLineList"][0]["notesAbove"][0].update(type=3, holdTime=64)
        notes = pure_notes(source)
        self.assertAlmostEqual(notes[0]["duration"], 64 * UNIT)
        self.assertEqual(notes[1]["duration"], 0)

    def test_pause_breaks_run(self):
        source = fixture(); line = source["judgeLineList"][0]["notesAbove"]
        for note in line[30:]:
            note["time"] += 256  # 4 s
        self.assertEqual(len(segments(pure_notes(source))), 2)

    def test_dense_chords_kept(self):
        source = fixture(); line = source["judgeLineList"][0]["notesAbove"]
        line += [dict(line[10], positionX=0), dict(line[10], positionX=-6), dict(line[10])]
        notes = pure_notes(source)
        runs = segments(notes)
        self.assertEqual(len(runs), 1)
        self.assertEqual(max_contacts(notes), 4)


class WindowTests(unittest.TestCase):
    def test_windows_never_cut_holds_and_respect_limits(self):
        source = fixture(200); line = source["judgeLineList"][0]["notesAbove"]
        for i in range(0, 200, 7):
            line[i].update(type=3, holdTime=40)
        notes = pure_notes(source)
        windows = windows_of(notes, segments(notes))
        self.assertTrue(windows)
        for w in windows:
            self.assertTrue(CONFIG["minimum_notes"] <= len(w) <= CONFIG["maximum_notes"])
            self.assertLessEqual(w[-1]["time"] - w[0]["time"], CONFIG["maximum_seconds"] + 1e-9)
            self.assertTrue(all(n["time"] + n["duration"] <= w[-1]["time"] + 1e-5 for n in w))
            t0 = w[0]["time"]
            self.assertFalse(any(n["type"] == 3 and n["time"] < t0 - 1e-5 and n["time"] + n["duration"] > t0 + 1e-5 for n in notes))

    def test_token(self):
        notes = pure_notes(fixture())
        tok = token(notes[3], notes[0]["time"])
        self.assertEqual(len(tok), 4)
        self.assertAlmostEqual(tok[0], 48 * UNIT, places=5)
        self.assertEqual(tok[1], 1)
        self.assertAlmostEqual(tok[2], .5 - 3 / 18, places=5)


if __name__ == "__main__":
    unittest.main()
