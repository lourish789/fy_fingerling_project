"""
Size Classifier for Catfish Fingerlings

This module classifies detected fingerlings into size categories:
- Small (Fry): < 25mm
- Medium (Fingerling): 25-50mm
- Juvenile: 50-100mm
- Adult: > 100mm
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np


class SizeCategory(Enum):
    """Enumeration of fingerling size categories."""
    SMALL = "small"
    MEDIUM = "medium"
    JUVENILE = "juvenile"
    ADULT = "adult"
    UNKNOWN = "unknown"


@dataclass
class SizeClass:
    """Data class representing a size classification."""
    category: SizeCategory
    name: str
    min_area: int
    max_area: int
    min_length_mm: float
    max_length_mm: float
    color: Tuple[int, int, int]
    
    def contains_area(self, area: int) -> bool:
        """Check if an area falls within this size class."""
        return self.min_area <= area < self.max_area
    
    def contains_length(self, length_mm: float) -> bool:
        """Check if a length falls within this size class."""
        return self.min_length_mm <= length_mm < self.max_length_mm


class SizeClassifier:
    """
    Classifier for categorizing fingerlings by size.
    
    Uses bounding box dimensions and optional calibration data
    to estimate real-world sizes and classify fingerlings.
    """
    
    # Default size classes (pixel-based areas)
    DEFAULT_SIZE_CLASSES = {
        SizeCategory.SMALL: SizeClass(
            category=SizeCategory.SMALL,
            name="Small (Fry)",
            min_area=0,
            max_area=500,
            min_length_mm=0,
            max_length_mm=25,
            color=(0, 255, 0)  # Green
        ),
        SizeCategory.MEDIUM: SizeClass(
            category=SizeCategory.MEDIUM,
            name="Medium (Fingerling)",
            min_area=500,
            max_area=1500,
            min_length_mm=25,
            max_length_mm=50,
            color=(0, 255, 255)  # Yellow
        ),
        SizeCategory.JUVENILE: SizeClass(
            category=SizeCategory.JUVENILE,
            name="Juvenile",
            min_area=1500,
            max_area=4000,
            min_length_mm=50,
            max_length_mm=100,
            color=(0, 165, 255)  # Orange
        ),
        SizeCategory.ADULT: SizeClass(
            category=SizeCategory.ADULT,
            name="Adult",
            min_area=4000,
            max_area=999999,
            min_length_mm=100,
            max_length_mm=999,
            color=(0, 0, 255)  # Red
        ),
    }
    
    def __init__(
        self,
        size_classes: Optional[Dict[SizeCategory, SizeClass]] = None,
        pixels_per_mm: float = 5.0,
        use_length_estimation: bool = True
    ):
        """
        Initialize the size classifier.
        
        Args:
            size_classes: Custom size class definitions.
            pixels_per_mm: Calibration factor for real-world size estimation.
            use_length_estimation: Whether to use length-based classification.
        """
        self.size_classes = size_classes or self.DEFAULT_SIZE_CLASSES
        self.pixels_per_mm = pixels_per_mm
        self.use_length_estimation = use_length_estimation
        
    def classify(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify a single detection by size.
        
        Args:
            detection: Detection dictionary containing bbox, area, etc.
            
        Returns:
            Detection dictionary with added size classification.
        """
        area = detection.get('area', 0)
        width = detection.get('width', 0)
        height = detection.get('height', 0)
        
        # Estimate length (major axis of bounding box)
        length_pixels = max(width, height)
        length_mm = length_pixels / self.pixels_per_mm
        
        # Classify based on area or length
        size_class = self._classify_by_area(area)
        
        if self.use_length_estimation:
            length_class = self._classify_by_length(length_mm)
            # Use length-based if available and more specific
            if length_class.category != SizeCategory.UNKNOWN:
                size_class = length_class
        
        # Add classification to detection
        detection['size_category'] = size_class.category.value
        detection['size_name'] = size_class.name
        detection['size_color'] = size_class.color
        detection['estimated_length_mm'] = round(length_mm, 1)
        
        return detection
    
    def classify_batch(
        self,
        detections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Classify multiple detections.
        
        Args:
            detections: List of detection dictionaries.
            
        Returns:
            List of detections with size classifications.
        """
        return [self.classify(d) for d in detections]
    
    def _classify_by_area(self, area: int) -> SizeClass:
        """Classify based on bounding box area."""
        for size_class in self.size_classes.values():
            if size_class.contains_area(area):
                return size_class
        return SizeClass(
            category=SizeCategory.UNKNOWN,
            name="Unknown",
            min_area=0,
            max_area=0,
            min_length_mm=0,
            max_length_mm=0,
            color=(128, 128, 128)
        )
    
    def _classify_by_length(self, length_mm: float) -> SizeClass:
        """Classify based on estimated length."""
        for size_class in self.size_classes.values():
            if size_class.contains_length(length_mm):
                return size_class
        return SizeClass(
            category=SizeCategory.UNKNOWN,
            name="Unknown",
            min_area=0,
            max_area=0,
            min_length_mm=0,
            max_length_mm=0,
            color=(128, 128, 128)
        )
    
    def calibrate(
        self,
        reference_length_pixels: float,
        reference_length_mm: float
    ) -> None:
        """
        Calibrate the classifier using a known reference.
        
        Args:
            reference_length_pixels: Length of reference object in pixels.
            reference_length_mm: Actual length of reference object in mm.
        """
        self.pixels_per_mm = reference_length_pixels / reference_length_mm
        print(f"Calibrated: {self.pixels_per_mm:.2f} pixels per mm")
    
    def get_size_distribution(
        self,
        detections: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Get distribution of sizes from classified detections.
        
        Args:
            detections: List of classified detections.
            
        Returns:
            Dictionary mapping size categories to counts.
        """
        distribution = {
            'small': 0,
            'medium': 0,
            'juvenile': 0,
            'adult': 0,
            'unknown': 0
        }
        
        for detection in detections:
            category = detection.get('size_category', 'unknown')
            if category in distribution:
                distribution[category] += 1
            else:
                distribution['unknown'] += 1
        
        return distribution
    
    def update_thresholds(
        self,
        category: SizeCategory,
        min_area: Optional[int] = None,
        max_area: Optional[int] = None,
        min_length_mm: Optional[float] = None,
        max_length_mm: Optional[float] = None
    ) -> None:
        """
        Update thresholds for a size category.
        
        Args:
            category: Size category to update.
            min_area: New minimum area threshold.
            max_area: New maximum area threshold.
            min_length_mm: New minimum length threshold.
            max_length_mm: New maximum length threshold.
        """
        if category in self.size_classes:
            size_class = self.size_classes[category]
            if min_area is not None:
                size_class.min_area = min_area
            if max_area is not None:
                size_class.max_area = max_area
            if min_length_mm is not None:
                size_class.min_length_mm = min_length_mm
            if max_length_mm is not None:
                size_class.max_length_mm = max_length_mm


class AdaptiveSizeClassifier(SizeClassifier):
    """
    Adaptive classifier that learns size thresholds from data.
    
    Useful when the camera setup changes or for automatic calibration.
    """
    
    def __init__(self, **kwargs):
        """Initialize with adaptive learning capabilities."""
        super().__init__(**kwargs)
        self.area_history: List[int] = []
        self.length_history: List[float] = []
        self.min_samples_for_adaptation = 100
    
    def add_sample(self, area: int, length_mm: float) -> None:
        """Add a sample for adaptive learning."""
        self.area_history.append(area)
        self.length_history.append(length_mm)
    
    def adapt_thresholds(self) -> bool:
        """
        Adapt thresholds based on collected samples.
        
        Uses percentile-based clustering to determine size boundaries.
        
        Returns:
            True if adaptation was successful, False otherwise.
        """
        if len(self.area_history) < self.min_samples_for_adaptation:
            return False
        
        areas = np.array(self.area_history)
        
        # Use percentiles to determine boundaries
        percentiles = [25, 50, 75]
        boundaries = np.percentile(areas, percentiles)
        
        # Update thresholds
        self.size_classes[SizeCategory.SMALL].max_area = int(boundaries[0])
        self.size_classes[SizeCategory.MEDIUM].min_area = int(boundaries[0])
        self.size_classes[SizeCategory.MEDIUM].max_area = int(boundaries[1])
        self.size_classes[SizeCategory.JUVENILE].min_area = int(boundaries[1])
        self.size_classes[SizeCategory.JUVENILE].max_area = int(boundaries[2])
        self.size_classes[SizeCategory.ADULT].min_area = int(boundaries[2])
        
        return True
    
    def reset_history(self) -> None:
        """Reset the sample history."""
        self.area_history.clear()
        self.length_history.clear()
