"""
Visualization Module for Fingerling Counter

Drawing utilities for bounding boxes, tracks, counting lines, and
a minimal count overlay.  Frame numbers, processing speed, and other
system telemetry are intentionally omitted from the frame; they are
displayed in the web dashboard instead.
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
    font_scale: float = 0.5
    line_thickness: int = 1       # thin, discrete boxes
    track_history_length: int = 30


class Visualizer:
    """Visualization utilities for the fingerling counter."""

    SIZE_COLORS = {
        'fingerling':     (0, 255, 136),   # green
        'post_fingerling':(255, 179, 71),   # amber
        'juvenile':       (0, 165, 255),    # orange-blue
        'unknown':        (128, 128, 128),  # grey
    }

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()
        self.font = cv2.FONT_HERSHEY_SIMPLEX

    # ─── Detections ────────────────────────────────────────────────────────
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]]
    ) -> np.ndarray:
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            class_key = det.get('class_name', det.get('size_category', 'unknown'))
            color = det.get('class_color', det.get('size_color',
                            self.SIZE_COLORS.get(class_key, (128, 128, 128))))

            # Thin bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color,
                          self.config.line_thickness)

            if self.config.show_size_labels:
                label = det.get('class_display_name', det.get('size_name', 'Fish'))
                # Compact label: class name only (confidence omitted to keep frame clean)
                (lw, lh), _ = cv2.getTextSize(
                    label, self.font, self.config.font_scale, 1)

                # Small label tag above box
                cv2.rectangle(annotated,
                              (x1, y1 - lh - 6),
                              (x1 + lw + 4, y1),
                              color, -1)
                cv2.putText(annotated, label,
                            (x1 + 2, y1 - 3),
                            self.font, self.config.font_scale,
                            (0, 0, 0), 1, cv2.LINE_AA)

        return annotated

    # ─── Tracks ────────────────────────────────────────────────────────────
    def draw_tracks(
        self,
        frame: np.ndarray,
        tracks: List[Any]
    ) -> np.ndarray:
        annotated = frame.copy()

        for track in tracks:
            if track.time_since_update > 0:
                continue

            color = track.class_color if hasattr(track, 'class_color') else (0, 255, 0)
            x1, y1, x2, y2 = track.bbox

            # Thin bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color,
                          self.config.line_thickness)

            # Label: class name only (track ID hidden from production frame)
            label = getattr(track, 'class_display_name', 'Fish')
            (lw, lh), _ = cv2.getTextSize(
                label, self.font, self.config.font_scale, 1)
            cv2.rectangle(annotated,
                          (x1, y1 - lh - 6),
                          (x1 + lw + 4, y1),
                          color, -1)
            cv2.putText(annotated, label,
                        (x1 + 2, y1 - 3),
                        self.font, self.config.font_scale,
                        (0, 0, 0), 1, cv2.LINE_AA)

            # Fading trail
            if self.config.show_tracks and len(track.history) > 1:
                history = track.history[-self.config.track_history_length:]
                for i in range(1, len(history)):
                    alpha = i / len(history)
                    cv2.line(annotated,
                             history[i - 1], history[i],
                             color,
                             max(1, int(self.config.line_thickness * alpha)),
                             cv2.LINE_AA)

            # Dot at centroid
            cv2.circle(annotated, track.center, 3, color, -1)

            if track.counted:
                cv2.circle(annotated, track.center, 8, (0, 255, 136), 1)

        return annotated

    # ─── Counting Line ─────────────────────────────────────────────────────
    def draw_counting_line(
        self,
        frame: np.ndarray,
        line: Tuple[int, int, int, int],
        orientation: str = "horizontal"
    ) -> np.ndarray:
        annotated = frame.copy()
        x1, y1, x2, y2 = line

        # Subtle dashed-style line (two overlapping colours)
        cv2.line(annotated, (x1, y1), (x2, y2), (0, 0, 0), 3, cv2.LINE_AA)
        cv2.line(annotated, (x1, y1), (x2, y2), (0, 210, 255), 1, cv2.LINE_AA)

        # Direction arrows
        mid_x = (x1 + x2) // 2
        mid_y = (y1 + y2) // 2
        if orientation == "horizontal":
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x, mid_y - 16),
                            (0, 210, 255), 1, tipLength=0.4)
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x, mid_y + 16),
                            (0, 210, 255), 1, tipLength=0.4)
        else:
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x - 16, mid_y),
                            (0, 210, 255), 1, tipLength=0.4)
            cv2.arrowedLine(annotated, (mid_x, mid_y), (mid_x + 16, mid_y),
                            (0, 210, 255), 1, tipLength=0.4)

        return annotated

    # ─── Statistics Overlay ────────────────────────────────────────────────
    def draw_statistics(
        self,
        frame: np.ndarray,
        stats: Dict[str, Any],
        position: str = "top-left"
    ) -> np.ndarray:
        """
        Draw a compact count overlay on the frame.

        Only class counts are shown — frame number, FPS, and active-track
        telemetry are omitted (they are displayed in the web dashboard).
        """
        annotated = frame.copy()
        counts = stats.get('counts', {})

        lines: List[Tuple[str, Tuple[int, int, int]]] = []
        total = counts.get('total', 0)
        if total:
            lines.append((f"Total: {total}", (255, 255, 255)))

        class_keys = [
            ('fingerling',      'Fingerling',      self.SIZE_COLORS['fingerling']),
            ('post_fingerling', 'Post-Fingerling', self.SIZE_COLORS['post_fingerling']),
            ('juvenile',        'Juvenile',        self.SIZE_COLORS['juvenile']),
            ('unknown',         'Unknown',         self.SIZE_COLORS['unknown']),
        ]
        for key, label, color in class_keys:
            val = counts.get(key, 0)
            if val:
                lines.append((f"{label}: {val}", color))

        if not lines:
            return annotated

        padding = 8
        line_h = 18
        overlay_w = 148
        overlay_h = len(lines) * line_h + padding * 2

        x_off = padding if position == "top-left" else (frame.shape[1] - overlay_w - padding)
        y_off = padding

        # Semi-transparent background
        roi = annotated[y_off : y_off + overlay_h, x_off : x_off + overlay_w]
        if roi.shape[0] > 0 and roi.shape[1] > 0:
            bg = np.zeros_like(roi)
            cv2.addWeighted(bg, 0.55, roi, 0.45, 0, roi)
            annotated[y_off : y_off + overlay_h, x_off : x_off + overlay_w] = roi

        for i, (text, color) in enumerate(lines):
            cv2.putText(
                annotated, text,
                (x_off + padding, y_off + padding + i * line_h + line_h - 4),
                self.font, self.config.font_scale,
                color, 1, cv2.LINE_AA,
            )

        return annotated

    # ─── Draw All ──────────────────────────────────────────────────────────
    def draw_all(
        self,
        frame: np.ndarray,
        detections: Optional[List[Dict[str, Any]]] = None,
        tracks: Optional[List[Any]] = None,
        counting_line: Optional[Tuple[int, int, int, int]] = None,
        counting_line_orientation: str = "horizontal",
        stats: Optional[Dict[str, Any]] = None
    ) -> np.ndarray:
        annotated = frame.copy()

        if self.config.show_counting_line and counting_line:
            annotated = self.draw_counting_line(
                annotated, counting_line, counting_line_orientation)

        if tracks and self.config.show_bounding_boxes:
            annotated = self.draw_tracks(annotated, tracks)
        elif detections and self.config.show_bounding_boxes:
            annotated = self.draw_detections(annotated, detections)

        if self.config.show_statistics and stats:
            annotated = self.draw_statistics(annotated, stats)

        return annotated

    # ─── Dashboard (legacy helper, kept for compatibility) ─────────────────
    def create_dashboard(
        self,
        frame: np.ndarray,
        stats: Dict[str, Any],
        size_distribution: Dict[str, int]
    ) -> np.ndarray:
        return self.draw_statistics(frame.copy(), stats)
