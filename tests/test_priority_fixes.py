"""
Regression tests for Priority 1-3 engineering fixes:
- ONNX detector preprocessing parity (CLAHE before letterbox, preprocess flag, class-aware NMS, fallback)
- Optional channel ROI cropping and full-frame coordinate mapping
- Batch upload CSV export when detections is a list of dicts
- /api/stop race condition guard (keeps is_processing=True until worker finishes)
- /api/process_url SSRF validation (blocks loopback/metadata, allows LAN IP cameras & public URLs)
- Directional counting line arrows & ROI visualization

Run from the repository root:
    python -m unittest discover -s tests -v
"""
import csv
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from models.onnx_detector import OnnxFingerlingDetector, _FallbackDetector  # noqa: E402
from streaming.server import StreamingServer, is_safe_media_url  # noqa: E402
from video.visualization import Visualizer  # noqa: E402
from app.counter import FingerlingCounter  # noqa: E402


class OnnxDetectorParityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.detector = OnnxFingerlingDetector(
            str(ROOT / "models" / "best.onnx"),
            confidence_threshold=0.50,
            iou_threshold=0.50,
        )

    def test_default_size_consistency_is_disabled(self):
        self.assertFalse(self.detector.size_consistency_enabled)

    def test_preprocess_flag_is_honored_and_letterbox_padding_untouched(self):
        # Wide 16:9 image with varying brightness so CLAHE visibly changes pixel values
        img = np.zeros((180, 320, 3), dtype=np.uint8)
        cv2.circle(img, (160, 90), 50, (40, 80, 120), -1)
        cv2.rectangle(img, (20, 20), (100, 140), (200, 200, 200), -1)

        blob_clahe, _, pad_top, _ = self.detector._preprocess(img, apply_clahe=True)
        blob_raw, _, _, _ = self.detector._preprocess(img, apply_clahe=False)

        self.assertGreater(pad_top, 0)
        # CLAHE must actually alter the image content when enabled
        self.assertFalse(np.allclose(blob_clahe, blob_raw))
        # Letterbox padding rows must remain exact 114/255.0 (CLAHE ran BEFORE letterboxing)
        expected_pad = np.float32(114.0 / 255.0)
        self.assertTrue(np.allclose(blob_clahe[0, :, :pad_top, :], expected_pad, atol=1e-5))

    def test_class_aware_nms_keeps_different_classes_and_suppresses_same_class(self):
        boxes = np.array([
            [10.0, 10.0, 50.0, 50.0],  # class 0, score 0.9
            [11.0, 11.0, 51.0, 51.0],  # class 0, score 0.8 (duplicate -> suppress)
            [10.0, 10.0, 50.0, 50.0],  # class 1, score 0.85 (different class -> keep)
        ], dtype=np.float32)
        scores = np.array([0.9, 0.8, 0.85], dtype=np.float32)
        cls_ids = np.array([0, 0, 1], dtype=np.int64)

        keep = self.detector._nms(boxes, scores, cls_ids)
        self.assertEqual(sorted(keep), [0, 2])

    def test_fallback_detector_exists_and_runs(self):
        fb = _FallbackDetector()
        self.assertEqual(fb.get_class_keys(), ["fingerling", "post_fingerling", "juvenile"])
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        dets = fb.detect(frame)
        self.assertIsInstance(dets, list)


class ChannelRoiTests(unittest.TestCase):

    def test_relative_and_pixel_roi_crop_and_remap(self):
        counter = FingerlingCounter(
            weights_path=str(ROOT / "models" / "best.onnx"),
            use_streaming=False,
            use_display=False,
        )
        seen_shapes = []

        class StubDetector:
            def detect(self, frame):
                seen_shapes.append(frame.shape[:2])
                return [{
                    "bbox": [10, 20, 30, 50],
                    "center": (20, 35),
                    "class_name": "fingerling",
                    "confidence": 0.9,
                    "width": 20,
                    "height": 30,
                    "area": 600,
                }]

        counter.detector = StubDetector()
        frame = np.zeros((400, 800, 3), dtype=np.uint8)

        # Relative ROI: x in [200, 600], y in [100, 300] -> 200x400 crop
        counter.config.setdefault("video", {})["roi"] = [0.25, 0.25, 0.75, 0.75]
        dets = counter._detect_with_roi(frame)
        self.assertEqual(seen_shapes[-1], (200, 400))
        self.assertEqual(dets[0]["bbox"], [210, 120, 230, 150])
        self.assertEqual(dets[0]["center"], (220, 135))

        # Pixel ROI: x in [50, 250], y in [40, 140] -> 100x200 crop
        counter.config["video"]["roi"] = [50, 40, 250, 140]
        dets = counter._detect_with_roi(frame)
        self.assertEqual(seen_shapes[-1], (100, 200))
        self.assertEqual(dets[0]["bbox"], [60, 60, 80, 90])
        self.assertEqual(dets[0]["center"], (70, 75))


class ServerFixesTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aquacount_srv_"))
        self.server = StreamingServer(runs_dir=str(self.tmp / "runs"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_batch_csv_writes_cleanly_when_detections_is_a_list(self):
        img_path = self.tmp / "sample.jpg"
        cv2.imwrite(str(img_path), np.zeros((100, 100, 3), dtype=np.uint8))

        class StubCounter:
            def process_image_file(self, path, no_annotations=False):
                return {
                    "counts": {"total": 2, "fingerling": 2, "post_fingerling": 0, "juvenile": 0, "unknown": 0},
                    "detections": [{"bbox": [1, 2, 3, 4]}, {"bbox": [5, 6, 7, 8]}],
                    "annotated_image": np.zeros((100, 100, 3), dtype=np.uint8),
                }

        self.server.counter = StubCounter()
        self.server._process_batch_files([{"filename": "sample.jpg", "filepath": str(img_path)}])

        # Detections must be normalized to an int count
        self.assertEqual(self.server.batch_results[0]["detections"], 2)

        # batch_summary.csv must exist and contain the integer detection count
        csv_files = list((self.tmp / "runs").glob("*_batch-*/batch_summary.csv"))
        self.assertEqual(len(csv_files), 1)
        with open(csv_files[0], encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "sample.jpg")
        self.assertEqual(rows[0]["detections"], "2")
        self.assertEqual(rows[0]["total"], "2")

    def test_stop_keeps_is_processing_true_until_worker_exits(self):
        release = threading.Event()
        started = threading.Event()

        def slow_job():
            started.set()
            release.wait(timeout=5.0)

        self.server.stop_callback = lambda: None
        ok = self.server._start_job("upload", "test.mp4", slow_job, ())
        self.assertTrue(ok)
        self.assertTrue(started.wait(timeout=2.0))

        client = self.server.app.test_client()
        resp = client.post("/api/stop")
        self.assertEqual(resp.status_code, 200)
        # Worker is still finishing teardown -> is_processing must still be True
        self.assertTrue(self.server.is_processing)

        # Once worker finishes, is_processing clears automatically
        release.set()
        deadline = time.time() + 3.0
        while self.server.is_processing and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.server.is_processing)

    def test_url_ssrf_validation(self):
        # Blocked targets
        for bad in [
            "http://127.0.0.1:5000/secret",
            "http://localhost/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://0.0.0.0/test",
            "file:///etc/passwd",
            "ftp://example.com/a.mp4",
        ]:
            ok, _ = is_safe_media_url(bad)
            self.assertFalse(ok, f"Expected URL to be blocked: {bad}")

        # Allowed targets (public URLs + hatchery LAN IP cameras)
        for good in [
            "https://example.com/video.mp4",
            "rtsp://192.168.1.45:8080/h264_ulaw.sdp",
            "http://10.0.0.12:8080/video",
            "rtmp://172.16.0.5/live/channel1",
        ]:
            ok, err = is_safe_media_url(good)
            self.assertTrue(ok, f"Expected URL to be allowed: {good} (err={err})")


class VisualizerDirectionTests(unittest.TestCase):

    def test_directional_arrow_matches_count_direction(self):
        vis = Visualizer()
        blank = np.zeros((200, 200, 3), dtype=np.uint8)

        img_down = vis.draw_counting_line(blank, (0, 100, 200, 100), "horizontal", "down")
        # Arrow extends downward (y in 105..120), nothing above line (y in 80..95)
        self.assertEqual(int(img_down[80:95, 90:110].sum()), 0)
        self.assertGreater(int(img_down[105:122, 90:110].sum()), 0)

        img_up = vis.draw_counting_line(blank, (0, 100, 200, 100), "horizontal", "up")
        self.assertGreater(int(img_up[78:95, 90:110].sum()), 0)
        self.assertEqual(int(img_up[105:122, 90:110].sum()), 0)

        # ROI overlay renders cleanly
        img_roi = vis.draw_all(blank, counting_line=(0, 100, 200, 100), count_direction="down", roi=(20, 20, 180, 180))
        self.assertGreater(int(img_roi[20, 20:180].sum()), 0)


if __name__ == "__main__":
    unittest.main()
