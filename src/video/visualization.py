"""
Visualization Module for Fingerling Counter

Provides drawing utilities for bounding boxes, tracks,
counting lines, and statistics overlay.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class VisualizationConfig:
    """Configuration for visualization."""
    show_bounding_boxes: bool = True
    show_tracks: bool = True
    show_counting_line: bool = True
    show_size_labels: bool = True
    show_statistics: bool = True
    font_scale: float = 0.6
    line_thickness: int = 2
    track_history_length: int = 30


class Visualizer:
    """
    Visualization utilities for the fingerling counter.
    """
    
    # Color palette for different size categories
    SIZE_COLORS = {
        'fingerling': (0, 255, 0),
        'post_fingerling': (255, 191, 0),
        'juvenile': (0, 165, 255),
        'unknown': (128, 128, 128)
    }
    
    def __init__(self, config: Optional[VisualizationConfig] = None):
        """
        Initialize visualizer.
        
        Args:
            config: Visualization configuration.
        """
        self.config = config or VisualizationConfig()
        self.font = cv2.FONT_HERSHEY_SIMPLEX
    
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Draw detection bounding boxes on frame.
        
        Args:
            frame: Input frame.
            detections: List of detection dictionaries.
            
        Returns:
            Annotated frame.
        """
        annotated = frame.copy()
        
        for det in detections:
            bbox = det['bbox']
            x1, y1, x2, y2 = bbox
            
            # Get color based on model class
            class_key = det.get('class_name', det.get('size_category', 'unknown'))
            color = det.get('class_color', det.get('size_color', self.SIZE_COLORS.get(class_key, (128, 128, 128))))
            
            # Draw bounding box
            cv2.rectangle(
                annotated,
                (x1, y1),
                (x2, y2),
                color,
                self.config.line_thickness
            )
            
            # Draw label
            if self.config.show_size_labels:
                size_name = det.get('class_display_name', det.get('size_name', 'Unknown'))
                conf = det.get('confidence', 0)
                length_mm = det.get('estimated_length_mm', 0)
                
                label = f"{size_name} {conf:.2f}"
                if length_mm > 0:
                    label += f" ({length_mm:.0f}mm)"
                
                # Calculate label position
                (label_w, label_h), baseline = cv2.getTextSize(
                    label, self.font, self.config.font_scale, 1
                )
                
                # Draw label background
                cv2.rectangle(
                    annotated,
                    (x1, y1 - label_h - 10),
                    (x1 + label_w + 4, y1),
                    color,
                    -1
                )
                
                # Draw label text
                cv2.putText(
                    annotated,
                    label,
                    (x1 + 2, y1 - 5),
                    self.font,
                    self.config.font_scale,
                    (0, 0, 0),
                    1
                )
        
        return annotated
    
    def draw_tracks(
        self,
        frame: np.ndarray,
        tracks: List[Any]  # List of Track objects
    ) -> np.ndarray:
        """
        Draw tracking information on frame.
        
        Args:
            frame: Input frame.
            tracks: List of Track objects.
            
        Returns:
            Annotated frame.
        """
        annotated = frame.copy()
        
        for track in tracks:
            if track.time_since_update > 0:
                continue  # Skip tracks not detected in current frame
            
            # Get color
            color = track.class_color if hasattr(track, 'class_color') else (0, 255, 0)
            
            # Draw bounding box
            x1, y1, x2, y2 = track.bbox
            cv2.rectangle(
                annotated,
                (x1, y1),
                (x2, y2),
                color,
                self.config.line_thickness
            )
            
            # Draw track ID
            label = f"ID:{track.track_id}"
            if hasattr(track, 'class_display_name'):
                label += f" {track.class_display_name}"
            
            cv2.putText(
                annotated,
                label,
                (x1, y1 - 10),
                self.font,
                self.config.font_scale,
                color,
                2
            )
            
            # Draw track history (trail)
            if self.config.show_tracks and len(track.history) > 1:
                history = track.history[-self.config.track_history_length:]
                for i in range(1, len(history)):
                    # Fade effect - older points are more transparent
                    alpha = i / len(history)
                    pt1 = history[i - 1]
                    pt2 = history[i]
                    cv2.line(
                        annotated,
                        pt1,
                        pt2,
                        color,
                        max(1, int(self.config.line_thickness * alpha))
                    )
            
            # Draw center point
            cv2.circle(annotated, track.center, 4, color, -1)
            
            # Draw counted indicator
            if track.counted:
                cv2.circle(
                    annotated,
                    track.center,
                    10,
                    (0, 255, 0),
                    2
                )
        
        return annotated
    
    def draw_counting_line(
        self,
        frame: np.ndarray,
        line: Tuple[int, int, int, int],
        orientation: str = "horizontal"
    ) -> np.ndarray:
        """
        Draw counting line on frame.
        
        Args:
            frame: Input frame.
            line: Line coordinates (x1, y1, x2, y2).
            orientation: Line orientation.
            
        Returns:
            Annotated frame.
        """
        annotated = frame.copy()
        
        x1, y1, x2, y2 = line
        
        # Draw line
        cv2.line(
            annotated,
            (x1, y1),
            (x2, y2),
            (0, 255, 255),  # Yellow
            3
        )
        
        # Draw arrows to indicate counting direction
        mid_x = (x1 + x2) // 2
        mid_y = (y1 + y2) // 2
        
        if orientation == "horizontal":
            # Arrows pointing up and down
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x, mid_y - 20), (0, 255, 255), 2)
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x, mid_y + 20), (0, 255, 255), 2)
        else:
            # Arrows pointing left and right
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x - 20, mid_y), (0, 255, 255), 2)
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x + 20, mid_y), (0, 255, 255), 2)
        
        return annotated
    
    def draw_statistics(
        self,
        frame: np.ndarray,
        stats: Dict[str, Any],
        position: str = "top-left"
    ) -> np.ndarray:
        """
        Draw statistics overlay on frame.
        
        Args:
            frame: Input frame.
            stats: Statistics dictionary.
            position: Position of overlay.
            
        Returns:
            Annotated frame.
        """
        annotated = frame.copy()
        
        # Prepare text lines
        lines = []
        
        # Counts
        counts = stats.get('counts', {})
        lines.append(f"Total: {counts.get('total', 0)}")
        preferred = ['fingerling', 'post_fingerling', 'juvenile', 'unknown']
        for key in preferred:
            if key in counts:
                lines.append(f"{key.replace('_', ' ').title()}: {counts.get(key, 0)}")
        for key, value in counts.items():
            if key in preferred or key == 'total':
                continue
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
        
        # Current frame info
        if 'frame' in stats:
            lines.append(f"Frame: {stats['frame']}")
        if 'active_tracks' in stats:
            lines.append(f"Active: {stats['active_tracks']}")
        if 'fps' in stats:
            lines.append(f"FPS: {stats['fps']:.1f}")
        
        # Calculate position
        padding = 10
        line_height = 25
        
        if position == "top-left":
            x = padding
            y = padding + line_height
        elif position == "top-right":
            x = frame.shape[1] - 150
            y = padding + line_height
        else:
            x = padding
            y = frame.shape[0] - len(lines) * line_height - padding
        
        # Draw semi-transparent background
        bg_height = len(lines) * line_height + padding
        bg_width = 180
        overlay = annotated.copy()
        cv2.rectangle(
            overlay,
            (x - 5, y - line_height),
            (x + bg_width, y + bg_height - line_height),
            (0, 0, 0),
            -1
        )
        cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)
        
        # Draw text
        for i, line in enumerate(lines):
            color = (255, 255, 255)
            
            # Color code the size counts
            if line.startswith("Fingerling:"):
                color = self.SIZE_COLORS['fingerling']
            elif line.startswith("Post Fingerling:"):
                color = self.SIZE_COLORS['post_fingerling']
            elif line.startswith("Juvenile:"):
                color = self.SIZE_COLORS['juvenile']
            elif line.startswith("Unknown:"):
                color = self.SIZE_COLORS['unknown']
            
            cv2.putText(
                annotated,
                line,
                (x, y + i * line_height),
                self.font,
                self.config.font_scale,
                color,
                2
            )
        
        return annotated
    
    def draw_all(
        self,
        frame: np.ndarray,
        detections: Optional[List[Dict[str, Any]]] = None,
        tracks: Optional[List[Any]] = None,
        counting_line: Optional[Tuple[int, int, int, int]] = None,
        counting_line_orientation: str = "horizontal",
        stats: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        """
        Draw all visualizations on frame.
        
        Args:
            frame: Input frame.
            detections: List of detections.
            tracks: List of tracks.
            counting_line: Counting line coordinates.
            counting_line_orientation: Line orientation.
            stats: Statistics dictionary.
            
        Returns:
            Fully annotated frame.
        """
        annotated = frame.copy()
        
        # Draw counting line first (background)
        if self.config.show_counting_line and counting_line:
            annotated = self.draw_counting_line(
                annotated,
                counting_line,
                counting_line_orientation
            )
        
        # Draw detections or tracks
        if tracks and self.config.show_bounding_boxes:
            annotated = self.draw_tracks(annotated, tracks)
        elif detections and self.config.show_bounding_boxes:
            annotated = self.draw_detections(annotated, detections)
        
        # Draw statistics
        if self.config.show_statistics and stats:
            annotated = self.draw_statistics(annotated, stats)
        
        return annotated
    
    def create_dashboard(
        self,
        frame: np.ndarray,
        stats: Dict[str, Any],
        size_distribution: Dict[str, int]
    ) -> np.ndarray:
        """
        Create a dashboard view with frame and charts.
        
        Args:
            frame: Annotated video frame.
            stats: Statistics dictionary.
            size_distribution: Size distribution counts.
            
        Returns:
            Dashboard image.
        """
        h, w = frame.shape[:2]
        
        # Return the annotated frame with a small textual stats overlay
        dashboard = frame.copy()

        # Overlay simple counts (no charts)
        x = 10
        y = 20
        line_height = 22
        counts = stats.get('counts', {}) if stats else {}

        for i, (k, v) in enumerate(counts.items()):
            text = f"{k.replace('_', ' ').title()}: {v}"
            cv2.putText(dashboard, text, (x, y + i * line_height), self.font, 0.6, (255, 255, 255), 1)

        return dashboard
