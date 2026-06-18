"""
ONNX-Runtime Detector — production-grade, CPU-only inference.

Drop-in replacement for FingerlingDetector that requires only
onnxruntime (~150 MB) instead of PyTorch + Ultralytics (~1.8 GB).

Usage:
    detector = OnnxFingerlingDetector("models/best.onnx")
    detections = detector.detect(frame)   # same API as FingerlingDetector
"""

from __future__ import annotations

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
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        input_size: int = 640,
        class_names: Optional[List[str]] = None,
    ):
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.input_size = input_size
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
        opts.intra_op_num_threads = 2

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

    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        h, w = frame.shape[:2]
        scale = self.input_size / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(frame, (new_w, new_h))

        # Letterbox pad to square
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_top = (self.input_size - new_h) // 2
        pad_left = (self.input_size - new_w) // 2
        canvas[pad_top : pad_top + new_h, pad_left : pad_left + new_w] = resized

        # CLAHE contrast enhancement (helps murky water)
        lab = cv2.cvtColor(canvas, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        canvas = cv2.cvtColor(cv2.merge([clahe.apply(l), a, b]), cv2.COLOR_LAB2BGR)

        blob = canvas[..., ::-1].astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis]  # NCHW
        return blob, scale, pad_top, pad_left

    def _nms(self, boxes: np.ndarray, scores: np.ndarray) -> List[int]:
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep: List[int] = []
        while order.size > 0:
            i = order[0]
            keep.append(int(i))
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou < self.iou_threshold]
        return keep

    def detect(self, frame: np.ndarray, preprocess: bool = True) -> List[Dict[str, Any]]:
        orig_h, orig_w = frame.shape[:2]
        blob, scale, pad_top, pad_left = self._preprocess(frame)

        outputs = self.session.run(None, {self._input_name: blob})

        # YOLOv8 output shape: [1, 4+nc, num_anchors]  (transposed in export)
        pred = outputs[0]
        if pred.ndim == 3:
            pred = pred[0]  # remove batch dim → (4+nc, num_anchors) or (num_anchors, 4+nc)
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T  # ensure (num_anchors, 4+nc)

        if pred.shape[0] == 0:
            return []

        num_classes = pred.shape[1] - 4
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

        keep = self._nms(boxes_f, scores_f)
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

        return detections
