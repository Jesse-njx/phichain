"""Run with: python3 -m unittest discover -s tools/agent-evals/tests"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
JUDGE = Path(__file__).resolve().parents[1] / "judge"
sys.path.insert(0, str(JUDGE))

from chartmodel import from_native  # noqa: E402
from l0_validity import check  # noqa: E402
from l1_detectors import analyze, two_finger_route  # noqa: E402
import l2_review  # noqa: E402

OVERRIDE = ROOT / "charts/override/override-sol-in163"
RUN02 = ROOT / "charts/happy-ending/happy-ending-guided-run02"


def native_chart(notes, events=None):
    base = [
        {"kind": k, "start_beat": [0, 0, 1], "end_beat": [100, 0, 1], "value": {"type": "constant", "value": v}}
        for k, v in (("x", 0), ("y", -270), ("rotation", 0), ("opacity", 255), ("speed", 9))
    ]
    return {"format": "6", "offset": "0.0", "bpm_list": [{"beat": [0, 0, 1], "bpm": 120.0}],
            "lines": [{"name": "L", "role": "simple", "notes": notes, "events": events if events is not None else base, "children": [], "curve_note_tracks": []}]}


def tap(beat, x):
    return {"kind": "tap", "above": True, "beat": [beat, 0, 1], "x": x, "speed": 1.0}


class Regression(unittest.TestCase):
    def test_reproduces_existing_cadence_numbers(self):
        """Same chart and definitions as override-sol-in163/performance-comparison.json."""
        expected = json.loads((OVERRIDE / "performance-comparison.json").read_text())["Override"]["coverage"]
        m = analyze(str(OVERRIDE / "export/chart.json"))["metrics"]
        self.assertAlmostEqual(m["carrier_motion_pct"], expected["carrier_motion"], delta=0.06)
        self.assertAlmostEqual(m["background_motion_pct"], expected["background_motion"], delta=0.06)
        self.assertAlmostEqual(m["any_motion_pct"], expected["motion"], delta=0.06)
        self.assertAlmostEqual(m["strong_motion_pct"], expected["strong"], delta=0.06)

    def test_native_and_exported_official_agree(self):
        """One chart, two formats: the model must not make formats look different."""
        native = analyze(str(RUN02 / "project/chart.json"))
        official = analyze(str(RUN02 / "export/chart.json"))
        self.assertEqual(native["notes"], official["notes"])
        self.assertAlmostEqual(native["span_s"], official["span_s"], delta=0.02)
        for name, tolerance in {
            "required_move_median_px": 2.0,
            "required_travel_px_per_s": 2.0,
            "approach_heights_per_s_median": 0.02,
            "fresh_onsets_per_s": 0.02,
            "carrier_motion_pct": 2.0,
            "background_motion_pct": 2.0,
        }.items():
            self.assertAlmostEqual(native["metrics"][name], official["metrics"][name], delta=tolerance, msg=name)


class Hands(unittest.TestCase):
    def test_two_stationary_lanes_require_no_travel(self):
        """Wide alternation between two fixed lanes needs no hand travel."""
        groups = [[(i * 0.1, -300 if i % 2 else 300, 0)] for i in range(40)]
        moves = [r[3] for r in two_finger_route(groups)]
        self.assertAlmostEqual(sum(moves), 0.0)

    def test_three_lanes_force_movement(self):
        groups = [[(i * 0.1, [-400, 0, 400][i % 3], 0)] for i in range(30)]
        self.assertGreater(sum(r[3] for r in two_finger_route(groups)), 0)


class L0(unittest.TestCase):
    def write(self, doc, folder):
        path = Path(folder) / "chart.json"
        path.write_text(json.dumps(doc))
        return path

    def test_valid_chart_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(check(self.write(native_chart([tap(4, 0), tap(5, 100)]), d), audio_seconds=60)["pass"])

    def test_defects_fail(self):
        cases = {
            "no_notes": native_chart([]),
            "empty_hold": native_chart([{"kind": "hold", "above": True, "beat": [4, 0, 1], "hold_beat": [0, 0, 1], "x": 0, "speed": 1.0}]),
            "notes_after_audio": native_chart([tap(90, 0)]),
            "offscreen_head": native_chart([tap(4, 5000)]),
        }
        with tempfile.TemporaryDirectory() as d:
            for code, doc in cases.items():
                result = check(self.write(doc, d), audio_seconds=10)
                self.assertIn(code, [e["code"] for e in result["errors"]], code)

    def test_finger_limit_only_applies_when_stated(self):
        doc = native_chart([tap(4, -300), tap(4, 0), tap(4, 300)])
        with tempfile.TemporaryDirectory() as d:
            path = self.write(doc, d)
            self.assertTrue(check(path, audio_seconds=60)["pass"])
            self.assertFalse(check(path, max_fingers=2, audio_seconds=60)["pass"])

    def test_overlapping_native_events_fail(self):
        row = lambda a, b: {"kind": "x", "start_beat": [a, 0, 1], "end_beat": [b, 0, 1], "value": {"type": "constant", "value": 0}}
        with tempfile.TemporaryDirectory() as d:
            result = check(self.write(native_chart([tap(4, 0)], [row(0, 10), row(5, 20)]), d), audio_seconds=60)
            self.assertIn("overlapping_event", [e["code"] for e in result["errors"]])

    def test_official_corpus_has_no_false_rejects(self):
        report = JUDGE.parent / "bands/l0-corpus.json"
        self.assertEqual(json.loads(report.read_text())["failing"], [])


class Motion(unittest.TestCase):
    def test_constant_line_has_no_motion_and_moving_line_does(self):
        notes = [tap(i, 0) for i in range(4, 30)]
        still = analyze(from_native(native_chart(notes)))["metrics"]
        self.assertEqual(still["any_motion_pct"], 0.0)
        moving = [
            {"kind": "x", "start_beat": [i, 0, 1], "end_beat": [i + 1, 0, 1], "value": {"type": "transition", "start": 0 if i % 2 else 200, "end": 200 if i % 2 else 0, "easing": {"type": "linear"}}}
            for i in range(0, 40)
        ] + [{"kind": k, "start_beat": [0, 0, 1], "end_beat": [100, 0, 1], "value": {"type": "constant", "value": v}} for k, v in (("y", -270), ("opacity", 255), ("speed", 9))]
        # Horizontal travel along a level line is not normal travel, so tilt it.
        moving.append({"kind": "rotation", "start_beat": [0, 0, 1], "end_beat": [100, 0, 1], "value": {"type": "constant", "value": 45}})
        result = analyze(from_native(native_chart(notes, moving)))["metrics"]
        self.assertGreater(result["carrier_motion_pct"], 90)


class L2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.clips = []
        for name in ("secret-candidate-one", "secret-candidate-two", "secret-official", "secret-rejected"):
            path = base / f"{name}.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1", "-f", "lavfi", "-i", "anullsrc", "-shortest", "-metadata", f"title={name}", str(path)], check=True)
            cls.clips.append(path)
        cls.manifest = base / "manifest.json"
        cls.manifest.write_text(json.dumps({"title": "Test", "clips": [
            {"id": "one", "condition": "condA", "role": "candidate", "video": cls.clips[0].name, "chart": "x.json"},
            {"id": "two", "condition": "condB", "role": "candidate", "video": cls.clips[1].name},
            {"id": "official", "role": "anchor_official", "video": cls.clips[2].name},
            {"id": "rejected", "role": "anchor_rejected", "video": cls.clips[3].name},
        ]}))
        cls.out = base / "out"
        l2_review.build(cls.manifest, cls.out, None)
        cls.sealed = json.loads((cls.out / "sealed/key.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_review_folder_leaks_nothing(self):
        for path in (self.out / "review").rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            for secret in (b"secret-", b"condA", b"condB", b"anchor_", b"candidate"):
                self.assertNotIn(secret, data, f"{secret} in {path.name}")
            self.assertNotIn("secret", path.name)

    def test_clips_keep_no_source_metadata(self):
        for clip in (self.out / "review/clips").iterdir():
            info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(clip)], capture_output=True, text=True).stdout
            self.assertNotIn("secret", info)

    def ratings(self, official_score, rejected_score):
        out = {}
        for label, clip in self.sealed["key"].items():
            score = {"official": official_score, "rejected": rejected_score, "one": 5, "two": 1}[clip["id"]]
            out[label] = {d[0]: score for d in l2_review.DIMENSIONS}
            out[label]["verdict"] = "keep" if score >= 4 else "reject"
        return {"session": self.sealed["session"], "ratings": out}

    def run_ingest(self, doc):
        path = Path(self.tmp.name) / "ratings.json"
        path.write_text(json.dumps(doc))
        return l2_review.ingest(self.out, path)

    def test_ingest_summarizes_and_flags_calibration(self):
        good = self.run_ingest(self.ratings(5, 1))
        self.assertTrue(good["calibrated"])
        self.assertEqual(good["conditions"]["condA"]["keep_rate"], 1.0)
        self.assertEqual(good["conditions"]["condB"]["reject_rate"], 1.0)
        labels = l2_review.HERE.parent / "backtest/labels.d" / f"{self.sealed['session']}.json"
        self.assertTrue(labels.exists())
        labels.unlink()
        bad = self.run_ingest(self.ratings(2, 3))
        self.assertFalse(bad["calibrated"])
        self.assertFalse(labels.exists())

    def test_wrong_session_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_ingest({"session": "other", "ratings": {}})

    def test_session_requires_both_anchors(self):
        manifest = Path(self.tmp.name) / "no-anchor.json"
        manifest.write_text(json.dumps({"clips": [{"id": "a", "role": "candidate", "video": self.clips[0].name}]}))
        with self.assertRaises(SystemExit):
            l2_review.build(manifest, Path(self.tmp.name) / "no-anchor", None)


if __name__ == "__main__":
    unittest.main()
