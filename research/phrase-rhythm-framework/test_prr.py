"""Tests for the PRR builder on synthetic evidence (no audio, no models).

    main/research/music-flow-study/.venv/bin/python -m unittest test_prr -v
"""
import unittest
from fractions import Fraction

import numpy as np

import prr
import prr_build as pb

FPS = 22050 / 110
BPM = 120.0
BEAT = 60.0 / BPM
OFF = 0.5
BARS = 16  # 4 phrases of 4 bars
DUR = OFF + BARS * 4 * BEAT + 1.0


def spikes(times, n, heights=None):
    e = np.zeros(n, np.float32)
    for i, t in enumerate(times):
        k = int(round(t * FPS))
        if 0 <= k < n:
            e[k] = heights[i] if heights is not None else 1.0
    return e


def steps(times, n):
    """Activation that jumps at each hit and decays (NMF-like)."""
    a = np.zeros(n, np.float32)
    for t in times:
        k = int(round(t * FPS))
        if 0 <= k < n:
            a[k : k + 30] += np.exp(-np.arange(min(30, n - k)) / 8.0)
    return a


def synthetic(triplet_bar=None, kick_out_bars=(), lead_offset=0.0):
    n = int(DUR * FPS) + 10
    kicks = [OFF + b * BEAT for b in range(BARS * 4) if b // 4 not in kick_out_bars]
    snares = [OFF + b * BEAT for b in range(BARS * 4) if b % 2 == 1]
    hats = [OFF + (b + 0.5) * BEAT for b in range(BARS * 4)]
    hat_h = [1.0] * len(hats)
    if triplet_bar is not None:
        a = OFF + triplet_bar * 4 * BEAT
        extra = [a + k * BEAT / 3 for k in range(12) if k % 3]
        hats += extra
        hat_h += [1.0] * len(extra)
        order = np.argsort(hats)
        hats, hat_h = list(np.array(hats)[order]), list(np.array(hat_h)[order])
    # lead: same 1-bar figure every bar: C5 (1 beat sustain), D5 8th, E5 8th, G5 2 beats
    notes = []
    for bar in range(BARS):
        a = OFF + bar * 4 * BEAT + lead_offset
        for pos, length, pitch in ((0, 1.0, 72), (1.0, 0.5, 74), (1.5, 0.5, 76), (2.0, 2.0, 79)):
            notes.append(dict(start=a + pos * BEAT, end=a + (pos + length) * BEAT - 0.01, pitch=pitch, activation=0.8, onset=0.9, kind="pitch_change_or_entry"))
    rms = {k: np.full(n, 0.1, np.float32) for k in ("mix", "drums", "bass", "vocals", "other")}
    ev = dict(
        audio="synthetic",
        audio_sha256="0",
        duration=DUR,
        env_fps=FPS,
        envelopes=dict(
            act_kick=steps(kicks, n), act_snare=steps(snares, n), act_hat=steps(hats, n),
            drums=spikes(sorted(set(kicks + snares + hats)), n), mix=spikes(sorted(set(kicks + hats)), n),
        ),
        rms=rms,
        notes=dict(vocals=[], other=notes, bass=[]),
    )
    return ev


def config(**kw):
    sections = [
        dict(id="verse", beats=[0, 32], function="verse", group="A", lead="synth"),
        dict(id="chorus", beats=[32, 64], function="chorus", group="A'", lead="synth"),
    ]
    return pb.grid_from_config(dict(bpm=BPM, offset_seconds=OFF, sections=sections, **kw), DUR)


def build(ev, grid=None):
    b = pb.Builder(ev, grid or config())
    return b.build("synthetic", "0")


class SlotSetTests(unittest.TestCase):
    def test_straight_onsets_stay_sixteenths(self):
        subs, _ = pb.choose_slot_set({"hat": [0.5, 1.5, 2.5, 3.5, 0.25, 1.25]})
        self.assertEqual(subs, [Fraction(1, 4)])

    def test_triplets_added(self):
        pos = [k / 3 for k in range(12)]
        subs, why = pb.choose_slot_set({"hat": pos})
        self.assertIn(Fraction(1, 6), subs)
        self.assertEqual(why["triplet_layers"], ["hat"])

    def test_tolerance_has_floor_and_cap(self):
        tol = pb.tolerance_beats([Fraction(1, 4)], BEAT)
        self.assertAlmostEqual(tol, max(1 / 16, 0.015 / BEAT))
        mixed = pb.tolerance_beats([Fraction(1, 4), Fraction(1, 6)], BEAT)
        self.assertLessEqual(mixed, 0.45 / 12 + 1e-9)


class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = build(synthetic())
        cls.p1 = cls.rec["phrases"][0]

    def test_phrases_and_bars(self):
        self.assertEqual(len(self.rec["phrases"]), 4)
        self.assertEqual(self.p1["bars"], [1, 2, 3, 4])
        self.assertTrue(self.p1["section_start"])
        self.assertEqual(self.p1["MG6_slot_set"]["subdivisions"], ["1/4"])

    def test_layer_lines(self):
        lines = self.p1["MR1_layer_lines"]
        self.assertEqual(lines["kick"]["bars"][0]["string"], "X...X...X...X...")
        self.assertEqual(lines["snare"]["bars"][0]["string"], "....X.......X...")
        self.assertEqual(lines["hat"]["bars"][0]["string"], "..X...X...X...X.")
        self.assertEqual(lines["other"]["bars"][0]["string"], "X~~~X~X~X~~~~~~~")
        self.assertEqual(lines["other"]["bars"][0]["pitches"], ["C5", "D5", "E5", "G5"])

    def test_cells_are_shared(self):
        kick_cells = self.rec["MR2_cells"]["kick"]
        self.assertEqual(len(kick_cells), 1)
        self.assertEqual(len(kick_cells[0]["bars"]), BARS)

    def test_sustains(self):
        sus = [s for s in self.p1["MR6_sustains"] if s["layer"] == "other"]
        self.assertEqual([s["slot"] for s in sus[:2]], ["b1.0", "b1.8"])
        self.assertAlmostEqual(sus[0]["length_beats"], 1.0)
        self.assertAlmostEqual(sus[1]["length_beats"], 2.0)

    def test_readings_and_thinning(self):
        rs = {r["id"]: r for r in self.p1["MH0_readings"]}
        self.assertEqual(set(rs), {"R-lead", "R-lead+kick", "R-drums", "R-dense"})
        self.assertEqual(rs["R-lead"]["density"]["hits"], 16)
        lead_kick_bar1 = [e["slot"] for e in rs["R-lead+kick"]["events"] if e["slot"].startswith("b1.")]
        self.assertEqual(lead_kick_bar1, ["b1.0", "b1.4", "b1.6", "b1.8", "b1.12"])
        # anchors survive every level; the phrase downbeat is an anchor
        first = rs["R-lead"]["events"][0]
        self.assertIn("section_arrival", first["anchor"])
        self.assertEqual(first["keep_through"], 4)
        ladder = [x["events"] for x in rs["R-dense"]["thinning_ladder"]]
        self.assertEqual(ladder, sorted(ladder, reverse=True))

    def test_recurrence(self):
        later = self.rec["phrases"][2]
        self.assertEqual(later["recurrence"]["same_as"], "P01")
        self.assertEqual(later["recurrence"]["lead_bar_differences"], [])
        self.assertEqual(later["default_reading"], self.p1["default_reading"])


class ArticulationTests(unittest.TestCase):
    def test_triplet_phrase_and_rest(self):
        rec = build(synthetic(triplet_bar=5, kick_out_bars=(8, 9, 10, 11)))
        p2 = rec["phrases"][1]
        self.assertIn("1/6", p2["MG6_slot_set"]["subdivisions"])
        self.assertEqual(rec["phrases"][0]["MG6_slot_set"]["subdivisions"], ["1/4"])
        p3 = rec["phrases"][2]
        self.assertEqual(p3["MR1_layer_lines"]["kick"]["attacks"], 0)
        kinds = {(b["layer"], b["kind"]) for b in rec["MR3_fills_and_breaks"]["breaks"]}
        self.assertIn(("kick", "stops"), kinds)
        self.assertIn(("kick", "returns"), kinds)
        rs = {r["id"]: r for r in p3["MH0_readings"]}
        self.assertEqual(rs["R-lead+kick"]["notes"], ["no kick in phrase: snare accents instead"])

    def test_off_grid_and_latency(self):
        ev = synthetic(lead_offset=0.040)  # 40 ms late: beyond tolerance
        rec = build(ev)
        self.assertGreater(len(rec["phrases"][0]["MR4_off_grid"]), 0)
        b = pb.Builder(synthetic(lead_offset=0.040), config(), latency={"other": 0.040})
        rec2 = b.build("s", "0")
        self.assertEqual(rec2["phrases"][0]["MR1_layer_lines"]["other"]["bars"][0]["string"], "X~~~X~X~X~~~~~~~")

    def test_swing_estimate(self):
        pos = []
        for b in range(8):
            pos += [b, b + 0.5 + 0.06]
        sw = pb.Builder.estimate_swing(pos)
        self.assertTrue(sw["consistent"])
        self.assertAlmostEqual(sw["eighth_shift_beats"], 0.06, places=3)
        self.assertGreater(sw["swing_ratio"], 1.2)


class UserTests(unittest.TestCase):
    def test_written_rhythm_propagates(self):
        rec = build(synthetic())
        user = {"rhythms": [{"phrase": "P01", "bars": {"1": "X...x...X.......", "2": "X...x...X......."}}], "choices": [{"phrase": "P01", "reading": "R-lead", "apply_to_group": True}]}
        prr.apply_user(rec, user)
        p1 = rec["phrases"][0]
        r = next(x for x in p1["MH0_readings"] if x["id"] == "R-user")
        self.assertEqual(r["status"], "user-confirmed")
        self.assertEqual(len(r["events"]), 6)
        p3 = rec["phrases"][2]
        prop = next(x for x in p3["MH0_readings"] if x["id"] == "R-user")
        self.assertEqual(prop["status"], "propagated")
        self.assertEqual(p3["chosen_reading"]["status"], "propagated")

    def test_taps_are_offset_fitted(self):
        rec = build(synthetic())
        p1 = rec["phrases"][0]
        taps = [OFF + 0.03 + k * BEAT for k in range(16)]
        bars, shift = prr.quantize_taps(p1, rec, taps)
        self.assertAlmostEqual(shift, -0.03, places=2)
        self.assertEqual(bars["1"], "x...x...x...x...")


if __name__ == "__main__":
    unittest.main()
