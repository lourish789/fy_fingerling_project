"""
Object Tracker for Fingerling Counting

Implements SORT-based (Simple Online and Realtime Tracking) algorithm
to track fingerlings across frames and count them accurately.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from scipy.optimize import linear_sum_assignment


@dataclass
class Track:
    """Represents a tracked object."""
    track_id: int
    bbox: List[int]
    center: Tuple[int, int]
    class_name: str = "unknown"
    class_display_name: str = "Unknown"
    class_color: Tuple[int, int, int] = (128, 128, 128)
    size_category: str = "unknown"
    size_name: str = "Unknown"
    size_color: Tuple[int, int, int] = (128, 128, 128)
    estimated_length_mm: float = 0.0
    confidence: float = 0.0
    age: int = 0
    hits: int = 1
    time_since_update: int = 0
    history: List[Tuple[int, int]] = field(default_factory=list)
    counted: bool = False
    direction: Optional[str] = None  # "up", "down", "left", "right"
    
    def update(self, detection: Dict[str, Any]) -> None:
        """Update track with new detection."""
        self.bbox = detection['bbox']
        self.center = detection['center']
        self.class_name = detection.get('class_name', self.class_name)
        self.class_display_name = detection.get('class_display_name', self.class_display_name)
        self.class_color = detection.get('class_color', self.class_color)
        self.size_category = detection.get('size_category', self.size_category)
        self.size_name = detection.get('size_name', self.size_name)
        self.size_color = detection.get('size_color', self.size_color)
        self.estimated_length_mm = detection.get('estimated_length_mm', self.estimated_length_mm)
        self.confidence = detection.get('confidence', self.confidence)
        self.hits += 1
        self.time_since_update = 0
        self.history.append(self.center)
        
        # Limit history length
        if len(self.history) > 30:
            self.history = self.history[-30:]
    
    def predict(self) -> Tuple[int, int]:
        """Predict next position using simple linear motion model."""
        if len(self.history) < 2:
            return self.center
        
        # Use last two positions to predict velocity
        dx = self.history[-1][0] - self.history[-2][0]
        dy = self.history[-1][1] - self.history[-2][1]
        
        predicted_x = self.center[0] + dx
        predicted_y = self.center[1] + dy
        
        return (predicted_x, predicted_y)
    
    def mark_missed(self) -> None:
        """Mark frame where track was not detected."""
        self.age += 1
        self.time_since_update += 1
    
    def is_confirmed(self, min_hits: int = 3) -> bool:
        """Check if track is confirmed (enough detections)."""
        return self.hits >= min_hits
    
    def get_direction(self) -> Optional[str]:
        """Determine movement direction based on history."""
        if len(self.history) < 5:
            return None
        
        # Calculate overall movement
        start = self.history[0]
        end = self.history[-1]
        
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        if abs(dx) > abs(dy):
            self.direction = "right" if dx > 0 else "left"
        else:
            self.direction = "down" if dy > 0 else "up"
        
        return self.direction


class FingerlingTracker:
    """
    SORT-based tracker for fingerling counting.
    
    Features:
    - Hungarian algorithm for detection-to-track association
    - Simple motion prediction
    - Track lifecycle management
    - Counting line/region support
    """
    
    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
        max_distance: int = 100,
        counting_mode: str = "unique_track",
        count_min_hits: int = 1
    ):
        """
        Initialize the tracker.
        
        Args:
            max_age: Maximum frames to keep track without detection.
            min_hits: Minimum detections before track is confirmed.
            iou_threshold: Minimum IOU for association.
            max_distance: Maximum distance for center-based association.
            counting_mode: Counting strategy: "unique_track" or "line_crossing".
            count_min_hits: Minimum hits before a track contributes to cumulative counts.
        """
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.max_distance = max_distance
        self.counting_mode = counting_mode
        self.count_min_hits = max(1, int(count_min_hits))
        
        self.tracks: List[Track] = []
        self.next_id = 1
        self.frame_count = 0
        
        # Counting
        self.counts: Dict[str, int] = defaultdict(int)
        self.counting_line: Optional[Tuple[int, int, int, int]] = None
        self.counting_line_orientation: str = "horizontal"
    
    def update(self, detections: List[Dict[str, Any]]) -> List[Track]:
        """
        Update tracks with new detections.
        
        Args:
            detections: List of detection dictionaries.
            
        Returns:
            List of active tracks.
        """
        self.frame_count += 1
        
        # Predict new positions for existing tracks
        for track in self.tracks:
            track.mark_missed()
        
        if detections:
            if not self.tracks:
                # No existing tracks - create new ones.
                for detection in detections:
                    self._create_track(detection)
            else:
                # Calculate cost matrix (using center distance)
                cost_matrix = self._compute_cost_matrix(detections)
                
                # Hungarian algorithm for optimal assignment
                track_indices, det_indices = linear_sum_assignment(cost_matrix)
                
                # Process matched pairs
                unmatched_detections = set(range(len(detections)))
                unmatched_tracks = set(range(len(self.tracks)))
                
                for t_idx, d_idx in zip(track_indices, det_indices):
                    if cost_matrix[t_idx, d_idx] < self.max_distance:
                        self.tracks[t_idx].update(detections[d_idx])
                        unmatched_detections.discard(d_idx)
                        unmatched_tracks.discard(t_idx)
                
                # Create new tracks for unmatched detections
                for d_idx in unmatched_detections:
                    self._create_track(detections[d_idx])
        
        # Update cumulative counts.
        if self.counting_mode == "line_crossing":
            if self.counting_line is not None:
                self._check_line_crossings()
            else:
                # Fallback prevents silent under-counting if line is not configured.
                self._count_unique_tracks()
        else:
            self._count_unique_tracks()
        
        # Remove old tracks
        self._remove_old_tracks()
        
        return self.tracks
    
    def _compute_cost_matrix(
        self,
        detections: List[Dict[str, Any]]
    ) -> np.ndarray:
        """Compute cost matrix based on center distances."""
        n_tracks = len(self.tracks)
        n_dets = len(detections)
        
        cost_matrix = np.full((n_tracks, n_dets), self.max_distance * 2)
        
        for t_idx, track in enumerate(self.tracks):
            predicted = track.predict()
            for d_idx, det in enumerate(detections):
                det_center = det['center']
                distance = np.sqrt(
                    (predicted[0] - det_center[0]) ** 2 +
                    (predicted[1] - det_center[1]) ** 2
                )
                cost_matrix[t_idx, d_idx] = distance
        
        return cost_matrix
    
    def _compute_iou(
        self,
        bbox1: List[int],
        bbox2: List[int]
    ) -> float:
        """Compute Intersection over Union between two bboxes."""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _create_track(self, detection: Dict[str, Any]) -> Track:
        """Create a new track from detection."""
        track = Track(
            track_id=self.next_id,
            bbox=detection['bbox'],
            center=detection['center'],
            class_name=detection.get('class_name', 'unknown'),
            class_display_name=detection.get('class_display_name', 'Unknown'),
            class_color=detection.get('class_color', (128, 128, 128)),
            size_category=detection.get('size_category', 'unknown'),
            size_name=detection.get('size_name', 'Unknown'),
            size_color=detection.get('size_color', (128, 128, 128)),
            estimated_length_mm=detection.get('estimated_length_mm', 0.0),
            confidence=detection.get('confidence', 0.0),
            history=[detection['center']]
        )
        self.tracks.append(track)
        self.next_id += 1
        return track
    
    def _remove_old_tracks(self) -> None:
        """Remove tracks that haven't been updated recently."""
        self.tracks = [
            t for t in self.tracks
            if t.time_since_update < self.max_age
        ]
    
    def set_counting_line(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        orientation: str = "horizontal"
    ) -> None:
        """
        Set the counting line position.
        
        Args:
            x1, y1: Start point of line.
            x2, y2: End point of line.
            orientation: "horizontal" or "vertical".
        """
        self.counting_line = (x1, y1, x2, y2)
        self.counting_line_orientation = orientation
    
    def _check_line_crossings(self) -> None:
        """Check if any tracks crossed the counting line."""
        if self.counting_line is None:
            return
        
        x1, y1, x2, y2 = self.counting_line
        
        for track in self.tracks:
            if track.counted or len(track.history) < 2:
                continue
            
            if not track.is_confirmed(self.min_hits):
                continue
            
            prev_pos = track.history[-2]
            curr_pos = track.history[-1]
            
            crossed = False
            
            if self.counting_line_orientation == "horizontal":
                # Check vertical crossing of horizontal line
                line_y = (y1 + y2) // 2
                if (prev_pos[1] < line_y <= curr_pos[1] or
                    prev_pos[1] > line_y >= curr_pos[1]):
                    crossed = True
            else:
                # Check horizontal crossing of vertical line
                line_x = (x1 + x2) // 2
                if (prev_pos[0] < line_x <= curr_pos[0] or
                    prev_pos[0] > line_x >= curr_pos[0]):
                    crossed = True
            
            if crossed:
                track.counted = True
                track.get_direction()
                class_key = track.class_name or 'unknown'
                self.counts[class_key] += 1
                self.counts['total'] += 1

    def _count_unique_tracks(self) -> None:
        """Count each track once after it reaches the configured hit threshold."""
        for track in self.tracks:
            if track.counted:
                continue

            if track.hits < self.count_min_hits:
                continue

            track.counted = True
            class_key = track.class_name or 'unknown'
            self.counts[class_key] += 1
            self.counts['total'] += 1
    
    def get_counts(self) -> Dict[str, int]:
        """Get current counts by size category."""
        return dict(self.counts)
    
    def reset_counts(self) -> None:
        """Reset all counts and per-track counted flags."""
        self.counts.clear()
        for track in self.tracks:
            track.counted = False
    
    def get_active_tracks(self) -> List[Track]:
        """Get list of confirmed, active tracks."""
        return [
            t for t in self.tracks
            if t.is_confirmed(self.min_hits) and t.time_since_update == 0
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        active = self.get_active_tracks()
        size_dist = defaultdict(int)
        
        for track in active:
            class_key = track.class_name or 'unknown'
            size_dist[class_key] += 1
        
        return {
            'frame': self.frame_count,
            'total_tracks': len(self.tracks),
            'active_tracks': len(active),
            'counts': self.get_counts(),
            'current_distribution': dict(size_dist)
        }
