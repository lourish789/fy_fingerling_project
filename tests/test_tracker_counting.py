"""
Counting-logic tests for FingerlingTracker (line-crossing mode).

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from models.tracker import FingerlingTracker  # noqa: E402

LINE_Y = 300


def det(x, y, cls="fingerling", conf=0.8):
    return {"bbox": [x - 15, y - 8, x + 15, y + 8], "center": (x, y),
            "class_name": cls, "confidence": conf}


def make_tracker(direction="down", min_hits=3):
    t = FingerlingTracker(max_age=30, min_hits=min_hits, max_distance=160,
                          counting_mode="line_crossing", count_min_hits=min_hits,
                          count_direction=direction)
    t.set_counting_line(0, LINE_Y, 1000, LINE_Y, "horizontal")
    return t


def run_path(tracker, ys, x=500, cls="fingerling"):
    for y in ys:
        tracker.update([det(x, y, cls)])


class LineCrossingTests(unittest.TestCase):

    def test_fish_crossing_before_confirmation_is_counted(self):
        # Regression: first seen just above the line and crosses on its 2nd
        # detection, before min_hits=3 confirms it. The old rule never counted it.
        for step in (20, 60):
            with self.subTest(step=step):
                t = make_tracker()
                run_path(t, range(LINE_Y - step, 700, step))
                self.assertEqual(t.get_counts().get("total", 0), 1)

    def test_slow_fish_counted_exactly_once(self):
        t = make_tracker()
        run_path(t, range(100, 600, 10))
        self.assertEqual(t.get_counts()["total"], 1)

    def test_static_false_positive_never_counted(self):
        t = make_tracker()
        for _ in range(100):
            t.update([det(500, 250), det(700, 350)])  # one each side, both static
        self.assertEqual(t.get_counts().get("total", 0), 0)

    def test_direction_gate_rejects_upstream_movers(self):
        t = make_tracker(direction="down")
        run_path(t, range(600, 50, -20))
        self.assertEqual(t.get_counts().get("total", 0), 0)

    def test_oscillating_fish_counted_once(self):
        t = make_tracker()
        run_path(t, [250, 270, 290, 310, 290, 310, 290, 330, 360, 400])
        self.assertEqual(t.get_counts()["total"], 1)

    def test_fish_that_turns_back_before_confirmation_is_not_counted_down(self):
        # Crossed down and came back up during its first frames; it ends upstream.
        t = make_tracker()
        run_path(t, [280, 310, 280, 260, 240])
        self.assertEqual(t.get_counts().get("total", 0), 0)

    def test_fish_born_downstream_is_not_counted(self):
        t = make_tracker()
        run_path(t, range(320, 700, 20))
        self.assertEqual(t.get_counts().get("total", 0), 0)

    def test_parallel_fish_each_counted(self):
        t = make_tracker()
        lanes = [100, 300, 500, 700, 900]
        for y in range(150, 500, 25):
            t.update([det(x, y) for x in lanes])
        self.assertEqual(t.get_counts()["total"], len(lanes))

    def test_reset_does_not_recount_fish_already_past_line(self):
        t = make_tracker()
        run_path(t, range(200, 420, 20))
        self.assertEqual(t.get_counts()["total"], 1)
        t.reset_counts()
        run_path(t, range(420, 600, 20))  # same fish keeps swimming downstream
        self.assertEqual(t.get_counts().get("total", 0), 0)

    def test_majority_vote_sets_class(self):
        t = make_tracker()
        labels = ["juvenile", "fingerling", "fingerling", "fingerling", "fingerling", "juvenile"]
        for y, cls in zip(range(220, 420, 35), labels):
            t.update([det(500, y, cls)])
        self.assertEqual(t.get_counts().get("fingerling"), 1)
        self.assertNotIn("juvenile", t.get_counts())

    def test_events_recorded_once_per_count(self):
        t = make_tracker()
        run_path(t, range(200, 500, 20))
        events = t.drain_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["class"], "fingerling")
        self.assertEqual(ev["direction"], "down")
        self.assertEqual(ev["seq"], 1)
        self.assertGreaterEqual(ev["hits"], 3)
        self.assertAlmostEqual(ev["mean_confidence"], 0.8, places=3)
        self.assertEqual(t.drain_events(), [])  # drained

    def test_vertical_line_right_direction(self):
        t = FingerlingTracker(min_hits=3, counting_mode="line_crossing",
                              count_min_hits=3, count_direction="right", max_distance=160)
        t.set_counting_line(500, 0, 500, 1000, "vertical")
        for x in range(380, 700, 30):
            t.update([det(x, 400)])
        self.assertEqual(t.get_counts()["total"], 1)


class UniqueTrackModeTests(unittest.TestCase):

    def test_unique_track_counts_after_min_hits(self):
        t = FingerlingTracker(min_hits=3, counting_mode="unique_track", count_min_hits=3)
        run_path(t, [100, 110])
        self.assertEqual(t.get_counts().get("total", 0), 0)
        run_path(t, [120, 130, 140])
        self.assertEqual(t.get_counts()["total"], 1)
        self.assertEqual(len(t.drain_events()), 1)


if __name__ == "__main__":
    unittest.main()
