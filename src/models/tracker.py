"""
Object Tracker for Fingerling Counting

Implements SORT-based (Simple Online and Realtime Tracking) algorithm
to track fingerlings across frames and count them accurately.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter, defaultdict
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
    class_votes: Counter = field(default_factory=Counter)
    # Sides of the counting line (-1 = before, +1 = after) this track has been
    # observed on. Counting uses this instead of the last step only, so a fish
    # that crosses before it is confirmed is still counted once confirmed.
    sides_seen: set = field(default_factory=set)
    conf_sum: float = 0.0

    def update(self, detection: Dict[str, Any]) -> None:
        """Update track with new detection."""
        self.bbox = detection['bbox']
        self.center = detection['center']
        self.class_name = detection.get('class_name', self.class_name)
        self.class_votes[self.class_name] += 1
        self.class_display_name = detection.get('class_display_name', self.class_display_name)
        self.class_color = detection.get('class_color', self.class_color)
        self.size_category = detection.get('size_category', self.size_category)
        self.size_name = detection.get('size_name', self.size_name)
        self.size_color = detection.get('size_color', self.size_color)
        self.estimated_length_mm = detection.get('estimated_length_mm', self.estimated_length_mm)
        self.confidence = detection.get('confidence', self.confidence)
        self.conf_sum += float(self.confidence)
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
    
    def get_voted_class(self) -> str:
        """
        Return the modal class label over the track's lifetime.

        Per-frame labels flicker on small, fast-moving fish; counting a track
        under its most recent label therefore sorts it by whichever frame
        happened to be last. The majority vote absorbs isolated
        misclassifications. Ties resolve to the label seen first.
        """
        if not self.class_votes:
            return self.class_name or 'unknown'
        return self.class_votes.most_common(1)[0][0]

    @property
    def mean_confidence(self) -> float:
        return self.conf_sum / max(self.hits, 1)

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
        count_min_hits: int = 1,
        count_direction: str = "any"
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
            count_direction: Which line crossings count. "down"/"right" count only
                downstream crossings, "up"/"left" only upstream, "any" counts both.
        """
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.max_distance = max_distance
        self.counting_mode = counting_mode
        self.count_min_hits = max(1, int(count_min_hits))
        self.count_direction = (count_direction or "any").lower()
        
        self.tracks: List[Track] = []
        self.next_id = 1
        self.frame_count = 0
        
        # Counting
        self.counts: Dict[str, int] = defaultdict(int)
        self.counting_line: Optional[Tuple[int, int, int, int]] = None
        self.counting_line_orientation: str = "horizontal"

        # One entry per counted fish, waiting to be collected by drain_events().
        self._pending_events: List[Dict[str, Any]] = []
        self._event_seq = 0

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
        """Compute cost matrix: distance from each track's predicted centre to each detection."""
        predicted = np.array([t.predict() for t in self.tracks], dtype=float).reshape(-1, 2)
        centers = np.array([d['center'] for d in detections], dtype=float).reshape(-1, 2)
        return np.linalg.norm(predicted[:, None, :] - centers[None, :, :], axis=2)
    
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
            conf_sum=float(detection.get('confidence', 0.0)),
            history=[detection['center']],
            class_votes=Counter([detection.get('class_name', 'unknown')])
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
        valid = {"horizontal": ("down", "up", "any"), "vertical": ("right", "left", "any")}
        if self.count_direction not in valid.get(orientation, ()):
            print(f"Warning: count_direction '{self.count_direction}' can never fire on a "
                  f"{orientation} counting line; expected one of {valid.get(orientation)}.")

    def _side_of_line(self, point: Tuple[int, int]) -> int:
        """-1 if the point is before the line (above / left of it), +1 if on or after it."""
        x1, y1, x2, y2 = self.counting_line
        if self.counting_line_orientation == "horizontal":
            return 1 if point[1] >= (y1 + y2) // 2 else -1
        return 1 if point[0] >= (x1 + x2) // 2 else -1

    def _check_line_crossings(self) -> None:
        """
        Count each confirmed track once, when it has been seen on both sides of
        the line and is currently on the side the flow goes to.

        The earlier rule compared only the last two positions of a track that
        was already confirmed. A fish that crossed during its first
        `min_hits` detections, which is common at CPU frame rates, was
        therefore never counted. Remembering every side a track has been seen
        on fixes that, and it still rejects static false positives, which
        never change side.
        """
        if self.counting_line is None:
            return

        horizontal = self.counting_line_orientation == "horizontal"

        for track in self.tracks:
            if track.time_since_update > 0:
                continue  # no fresh position this frame

            side = self._side_of_line(track.center)
            track.sides_seen.add(side)

            if track.counted or not track.is_confirmed(self.min_hits):
                continue
            if len(track.sides_seen) < 2:
                continue

            # Seen on both sides and now on `side`, so it crossed towards `side`.
            if horizontal:
                direction = "down" if side == 1 else "up"
            else:
                direction = "right" if side == 1 else "left"

            # Direction gate: a fish carried back upstream must not be counted,
            # and a static background false positive that drifts across the line
            # is rejected unless it moves the way the flow does.
            if self.count_direction != "any" and direction != self.count_direction:
                continue

            self._record_count(track, direction)

    def _count_unique_tracks(self) -> None:
        """Count each track once after it reaches the configured hit threshold."""
        for track in self.tracks:
            if track.counted:
                continue

            if track.hits < self.count_min_hits:
                continue

            self._record_count(track, None)

    def _record_count(self, track: Track, direction: Optional[str]) -> None:
        """Add a track to the counts and queue a per-fish audit event."""
        track.counted = True
        track.direction = direction
        class_key = track.get_voted_class() or 'unknown'
        self.counts[class_key] += 1
        self.counts['total'] += 1

        self._event_seq += 1
        self._pending_events.append({
            'seq': self._event_seq,
            'frame': self.frame_count,
            'track_id': track.track_id,
            'class': class_key,
            'votes': dict(track.class_votes),
            'hits': track.hits,
            'mean_confidence': round(track.mean_confidence, 4),
            'direction': direction or '',
            'bbox': [int(v) for v in track.bbox],
        })

    def drain_events(self) -> List[Dict[str, Any]]:
        """Return the count events recorded since the last call, and clear them."""
        events, self._pending_events = self._pending_events, []
        return events

    def get_counts(self) -> Dict[str, int]:
        """Get current counts by size category."""
        return dict(self.counts)

    def reset_counts(self) -> None:
        """
        Reset all counts and per-track counted flags.

        Each live track forgets the sides it has already visited, so a fish
        already past the line is not counted again straight after the reset.
        """
        self.counts.clear()
        self._pending_events.clear()
        for track in self.tracks:
            track.counted = False
            track.sides_seen = (
                {self._side_of_line(track.center)} if self.counting_line is not None else set()
            )
    
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
