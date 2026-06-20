"""Models package - Detection, Classification, and Tracking."""

# detector.py requires torch/ultralytics — NOT imported here so ONNX-only
# production environments (Render) never touch those packages.
# Import FingerlingDetector directly where needed: from models.detector import ...
from .size_classifier import SizeClassifier, SizeCategory, AdaptiveSizeClassifier
from .tracker import FingerlingTracker, Track

__all__ = [
    'FingerlingDetector',
    'FingerlingDetectorFallback',
    'SizeClassifier',
    'SizeCategory',
    'AdaptiveSizeClassifier',
    'FingerlingTracker',
    'Track'
]
