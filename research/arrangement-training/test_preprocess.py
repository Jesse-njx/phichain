import copy
import unittest
from preprocess import Events, convert_chart, make_windows, oriented_angle


def fixture():
    return {"formatVersion": 3, "offset": .125, "judgeLineList": [{
        "bpm": 120, "judgeLineMoveEvents": [{"startTime": 0, "endTime": 4096, "start": .5, "end": .5, "start2": .2, "end2": .2}],
        "judgeLineRotateEvents": [{"startTime": 0, "endTime": 4096, "start": 0, "end": 0}],
        "speedEvents": [{"startTime": 0, "endTime": 4096, "value": 1}],
        "notesAbove": [{"type": 1, "time": 32+i*16, "positionX": (-3 if i%2 else 3), "holdTime": 0, "speed": 1, "floorPosition": 0} for i in range(40)],
        "notesBelow": []}]}


class GeometryTests(unittest.TestCase):
    def test_angle_side_wrap_and_reverse(self):
        self.assertEqual(oriented_angle(360, True, 1), 0)
        self.assertEqual(oriented_angle(180, False, 1), 0)
        self.assertEqual(oriented_angle(0, False, 1), 180)
        self.assertEqual(oriented_angle(180, True, -1), 0)
        self.assertEqual(oriented_angle(-20, True, 1), 20)

    def test_world_x_line_bpm_offset_and_v1(self):
        source = fixture(); notes = convert_chart(source)
        self.assertAlmostEqual(notes[0]['time'], .625)
        self.assertAlmostEqual(notes[0]['x'], .5+3*.05625)
        second = copy.deepcopy(source['judgeLineList'][0]); second['bpm'] = 240
        second['notesAbove'] = [dict(second['notesAbove'][0], time=64)]
        source['judgeLineList'].append(second)
        both = convert_chart(source)
        self.assertAlmostEqual(both[0]['time'], both[1]['time'])
        old = Events([dict(startTime=0,endTime=32,start=440530,end=440530)], 1, 'x', 1)
        self.assertEqual(old.value(0), .5)
        self.assertEqual(Events([dict(startTime=0,endTime=32,start=440530,end=440530)], 1, 'y', 1).value(0), 1)

    def test_threshold_and_inverted_below(self):
        source = fixture(); r = source['judgeLineList'][0]['judgeLineRotateEvents'][0]
        r['start'] = r['end'] = 20
        self.assertTrue(convert_chart(source)[0]['angle_eligible'])
        r['start'] = r['end'] = 20.01
        self.assertFalse(convert_chart(source)[0]['angle_eligible'])
        r['start'] = r['end'] = 180
        line = source['judgeLineList'][0]; line['notesBelow'] = line.pop('notesAbove'); line['notesAbove'] = []
        self.assertTrue(convert_chart(source)[0]['angle_eligible'])

    def test_moving_hold_and_broken_phrase(self):
        source = fixture(); line = source['judgeLineList'][0]
        line['notesAbove'][20]['speed'] = 0
        notes = convert_chart(source); windows = make_windows(notes)
        rejected = notes[20]['id']
        self.assertTrue(windows)
        for window in windows:
            self.assertNotIn(rejected, {n['id'] for n in window})
            self.assertFalse(window[0]['time'] < notes[20]['time'] < window[-1]['time'])
        line['notesAbove'][0].update(type=3, holdTime=32)
        line['judgeLineMoveEvents'][0].update(end=1, endTime=64)
        self.assertIn('moving_hold_not_representable', convert_chart(source)[0]['exclusions'])


if __name__ == '__main__':
    unittest.main()
