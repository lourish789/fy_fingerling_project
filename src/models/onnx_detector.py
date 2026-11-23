"""
ONNX-Runtime Detector — production-grade, CPU-only inference.

Drop-in replacement for FingerlingDetector that requires only
onnxruntime (~150 MB) instead of PyTorch + Ultralytics (~1.8 GB).

Usage:
    detector = OnnxFingerlingDetector("models/best.onnx")
    detections = detector.detect(frame)   # same API as FingerlingDetector
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CLASS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "fingerling": (0, 255, 0),
    "post_fingerling": (255, 191, 0),
    "juvenile": (0, 140, 255),
    "unknown": (160, 160, 160),
}

_DEFAULT_CLASS_NAMES = ["fingerling", "post_fingerling", "juvenile"]


def _normalize_class_name(name: str) -> str:
    n = name.strip().lower().replace("-", "_").replace(" ", "_")
    if "juvenile" in n and ("post" in n or "pos" in n):
        return "post_fingerling"
    if "post" in n or "posfinger" in n:
        return "post_fingerling"
    if n == "juvenile" or n.startswith("juvenile_"):
        return "juvenile"
    if "fingerling" in n:
        return "fingerling"
    return n or "unknown"


def _display_name(key: str) -> str:
    mapping = {
        "fingerling": "Fingerling",
        "post_fingerling": "Post-Fingerling",
        "juvenile": "Juvenile",
    }
    return mapping.get(key, key.replace("_", " ").title())


class OnnxFingerlingDetector:
    """Lightweight ONNX-based detector — no PyTorch required at runtime."""

    def __init__(
        self,
        onnx_path: str = "models/best.onnx",
        confidence_threshold: float = 0.50,
        iou_threshold: float = 0.50,
        input_size: int = 640,
        class_names: Optional[List[str]] = None,
        num_threads: Optional[int] = None,
        size_consistency_enabled: bool = False,
    ):
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.input_size = input_size
        self.size_consistency_enabled = bool(size_consistency_enabled)
        self.class_names: List[str] = [
            _normalize_class_name(n) for n in (class_names or _DEFAULT_CLASS_NAMES)
        ]

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is not installed. "
                "Run: pip install onnxruntime"
            ) from exc

        path = Path(onnx_path)
        if not path.exists():
            raise FileNotFoundError(
                f"ONNX model not found: {path}\n"
                "Run scripts/convert_to_onnx.py to convert your .pt weights."
            )

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if num_threads is None:
            resolved_threads = max(2, min(os.cpu_count() or 2, 4))
        else:
            resolved_threads = max(1, int(num_threads))
        opts.intra_op_num_threads = resolved_threads
        self.num_threads = resolved_threads

        self.session = ort.InferenceSession(
            str(path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

        meta = self.session.get_modelmeta()
        custom_meta = meta.custom_metadata_map if meta else {}
        if "names" in custom_meta:
            import ast
            try:
                names_dict = ast.literal_eval(custom_meta["names"])
                if isinstance(names_dict, dict):
                    self.class_names = [
                        _normalize_class_name(names_dict[k])
                        for k in sorted(names_dict)
                    ]
                elif isinstance(names_dict, list):
                    self.class_names = [_normalize_class_name(n) for n in names_dict]
            except Exception:
                pass

        inp = self.session.get_inputs()[0]
        self._input_name: str = inp.name
        print(f"ONNX model loaded: {path.name}  |  classes: {self.class_names}")

    def get_class_keys(self) -> List[str]:
        return list(self.class_names)

    def _apply_clahe(self, frame: np.ndarray) -> np.ndarray:
        """Apply LAB-space CLAHE before letterboxing so padding never skews tile histograms."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return cv2.cvtColor(cv2.merge([clahe.apply(l), a, b]), cv2.COLOR_LAB2BGR)

    def _preprocess(
        self, frame: np.ndarray, apply_clahe: bool = True
    ) -> Tuple[np.ndarray, float, int, int]:
        if apply_clahe:
            frame = self._apply_clahe(frame)

        h, w = frame.shape[:2]
        scale = self.input_size / max(h, w)
        new_h, new_w = int(round(h * scale)), int(round(w * scale))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Letterbox pad to square
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_top = (self.input_size - new_h) // 2
        pad_left = (self.input_size - new_w) // 2
        canvas[pad_top : pad_top + new_h, pad_left : pad_left + new_w] = resized

        blob = canvas[..., ::-1].astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis]  # NCHW
        return blob, scale, pad_top, pad_left

    def _nms(
        self,
        boxes: np.ndarray,
        scores: np.ndarray,
        class_ids: Optional[np.ndarray] = None,
    ) -> List[int]:
        # Class-aware NMS (matches Ultralytics default agnostic_nms=False)
        if class_ids is not None:
            offsets = class_ids.astype(np.float32)[:, None] * 7680.0
            nms_boxes = boxes + offsets
        else:
            nms_boxes = boxes

        x1, y1, x2, y2 = nms_boxes[:, 0], nms_boxes[:, 1], nms_boxes[:, 2], nms_boxes[:, 3]
        areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
        order = scores.argsort()[::-1]
        keep: List[int] = []
        while order.size > 0:
            i = order[0]
            keep.append(int(i))
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou < self.iou_threshold]
        return keep

    def detect(self, frame: np.ndarray, preprocess: bool = True) -> List[Dict[str, Any]]:
        orig_h, orig_w = frame.shape[:2]
        blob, scale, pad_top, pad_left = self._preprocess(frame, apply_clahe=preprocess)

        outputs = self.session.run(None, {self._input_name: blob})

        # YOLOv8 output shape: [1, 4+nc, num_anchors]  (transposed in export)
        pred = outputs[0]
        if pred.ndim == 3:
            pred = pred[0]  # remove batch dim → (4+nc, num_anchors) or (num_anchors, 4+nc)
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T  # ensure (num_anchors, 4+nc)

        if pred.shape[0] == 0:
            return []

        boxes_raw = pred[:, :4]
        class_scores = pred[:, 4:]

        # cx,cy,w,h → x1,y1,x2,y2
        cx, cy, bw, bh = boxes_raw[:, 0], boxes_raw[:, 1], boxes_raw[:, 2], boxes_raw[:, 3]
        x1p = cx - bw / 2
        y1p = cy - bh / 2
        x2p = cx + bw / 2
        y2p = cy + bh / 2

        max_scores = class_scores.max(axis=1)
        class_ids = class_scores.argmax(axis=1)
        mask = max_scores >= self.confidence_threshold
        if not mask.any():
            return []

        boxes_f = np.stack([x1p, y1p, x2p, y2p], axis=1)[mask]
        scores_f = max_scores[mask]
        cls_ids_f = class_ids[mask]

        keep = self._nms(boxes_f, scores_f, cls_ids_f)
        detections: List[Dict[str, Any]] = []

        for idx in keep:
            bx1, by1, bx2, by2 = boxes_f[idx]
            # Undo letterbox
            bx1 = (bx1 - pad_left) / scale
            by1 = (by1 - pad_top) / scale
            bx2 = (bx2 - pad_left) / scale
            by2 = (by2 - pad_top) / scale

            x1 = int(np.clip(bx1, 0, orig_w - 1))
            y1 = int(np.clip(by1, 0, orig_h - 1))
            x2 = int(np.clip(bx2, 0, orig_w))
            y2 = int(np.clip(by2, 0, orig_h))

            cls_id = int(cls_ids_f[idx])
            raw_name = (
                self.class_names[cls_id]
                if cls_id < len(self.class_names)
                else "unknown"
            )
            class_name = _normalize_class_name(raw_name)
            color = CLASS_COLORS.get(class_name, CLASS_COLORS["unknown"])

            cx_det = (x1 + x2) // 2
            cy_det = (y1 + y2) // 2
            w_det = x2 - x1
            h_det = y2 - y1

            detections.append(
                {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": float(scores_f[idx]),
                    "class_id": cls_id,
                    "class_name": class_name,
                    "class_display_name": _display_name(class_name),
                    "class_color": color,
                    "center": (cx_det, cy_det),
                    "width": w_det,
                    "height": h_det,
                    "area": w_det * h_det,
                }
            )

        if self.size_consistency_enabled:
            return self._apply_size_consistency(detections, orig_h, orig_w)
        return detections

    def _apply_size_consistency(
        self,
        detections: List[Dict[str, Any]],
        orig_h: int,
        orig_w: int,
    ) -> List[Dict[str, Any]]:
        """
        Relative-size sanity check applied after YOLO inference.

        When the camera is far away every fish appears small in pixels, so
        YOLO may predict a class that matched that pixel scale in training
        (e.g. labelling a post-fingerling as "juvenile" because it resembles
        a juvenile-sized patch from closer footage).

        This check compares each detection's bounding-box area against:
          1. The median area of all detections in this frame (relative rank).
          2. Its fraction of the total frame area (absolute scale guard).

        Only predictions with confidence < 0.70 are adjusted — confident
        model predictions are never overridden.
        """
        if len(detections) < 2:
            return detections

        frame_area = float(orig_h * orig_w)
        areas = np.array([d["area"] for d in detections], dtype=float)
        median_area = float(np.median(areas))
        if median_area < 1:
            return detections

        for d in detections:
            if d["confidence"] >= 0.70:
                continue

            rel_to_median = d["area"] / median_area
            rel_to_frame  = d["area"] / frame_area
            cls = d["class_name"]
            new_cls: Optional[str] = None

            # Fish much smaller than its peers → unlikely to be juvenile
            if cls == "juvenile" and (rel_to_median < 0.35 or rel_to_frame < 0.003):
                new_cls = "post_fingerling"

            # Fish much larger than its peers → unlikely to be a fingerling
            elif cls == "fingerling" and rel_to_median > 3.5:
                new_cls = "post_fingerling"

            if new_cls:
                d["class_name"] = new_cls
                d["class_display_name"] = _display_name(new_cls)
                d["class_color"] = CLASS_COLORS.get(new_cls, CLASS_COLORS["unknown"])

        return detections


class _FallbackDetector:
    """Zero-PyTorch OpenCV MOG2 fallback used only when model weights cannot be loaded."""

    def __init__(self, min_area: int = 100, max_area: int = 10000):
        self.min_area = min_area
        self.max_area = max_area
        self.confidence_threshold = 0.0
        self.iou_threshold = 0.0
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=16, detectShadows=True
        )

    def get_class_keys(self) -> List[str]:
        return list(_DEFAULT_CLASS_NAMES)

    def detect(self, frame: np.ndarray, preprocess: bool = True) -> List[Dict[str, Any]]:
        fg_mask = self.bg_subtractor.apply(frame)
        fg_mask[fg_mask == 127] = 0
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections: List[Dict[str, Any]] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.min_area < area < self.max_area:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = max(w, h) / (min(w, h) + 1e-6)
                if 1.5 < aspect_ratio < 6.0:
                    detections.append({
                        "bbox": [x, y, x + w, y + h],
                        "confidence": 0.7,
                        "class_id": 0,
                        "class_name": "fingerling",
                        "class_display_name": "Fingerling",
                        "class_color": CLASS_COLORS["fingerling"],
                        "center": (x + w // 2, y + h // 2),
                        "width": w,
                        "height": h,
                        "area": w * h,
                    })
        return detections
