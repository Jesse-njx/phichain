import unittest

from feel import hand_token, mirror_token, patterns
from player import play


def hands(records):
    return "".join(hand_token(f for _, _, f in r["assign"]) for r in records)


class PlayerTest(unittest.TestCase):
    def test_fast_jack_alternates(self):
        _, r = play([[i * .083, 1, .5, 0] for i in range(8)], "two")
        self.assertIn(hands(r), ("LRLRLRLR", "RLRLRLRL"))

    def test_far_stairs_force_llrr(self):
        _, r = play([[i * .083, 1, x, 0] for i, x in enumerate([.1, .15, .85, .9] * 2)], "two")
        self.assertEqual(hands(r), "LLRRLLRR")

    def test_four_note_chord_needs_four_fingers(self):
        chord = [[0, 1, x, 0] for x in (.1, .35, .65, .9)]
        two, _ = play(chord, "two")
        four, r = play(chord, "four")
        self.assertGreater(two, 10)
        self.assertLess(four, 1)
        self.assertEqual(hand_token(f for _, _, f in r[0]["assign"]), "L2+R2")

    def test_drags_under_hold_use_holding_finger(self):
        _, r = play([[0, 3, .3, 1.0], [.2, 2, .32, 0], [.4, 2, .28, 0]], "two")
        held = r[0]["assign"][0][2]
        self.assertEqual([a[0][2] for a in (x["assign"] for x in r[1:])], [held, held])

    def test_mirror_canonical(self):
        self.assertEqual(mirror_token("L2+R"), "L+R2")
        a = patterns([(i * .1, "1", h) for i, h in enumerate("LRLR")])[0][3]
        b = patterns([(i * .1, "1", h) for i, h in enumerate("RLRL")])[0][3]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
