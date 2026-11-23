"""
Integration tests for job control and run records in FingerlingCounter.

Uses real video files and the real processing loop. Only the detector is
replaced: synthetic videos contain white blobs ("fish") swimming down across
the counting line, and a blob detector finds them exactly, so expected counts
are known.

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import csv
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.counter import FingerlingCounter  # noqa: E402

W, H = 320, 240          # counting line at y = 120
STEP, LIFE = 10, 20      # each fish moves 10 px/frame for 20 frames: y = 20 → 210


class BlobDetector:
    """Finds bright blobs; stands in for the YOLO model on synthetic frames."""
    confidence_threshold = 0.5
    iou_threshold = 0.5

    def __init__(self, delay=0.0):
        self.delay = delay

    def get_class_keys(self):
        return ["fingerling", "post_fingerling", "juvenile"]

    def detect(self, frame):
        if self.delay:
            time.sleep(self.delay)
        mask = (frame[..., 1] > 128).astype(np.uint8)
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
        dets = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < 20:
                continue
            dets.append({
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
                "center": (int(cents[i][0]), int(cents[i][1])),
                "class_name": "fingerling", "class_display_name": "Fingerling",
                "class_color": (0, 255, 0), "confidence": 0.9,
                "width": int(w), "height": int(h), "area": int(w * h),
            })
        return dets


def write_video(path, n_frames, fish):
    """fish: list of (start_frame, x). Each swims straight down across the line."""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (W, H))
    for f in range(n_frames):
        img = np.zeros((H, W, 3), np.uint8)
        for start, x in fish:
            k = f - start
            if 0 <= k < LIFE:
                y = 20 + STEP * k
                cv2.rectangle(img, (x - 12, y - 5), (x + 12, y + 5), (255, 255, 255), -1)
        vw.write(img)
    vw.release()


class JobControlTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aquacount_test_"))
        cls.video_long = cls.tmp / "long_batch.avi"     # 15 fish, one every 20 frames
        cls.video_short = cls.tmp / "short_batch.avi"   # exactly 2 fish
        write_video(cls.video_long, 300, [(20 * i, 160) for i in range(15)])
        write_video(cls.video_short, 70, [(0, 80), (25, 240)])

        cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
        cfg["video"]["fps"] = None                    # no rate limiting in tests
        cfg["output"]["save_csv"] = False
        cfg["output"]["runs_dir"] = str(cls.tmp / "runs")
        cfg["counting"]["mode"] = "line_crossing"
        cfg["counting"]["count_direction"] = "down"
        cfg["counting"]["count_correction_factor"] = 1.1
        cls.config_path = cls.tmp / "config.yaml"
        cls.config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def make_counter(self, delay=0.0):
        c = FingerlingCounter(config_path=str(self.config_path),
                              weights_path=str(ROOT / "models" / "best.onnx"),
                              use_streaming=False, use_display=False, web_server_mode=True)
        c.detector = BlobDetector(delay)
        c.class_keys = c.detector.get_class_keys()
        return c

    def runs_for(self, stem):
        out = []
        for d in sorted((self.tmp / "runs").glob(f"*_{stem}*")):
            s = d / "summary.json"
            if s.exists():
                out.append(json.loads(s.read_text(encoding="utf-8")))
        return out

    def test_full_run_counts_and_records(self):
        c = self.make_counter()
        c._process_new_source(str(self.video_short))
        runs = self.runs_for("short_batch")
        self.assertTrue(runs)
        run = runs[-1]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["counts"]["total"], 2)
        self.assertEqual(run["corrected_total"], 2)  # round(2 * 1.1)
        run_dir = self.tmp / "runs" / run["run_id"]
        with open(run_dir / "events.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["direction"] == "down" for r in rows))
        for r in rows:
            self.assertTrue((run_dir / r["crop"]).exists())
        self.assertIn("Total counted", (run_dir / "report.html").read_text(encoding="utf-8"))

    def test_new_job_waits_for_and_supersedes_running_job(self):
        c = self.make_counter(delay=0.02)  # long video takes ~6 s
        t = threading.Thread(target=c._process_new_source, args=(str(self.video_long),))
        t.start()
        deadline = time.time() + 10
        while c.frame_count < 30 and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(c.is_processing)

        c._process_new_source(str(self.video_short))  # must not overlap the first loop
        t.join(timeout=10)
        self.assertFalse(t.is_alive())

        long_run = self.runs_for("long_batch")[-1]
        short_run = self.runs_for("short_batch")[-1]
        self.assertEqual(long_run["status"], "superseded")
        self.assertLess(long_run["frames_processed"], 300)
        self.assertIn("warning", long_run)
        # The second job starts from a clean tracker: no fish carried over.
        self.assertEqual(short_run["status"], "completed")
        self.assertEqual(short_run["counts"]["total"], 2)
        self.assertEqual(short_run["frames_processed"], 70)

    def test_stop_marks_run_stopped(self):
        c = self.make_counter(delay=0.02)
        t = threading.Thread(target=c._process_new_source, args=(str(self.video_long),))
        t.start()
        while c.frame_count < 20:
            time.sleep(0.01)
        c._stop_from_server()
        t.join(timeout=10)
        self.assertEqual(self.runs_for("long_batch")[-1]["status"], "stopped")

    def test_reset_mid_run_splits_the_record(self):
        c = self.make_counter(delay=0.01)
        t = threading.Thread(target=c._process_new_source, args=(str(self.video_long),))
        t.start()
        while c.tracker.get_counts().get("total", 0) < 3:
            time.sleep(0.01)
        c._reset_counts_from_server()
        t.join(timeout=15)
        runs = self.runs_for("long_batch")[-2:]
        self.assertEqual(runs[0]["status"], "reset")
        self.assertEqual(runs[1]["status"], "completed")
        # Every fish is in exactly one of the two records.
        self.assertEqual(runs[0]["counts"]["total"] + runs[1]["counts"]["total"], 15)

    def test_unreadable_source_raises_and_records_error(self):
        bad = self.tmp / "not_a_video.avi"
        bad.write_bytes(b"this is not a video")
        c = self.make_counter()
        with self.assertRaises(RuntimeError):
            c._process_new_source(str(bad))
        self.assertEqual(self.runs_for("not_a_video")[-1]["status"], "error")


if __name__ == "__main__":
    unittest.main()
