"""
Catfish Fingerling Detection Model

This module provides the YOLO-based detection model for identifying
catfish fingerlings in video frames.
"""

import torch
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from ultralytics import YOLO
import cv2


CLASS_COLORS = {
    'fingerling': (0, 255, 0),
    'post_fingerling': (255, 191, 0),
    'juvenile': (0, 140, 255),
    'unknown': (160, 160, 160)
}


class FingerlingDetector:
    """
    YOLO-based detector for catfish fingerlings.
    
    This detector is optimized for detecting fish in water/tank environments
    and can work with both pre-trained weights and custom-trained models.
    """
    
    def __init__(
        self,
        weights_path: Optional[str] = None,
        model_engine: str = "ultralytics",
        pretrained_model: str = "yolov26n.pt",
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        device: str = "auto",
        dark_surface_filter_enabled: bool = False,
        dark_surface_min_value_mean: float = 45.0,
        dark_surface_max_value_std: float = 28.0,
        dark_surface_max_saturation_mean: float = 65.0
    ):
        """
        Initialize the fingerling detector.
        
        Args:
            weights_path: Path to model weights. If None, uses configured pretrained checkpoint.
            model_engine: Inference backend selector. Currently supports "ultralytics".
            pretrained_model: Default model checkpoint when no explicit weights are provided.
            confidence_threshold: Minimum confidence for detections.
            iou_threshold: IOU threshold for NMS.
            device: Device to run inference on ("auto", "cuda", "cpu").
            dark_surface_filter_enabled: Reject low-texture dark regions often confused as fish.
            dark_surface_min_value_mean: Minimum HSV-V mean before keeping a detection.
            dark_surface_max_value_std: Maximum HSV-V std for rejection decision.
            dark_surface_max_saturation_mean: Maximum HSV-S mean for rejection decision.
        """
        self.model_engine = model_engine
        self.pretrained_model = pretrained_model
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = self._get_device(device)
        self.dark_surface_filter_enabled = dark_surface_filter_enabled
        self.dark_surface_min_value_mean = dark_surface_min_value_mean
        self.dark_surface_max_value_std = dark_surface_max_value_std
        self.dark_surface_max_saturation_mean = dark_surface_max_saturation_mean
        
        # Load model
        self.model = self._load_model(weights_path)
        self.class_names = self._load_class_names()
        self.class_key_to_display = {
            key: self._display_name(key) for key in self.class_names
        }
        
    def _get_device(self, device: str) -> str:
        """Determine the best available device."""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device
    
    def _load_model(self, weights_path: Optional[str]) -> YOLO:
        """Load the YOLO model with checkpoint fallback support."""
        if self.model_engine.lower() != "ultralytics":
            raise ValueError(
                f"Unsupported model_engine='{self.model_engine}'. Supported: ultralytics"
            )

        if weights_path and Path(weights_path).exists():
            print(f"Loading custom weights from: {weights_path}")
            model = YOLO(weights_path)
        else:
            # Prefer user-configured checkpoint first, then fallback to widely available default.
            candidates = [self.pretrained_model, "yolov8n.pt"]
            last_error: Optional[Exception] = None
            model = None

            for checkpoint in candidates:
                try:
                    print(f"Loading pretrained model checkpoint: {checkpoint}")
                    model = YOLO(checkpoint)
                    break
                except Exception as exc:
                    last_error = exc
                    print(f"Warning: failed to load checkpoint '{checkpoint}': {exc}")

            if model is None:
                raise RuntimeError(
                    "Unable to load any pretrained model checkpoint. "
                    "Tried: " + ", ".join(candidates)
                ) from last_error
            
        model.to(self.device)
        return model

    def _load_class_names(self) -> List[str]:
        """Load and normalize class names from the model."""
        names = getattr(self.model, 'names', None)
        if isinstance(names, dict):
            ordered = [names[k] for k in sorted(names.keys())]
        elif isinstance(names, list):
            ordered = names
        else:
            ordered = ['fingerling', 'post_fingerling', 'juvenile']

        normalized = []
        for raw_name in ordered:
            class_key = self._normalize_class_name(str(raw_name))
            if class_key not in normalized:
                normalized.append(class_key)

        if 'fingerling' not in normalized:
            normalized.append('fingerling')

        return normalized

    def _normalize_class_name(self, name: str) -> str:
        """Normalize raw class names to stable keys used in counting/UI."""
        normalized = name.strip().lower().replace('-', '_').replace(' ', '_')

        if 'juvenile' in normalized and ('post' in normalized or 'pos' in normalized):
            return 'post_fingerling'
        if 'post' in normalized or 'posfinger' in normalized:
            return 'post_fingerling'
        if normalized == 'juvenile' or normalized.startswith('juvenile_'):
            return 'juvenile'
        if 'fingerling' in normalized:
            return 'fingerling'
        return normalized if normalized else 'unknown'

    def _display_name(self, class_key: str) -> str:
        if class_key == 'post_fingerling':
            return 'Post-Fingerling'
        if class_key == 'fingerling':
            return 'Fingerling'
        if class_key == 'juvenile':
            return 'Juvenile'
        return class_key.replace('_', ' ').title()

    def get_class_keys(self) -> List[str]:
        """Return canonical class keys predicted by this detector."""
        return list(self.class_names)

    def _is_dark_surface_false_positive(self, frame: np.ndarray, bbox: List[int]) -> bool:
        """Heuristic filter to suppress very dark, low-texture non-fish surfaces."""
        if not self.dark_surface_filter_enabled:
            return False

        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(0, min(x2, w))
        y2 = max(0, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return True

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return True

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]

        value_mean = float(np.mean(val))
        value_std = float(np.std(val))
        sat_mean = float(np.mean(sat))

        return (
            value_mean < self.dark_surface_min_value_mean
            and value_std < self.dark_surface_max_value_std
            and sat_mean < self.dark_surface_max_saturation_mean
        )
    
    def detect(
        self,
        frame: np.ndarray,
        preprocess: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Detect fingerlings in a single frame.
        
        Args:
            frame: BGR image as numpy array.
            preprocess: Whether to apply preprocessing.
            
        Returns:
            List of detection dictionaries containing:
                - bbox: [x1, y1, x2, y2]
                - confidence: float
                - class_id: int
                - center: (cx, cy)
                - area: int (bbox area in pixels)
        """
        if preprocess:
            frame = self._preprocess(frame)
        
        # Run inference
        results = self.model.predict(
            frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            verbose=False,
            device=self.device
        )
        
        detections = []
        
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
                
            for i in range(len(boxes)):
                # Get bounding box coordinates
                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)

                if self._is_dark_surface_false_positive(frame, [x1, y1, x2, y2]):
                    continue
                
                # Get confidence and class
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                raw_name = result.names.get(cls_id, 'unknown') if hasattr(result, 'names') else 'unknown'
                class_name = self._normalize_class_name(str(raw_name))
                class_display_name = self.class_key_to_display.get(class_name, self._display_name(class_name))
                class_color = CLASS_COLORS.get(class_name, CLASS_COLORS['unknown'])
                
                # Calculate center and area
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                width = x2 - x1
                height = y2 - y1
                area = width * height
                
                detections.append({
                    'bbox': [x1, y1, x2, y2],
                    'confidence': conf,
                    'class_id': cls_id,
                    'class_name': class_name,
                    'class_display_name': class_display_name,
                    'class_color': class_color,
                    'center': (cx, cy),
                    'width': width,
                    'height': height,
                    'area': area
                })
        
        return detections
    
    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Preprocess frame for better detection in water environments.
        
        Args:
            frame: BGR image as numpy array.
            
        Returns:
            Preprocessed frame.
        """
        # Apply CLAHE for contrast enhancement (helpful in murky water)
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        return enhanced
    
    def detect_batch(
        self,
        frames: List[np.ndarray],
        preprocess: bool = True
    ) -> List[List[Dict[str, Any]]]:
        """
        Detect fingerlings in multiple frames (batch processing).
        
        Args:
            frames: List of BGR images.
            preprocess: Whether to apply preprocessing.
            
        Returns:
            List of detection lists for each frame.
        """
        if preprocess:
            frames = [self._preprocess(f) for f in frames]
        
        results = self.model.predict(
            frames,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            verbose=False,
            device=self.device
        )
        
        all_detections = []
        
        for result in results:
            frame_detections = []
            boxes = result.boxes
            
            if boxes is not None:
                for i in range(len(boxes)):
                    xyxy = boxes.xyxy[i].cpu().numpy()
                    x1, y1, x2, y2 = map(int, xyxy)

                    if self._is_dark_surface_false_positive(frames[len(all_detections)], [x1, y1, x2, y2]):
                        continue
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    raw_name = result.names.get(cls_id, 'unknown') if hasattr(result, 'names') else 'unknown'
                    class_name = self._normalize_class_name(str(raw_name))
                    class_display_name = self.class_key_to_display.get(class_name, self._display_name(class_name))
                    class_color = CLASS_COLORS.get(class_name, CLASS_COLORS['unknown'])
                    
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    width = x2 - x1
                    height = y2 - y1
                    area = width * height
                    
                    frame_detections.append({
                        'bbox': [x1, y1, x2, y2],
                        'confidence': conf,
                        'class_id': cls_id,
                        'class_name': class_name,
                        'class_display_name': class_display_name,
                        'class_color': class_color,
                        'center': (cx, cy),
                        'width': width,
                        'height': height,
                        'area': area
                    })
            
            all_detections.append(frame_detections)
        
        return all_detections


class FingerlingDetectorFallback:
    """
    Fallback detector using traditional computer vision techniques.
    
    Use this when deep learning model is not available or for quick testing.
    Less accurate but works without GPU.
    """
    
    def __init__(
        self,
        min_area: int = 100,
        max_area: int = 10000,
        threshold_value: int = 50
    ):
        """
        Initialize fallback detector.
        
        Args:
            min_area: Minimum contour area to consider.
            max_area: Maximum contour area to consider.
            threshold_value: Threshold for binary conversion.
        """
        self.min_area = min_area
        self.max_area = max_area
        self.threshold_value = threshold_value
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=16,
            detectShadows=True
        )
    
    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect fingerlings using traditional CV methods.
        
        Args:
            frame: BGR image as numpy array.
            
        Returns:
            List of detection dictionaries.
        """
        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(frame)
        
        # Remove shadows (marked as 127 in MOG2)
        fg_mask[fg_mask == 127] = 0
        
        # Morphological operations to clean up mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(
            fg_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        detections = []
        
        for contour in contours:
            area = cv2.contourArea(contour)
            
            if self.min_area < area < self.max_area:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter based on aspect ratio (fish are elongated)
                aspect_ratio = max(w, h) / (min(w, h) + 1e-6)
                if 1.5 < aspect_ratio < 6.0:
                    cx = x + w // 2
                    cy = y + h // 2
                    
                    detections.append({
                        'bbox': [x, y, x + w, y + h],
                        'confidence': 0.7,  # Fixed confidence for CV method
                        'class_id': 0,
                        'class_name': 'fingerling',
                        'class_display_name': 'Fingerling',
                        'class_color': CLASS_COLORS['fingerling'],
                        'center': (cx, cy),
                        'width': w,
                        'height': h,
                        'area': area
                    })
        
        return detections
