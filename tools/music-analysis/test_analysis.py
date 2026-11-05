"""Behavior checks using known synthetic audio, plus offline export contracts."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np
import soundfile as sf

import analyze as a
from report import write_report


def pulse_song(duration=8, times=(1, 2, 3, 4, 5, 6), amplitudes=None):
    y = np.zeros(round(a.SR * duration), dtype=np.float32)
    rng = np.random.default_rng(19)
    tick = rng.normal(size=round(a.SR * 0.06)) * np.exp(-np.arange(round(a.SR * .06)) / a.SR * 85)
    for i, t in enumerate(times):
        start = round(t * a.SR)
        length = min(len(tick), len(y) - start)
        y[start:start + length] += tick[:length] * (amplitudes[i] if amplitudes is not None else .2)
    return y


def analyze_array(y, **kwargs):
    features = a.extract(y, progress=lambda _: None)
    duration = len(y) / a.SR
    sections, climax, timeline, curve = a.structure(features, duration)
    decisions = a.decide(features, sections, curve, duration, **kwargs)
    return features, sections, climax, timeline, decisions


class SignalTests(unittest.TestCase):
    def test_silence_has_no_notes_or_climax(self):
        _, _, climax, timeline, decisions = analyze_array(np.zeros(a.SR * 16, dtype=np.float32))
        self.assertEqual(decisions, [])
        self.assertEqual(climax, [])
        self.assertTrue(all(row["intensity"] == 0 for row in timeline))

    def test_known_attacks_and_fast_run_are_preserved(self):
        expected = [1, 2, 3, 4, 4.074, 4.148, 4.222, 5, 6]
        _, _, _, _, notes = analyze_array(pulse_song(times=expected), threshold=40)
        selected = [n["time_seconds"] for n in notes if n["selected"]]
        self.assertGreaterEqual(len(selected), len(expected))
        for t in expected:
            self.assertLess(min(abs(t - n) for n in selected), .05, f"Lost or shifted attack {t}")
        for left, right in zip(selected[:-1], selected[1:]):
            self.assertGreaterEqual(right - left, .045 - .00001)

    def test_louder_matching_attack_gets_higher_intensity(self):
        _, _, _, _, notes = analyze_array(pulse_song(amplitudes=[.08, .08, .08, .5, .5, .5]), threshold=35)
        quiet = min(notes, key=lambda n: abs(n["time_seconds"] - 2))
        loud = min(notes, key=lambda n: abs(n["time_seconds"] - 5))
        self.assertGreater(loud["intensity"], quiet["intensity"] + 8)
        self.assertNotEqual(loud["intensity"], loud["priority"])
        self.assertNotEqual(loud["intensity"] / 100, loud["confidence"])

    def test_sustained_tone_can_propose_hold(self):
        y = np.zeros(a.SR * 5, dtype=np.float32)
        t = np.arange(a.SR * 2) / a.SR
        tone = .35 * np.sin(2 * np.pi * 440 * t)
        tone[:441] *= np.linspace(0, 1, 441)
        tone[-441:] *= np.linspace(1, 0, 441)
        y[a.SR:a.SR * 3] = tone
        _, _, _, _, notes = analyze_array(y, threshold=35)
        holds = [n for n in notes if n["selected"] and n["suggested_type"] == "hold"]
        self.assertTrue(holds, "A clear sustained monophonic tone should provide a hold candidate")
        self.assertTrue(any(n["end_seconds"] - n["time_seconds"] > 1 for n in holds))
        self.assertTrue(all(n["end_seconds"] <= len(y) / a.SR for n in holds))

    def test_brief_loud_hit_is_not_a_climax(self):
        _, _, climax, _, _ = analyze_array(pulse_song(duration=20, times=[10], amplitudes=[.8]))
        self.assertEqual(climax, [])

    def test_sustained_dense_loud_section_is_detected(self):
        times = list(np.arange(1, 10, 1)) + list(np.arange(12, 23, .2)) + list(np.arange(25, 31, 1))
        amplitudes = [.06 if t < 12 or t > 23 else .45 for t in times]
        _, sections, climax, _, _ = analyze_array(pulse_song(32, times, amplitudes))
        self.assertTrue(climax)
        self.assertTrue(any(c["start_seconds"] < 18 < c["end_seconds"] for c in climax))
        self.assertEqual(sections[0]["start_seconds"], 0)
        self.assertEqual(sections[-1]["end_seconds"], 32)
        self.assertTrue(all(x["end_seconds"] == y["start_seconds"] for x, y in zip(sections, sections[1:])))


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.result = {"source": {"sha256": "abc", "duration_seconds": 10}, "analysis_id": "run1",
                       "parameters": {"bpm": 120, "offset_seconds": 0.5},
                       "decisions": [{"id": "n00001", "time_seconds": 1, "detected_time_seconds": 1,
                                      "end_seconds": 1, "selected": True, "intensity": 65,
                                      "suggested_type": "tap", "section_id": "s001"}],
                       "sections": [{"id": "s001", "start_seconds": 0, "end_seconds": 10}],
                       "climax_regions": []}

    def review(self, **kwargs):
        return {"source_sha256": "abc", "analysis_id": "run1", **kwargs}

    def test_review_changes_timing_without_erasing_detection(self):
        a.apply_review(self.result, self.review(decisions=[{"id": "n00001", "time_seconds": 2, "intensity": 12}]))
        note = self.result["decisions"][0]
        self.assertEqual(note["time_seconds"], 2)
        self.assertEqual(note["end_seconds"], 2)
        self.assertEqual(note["detected_time_seconds"], 1)
        self.assertEqual(note["beat"], 3)
        self.assertEqual(note["automatic_before_review"]["intensity"], 65)

    def test_reject_mismatched_review_and_invalid_values(self):
        invalid = [self.review(source_sha256="wrong"), self.review(analysis_id="wrong"),
                   self.review(decisions=[{"id": "missing"}]),
                   self.review(decisions=[{"id": "n00001", "selected": "yes"}]),
                   self.review(decisions=[{"id": "n00001", "intensity": float("nan")}]),
                   self.review(decisions=[{"id": "n00001", "time_seconds": 10}]),
                   self.review(decisions=[{"id": "n00001", "suggested_type": "hold", "end_seconds": .5}])]
        for review in invalid:
            with self.subTest(review=review), self.assertRaises(ValueError):
                a.apply_review(copy.deepcopy(self.result), review)

    def test_reviewed_section_bounds_and_climax_replace_automatic(self):
        sections = [{"start_seconds": 0, "end_seconds": 5, "label": "Intro", "climax": False},
                    {"start_seconds": 5, "end_seconds": 10, "label": "Peak", "climax": True}]
        a.apply_review(self.result, self.review(sections=sections))
        self.assertEqual(self.result["climax_regions"][0]["start_seconds"], 5)
        self.assertEqual(self.result["climax_regions"][0]["provenance"], "review")
        sections[1]["start_seconds"] = 4.9
        with self.assertRaises(ValueError):
            a.apply_review(self.result, self.review(sections=sections))

    def test_stems_require_matching_audio_and_time_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stems.json"
            path.write_text(json.dumps({"source_sha256": "wrong"}))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                a.load_stems(path, "abc", 10)
            path.write_text(json.dumps({"source_sha256": "abc", "time_origin": "chart"}))
            with self.assertRaisesRegex(ValueError, "time_origin"):
                a.load_stems(path, "abc", 10)

    def test_html_cannot_inject_script_from_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = {"source": {"path": "/tmp/a.mp3"}, "text": "</script><script>alert(1)</script>"}
            destination = Path(tmp) / "index.html"
            write_report(result, destination)
            page = destination.read_text()
            self.assertNotIn("<script>alert(1)", page)
            self.assertIn("\\u003c/script\\u003e", page)
            self.assertNotIn("__ANALYSIS_DATA__", page)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_mp3_end_to_end_exports_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sf.write(root / "source.wav", pulse_song(4, [1, 2, 3]), a.SR)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(root / "source.wav"),
                            str(root / "source.mp3")], check=True)
            result = a.run(root / "source.mp3", root / "result", progress=lambda _: None)
            report = root / "result"
            for name in ["analysis.json", "decisions.csv", "selected-notes.csv", "index.html", "audio.wav", "with-hits.wav", "review-template.json"]:
                self.assertTrue((report / name).is_file(), name)
            self.assertGreater(result["summary"]["selected_count"], 0)
            self.assertEqual(result["source"]["time_origin"], "decoded_audio_start")
            self.assertEqual(sf.info(report / "audio.wav").frames, sf.info(report / "with-hits.wav").frames)
            for t in [1, 2, 3]:
                self.assertLess(min(abs(n["time_seconds"] - t) for n in result["selected_notes"]), .05)
            review = {**result["review_template"], "decisions": [
                {"id": result["selected_notes"][0]["id"], "intensity": 11}]}
            (root / "review.json").write_text(json.dumps(review))
            reviewed = a.run(root / "source.mp3", root / "reviewed", review=root / "review.json", progress=lambda _: None)
            self.assertEqual(reviewed["review_template"]["decisions"], review["decisions"])
            self.assertEqual(reviewed["analysis_id"], result["analysis_id"])
            self.assertEqual(reviewed["summary"]["reviewed_count"], 1)
            self.assertEqual(next(n["intensity"] for n in reviewed["selected_notes"] if n["id"] == review["decisions"][0]["id"]), 11)
            with self.assertRaisesRegex(ValueError, "already exists"):
                a.run(root / "source.mp3", report, progress=lambda _: None)


if __name__ == "__main__":
    unittest.main()
