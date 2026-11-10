import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import to_phichain as v


def fixture():
    return {"schema_version": 1, "analysis_id": "demo", "source": {"sha256": "mp3", "decoded_sha256": "wav", "duration_seconds": 10},
            "decisions": [
                {"id": "n1", "selected": True, "time_seconds": 1.12345, "end_seconds": 1.12345,
                 "suggested_type": "tap", "layer": "low_percussive", "intensity": 0,
                 "reasons": ["Audible-attack evidence", "Coincident evidence: low_percussive, harmonic_texture"]},
                {"id": "n2", "selected": True, "time_seconds": 2, "end_seconds": 4,
                 "suggested_type": "hold", "layer": "harmonic_texture", "intensity": 100,
                 "reasons": ["Audible-attack evidence", "Stable dominant tonal ridge supports a provisional hold; tail needs listening review"]},
                {"id": "n3", "selected": False, "time_seconds": 5, "end_seconds": 5,
                 "suggested_type": "tap", "layer": "high_percussive", "intensity": 50,
                 "reasons": ["Omitted: below selection priority threshold"]}],
            "climax_regions": [{"start_seconds": 3, "end_seconds": 6}]}


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "analysis.json"
        self.path.write_text(json.dumps(fixture()))
        self.data = v.read_analysis(self.path)
        self.context = {"session": "s", "revision": "r", "project_path": self.temp.name,
                        "music_path": str(self.path), "note_count": 0, "lines": [],
                        "audio_duration_seconds": 10, "offset": 0,
                        "bpm_list": [{"beat": [0, 0, 1], "bpm": 120}]}

    def test_layer_view_one_object_per_selected_decision(self):
        plan = v.plan(self.data, self.context, "layer")
        self.assertEqual(len(plan["tracks"]), 2)
        self.assertEqual(len(plan["rows"]), 2)
        self.assertEqual(plan["rows"][0]["kind"], "tap")
        self.assertEqual(plan["rows"][1]["kind"], "hold")
        self.assertAlmostEqual(v.beat_number(plan["rows"][0]["beat"]) / 2, 1.12345, places=4)
        self.assertEqual(v.beat_number(plan["rows"][1]["hold_beat"]), 4)
        self.assertLess(plan["rows"][0]["x"], 0)
        self.assertGreater(plan["rows"][1]["x"], 0)
        self.assertEqual([r["value"] for r in plan["opacity"]], [65, 230, 65])

    def test_reason_view_is_explicitly_multilabel(self):
        summary = v.summary(self.data)
        self.assertEqual(summary["reason_tracks"], 3)
        self.assertEqual(summary["reason_view_objects"], 4)
        plan = v.plan(self.data, self.context, "reason")
        self.assertEqual(len(plan["rows"]), 4)
        self.assertEqual(len({r["decision_id"] for r in plan["rows"]}), 2)

    def test_piecewise_bpm_and_offset(self):
        bpm = [{"beat": [0, 0, 1], "bpm": 120}, {"beat": [4, 0, 1], "bpm": 60}]
        self.assertEqual(v.audio_to_beat(4.5, bpm, 500), 6)
        self.assertEqual(v.audio_to_beat(.25, bpm, 500), -.5)
        for t in [0, .000001, .123456, 999.99999, -.125]:
            beat = v.beat_array(t)
            self.assertTrue(0 <= beat[1] < beat[2] <= 10000)
            self.assertAlmostEqual(v.beat_number(beat), t, delta=.000051)

    def test_invalid_analysis_rejects(self):
        for field, value in [("intensity", float("nan")), ("layer", "invented_instrument"), ("time_seconds", 20)]:
            bad = fixture(); bad["decisions"][0][field] = value
            self.path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                v.read_analysis(self.path)

    @patch.object(v, "digest", return_value="wav")
    def test_target_checks_preserve_existing_work(self, _):
        v.check_target(self.data, self.context, self.temp.name)
        for changes in [{"note_count": 1}, {"lines": [{}, {}]}, {"project_path": "/wrong"}, {"audio_duration_seconds": 11}]:
            with self.assertRaises(ValueError):
                v.check_target(self.data, {**self.context, **changes}, self.temp.name)
        with patch.object(v, "digest", return_value="mp3"), self.assertRaises(ValueError):
            v.check_target(self.data, self.context, self.temp.name)

    @patch.object(v, "digest", return_value="wav")
    def test_revision_change_after_dryrun_never_commits(self, _):
        calls = []
        context_calls = 0
        def bridge(name, args):
            nonlocal context_calls
            if name == "get_context":
                context_calls += 1
                return {**self.context, "revision": "r" if context_calls == 1 else "human-change"}
            return {"document": {"notes": {}, "curve_tracks": {}}}
        class Adapter:
            def execute(self, name, args):
                calls.append((name, args))
                return {}
        with self.assertRaisesRegex(ValueError, "changed after dry run"):
            v.execute(self.data, None, self.temp.name, "layer", apply=True, bridge=bridge, adapter=Adapter())
        self.assertEqual([args["dry_run"] for name, args in calls if name == "chart_script"], [True])


if __name__ == "__main__":
    unittest.main()
