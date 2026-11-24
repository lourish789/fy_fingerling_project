"""
Fingerling Counter - Main Application

This module provides the main application class that integrates all components
for counting and sorting catfish fingerlings from video, image, or live camera input.
"""

import sys
import time
import signal
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Union, List
import yaml
import threading
from datetime import datetime

import cv2
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.tracker import FingerlingTracker
from video.processor import VideoProcessor, VideoWriter, ImageProcessor, URLVideoHandler
from video.visualization import Visualizer, VisualizationConfig
from streaming.server import StreamingServer, ConsoleStreamer, CSVLogger
from app.run_log import RunRecorder, file_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[2]


class FingerlingCounter:
    """
    Main application class for counting catfish fingerlings.
    
    Integrates detection, classification, tracking, and streaming
    into a unified processing pipeline.
    
    Supports:
    - Live camera feeds
    - Video files (local and remote)
    - Single images
    - Image directories
    - YouTube and web video URLs
    - RTSP/RTMP streams
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        video_source: Union[str, int] = 0,
        weights_path: Optional[str] = None,
        model_engine: Optional[str] = None,
        pretrained_model: Optional[str] = None,
        streaming_port: Optional[int] = None,
        use_streaming: bool = True,
        use_display: bool = True,
        output_path: Optional[str] = None,
        web_server_mode: bool = False
    ):
        """
        Initialize the fingerling counter.
        
        Args:
            config_path: Path to configuration file.
            video_source: Video source (file path, camera index, URL, or image path).
            weights_path: Path to model weights.
            model_engine: Model backend engine override (e.g., ultralytics).
            pretrained_model: Pretrained checkpoint override when weights_path is not provided.
            streaming_port: Optional override for web streaming port.
            use_streaming: Enable web streaming server.
            use_display: Show video display window.
            output_path: Path to save output video.
            web_server_mode: Run as web server for uploads.
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Override with arguments
        self.video_source = video_source
        self.weights_path = weights_path or self.config.get('model', {}).get('weights')
        self.model_engine = model_engine or self.config.get('model', {}).get('engine', 'ultralytics')
        self.pretrained_model = pretrained_model or self.config.get('model', {}).get('pretrained', 'yolov26n.pt')
        self.streaming_port = streaming_port
        self.use_streaming = use_streaming
        self.use_display = use_display
        self.output_path = output_path
        self.web_server_mode = web_server_mode

        # Job control. Only one source is processed at a time: a new request
        # bumps _job_seq, the running loop notices and exits, and the new job
        # starts only once _job_lock is free, so two loops never share a tracker.
        self._job_lock = threading.Lock()
        self._job_seq_lock = threading.Lock()
        self._job_seq = 0
        self._reset_requested = False
        self._quit_requested = False

        # Initialize components
        self._init_components()
        
        # State
        self.is_running = False
        self.is_processing = False
        self.frame_count = 0
        self.start_time = 0.0
        self.stop_requested = False
        
        # Thread lock for concurrent access
        self._lock = threading.Lock()

    def _normalized_counts(self, counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        """Return counts with stable keys so zero-detection runs still report valid results."""
        safe_counts = dict(counts or {})

        normalized = {'total': int(safe_counts.get('total', 0)), 'unknown': int(safe_counts.get('unknown', 0))}
        for class_key in self.class_keys:
            normalized[class_key] = int(safe_counts.get(class_key, 0))

        return normalized

    def _stop_from_server(self) -> None:
        """Handle stop request triggered from web dashboard."""
        self.stop_requested = True

    def _reset_counts_from_server(self) -> None:
        """Reset tracker counts and push immediate zero state to dashboard."""
        if self.is_processing:
            # Let the processing loop do it between frames, so it can close the
            # current run record and start a new one cleanly.
            self._reset_requested = True
        else:
            self.tracker.reset_counts()

        if self.streaming_server:
            zero_counts = {'total': 0, 'unknown': 0}
            for class_key in self.class_keys:
                zero_counts[class_key] = 0

            self.streaming_server.update_data(
                frame_number=self.frame_count,
                counts=zero_counts,
                current_detections=0,
                active_tracks=0,
                size_distribution={},
                fps=0.0,
                source_type=self.video_processor.source_type if self.video_processor else 'video',
                is_live=self.video_processor.is_live if self.video_processor else False
            )
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        
        # Try default config location
        default_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
        if default_path.exists():
            with open(default_path, 'r') as f:
                return yaml.safe_load(f)
        
        return {}
    
    def _init_components(self) -> None:
        """Initialize all processing components."""
        model_config = self.config.get('model', {})
        
        # Detector — lazy import so torch/ultralytics are never loaded on Render
        # (where only models/best.onnx is present and requirements-prod.txt
        # contains onnxruntime but NOT torch or ultralytics).
        weights = str(self.weights_path or '')
        if weights.lower().endswith('.onnx'):
            from models.onnx_detector import OnnxFingerlingDetector
            self.detector = OnnxFingerlingDetector(
                weights,
                confidence_threshold=model_config.get('confidence_threshold', 0.5),
                iou_threshold=model_config.get('iou_threshold', 0.5),
                num_threads=model_config.get('onnx_threads'),
                size_consistency_enabled=bool(model_config.get('size_consistency_enabled', False)),
            )
        else:
            try:
                from models.detector import FingerlingDetector
                self.detector = FingerlingDetector(
                    weights_path=self.weights_path,
                    model_engine=self.model_engine,
                    pretrained_model=self.pretrained_model,
                    confidence_threshold=model_config.get('confidence_threshold', 0.5),
                    iou_threshold=model_config.get('iou_threshold', 0.45),
                    device=model_config.get('device', 'auto'),
                    dark_surface_filter_enabled=model_config.get('dark_surface_filter', {}).get('enabled', False),
                    dark_surface_min_value_mean=model_config.get('dark_surface_filter', {}).get('min_value_mean', 45.0),
                    dark_surface_max_value_std=model_config.get('dark_surface_filter', {}).get('max_value_std', 28.0),
                    dark_surface_max_saturation_mean=model_config.get('dark_surface_filter', {}).get('max_saturation_mean', 65.0)
                )
            except Exception as e:
                print(f"Warning: Could not load YOLO model ({e}). Using fallback detector.")
                try:
                    from models.detector import FingerlingDetectorFallback
                except ImportError:
                    from models.onnx_detector import _FallbackDetector as FingerlingDetectorFallback
                self.detector = FingerlingDetectorFallback()
        
        # Tracker
        self.tracker = self._build_tracker()

        # Per-run audit records (events.csv, summary.json, report.html)
        output_config = self.config.get('output', {})
        runs_dir = Path(output_config.get('runs_dir', 'output/runs'))
        self.runs_dir = runs_dir if runs_dir.is_absolute() else REPO_ROOT / runs_dir
        self.save_runs = bool(output_config.get('save_runs', True))
        self.save_event_crops = bool(output_config.get('save_event_crops', True))
        self.model_fingerprint = file_fingerprint(str(self.weights_path or ''))

        # Video processor
        video_config = self.config.get('video', {})
        self.video_processor = VideoProcessor(
            source=self.video_source,
            target_fps=video_config.get('fps'),
            frame_width=video_config.get('frame_width'),
            frame_height=video_config.get('frame_height'),
            buffer_size=video_config.get('buffer_size', 10)
        )
        
        # Visualizer
        display_config = self.config.get('display', {})
        vis_config = VisualizationConfig(
            show_bounding_boxes=display_config.get('show_bounding_boxes', True),
            show_tracks=display_config.get('show_tracks', True),
            show_counting_line=display_config.get('show_counting_line', True),
            show_size_labels=display_config.get('show_size_labels', True),
            show_statistics=display_config.get('show_statistics', True),
            font_scale=display_config.get('font_scale', 0.6),
            line_thickness=display_config.get('line_thickness', 2)
        )
        self.visualizer = Visualizer(vis_config)
        
        # Console streamer
        self.console_streamer = ConsoleStreamer(update_interval=0.5)
        self.class_keys = self.detector.get_class_keys() if hasattr(self.detector, 'get_class_keys') else ['fingerling', 'post_fingerling', 'juvenile']
        
        # Streaming server
        self.streaming_server: Optional[StreamingServer] = None
        if self.use_streaming:
            streaming_config = self.config.get('streaming', {})
            try:
                self.streaming_server = StreamingServer(
                    host=streaming_config.get('host', '0.0.0.0'),
                    port=self.streaming_port or streaming_config.get('port', 5000),
                    update_interval_ms=streaming_config.get('update_interval_ms', 100),
                    process_callback=self._process_new_source if self.web_server_mode else None,
                    stop_callback=self._stop_from_server,
                    reset_callback=self._reset_counts_from_server,
                    runs_dir=str(self.runs_dir)
                )
                # Expose counter instance to streaming server for batch processing
                try:
                    setattr(self.streaming_server, 'counter', self)
                except Exception:
                    pass
            except ImportError:
                print("Warning: Flask not available. Web streaming disabled.")
                self.streaming_server = None
        
        # Video writer
        self.video_writer: Optional[VideoWriter] = None
        if self.output_path:
            self.video_writer = VideoWriter(
                output_path=self.output_path,
                fps=video_config.get('fps', 30),
                width=video_config.get('frame_width'),
                height=video_config.get('frame_height')
            )
        
        # CSV logger
        self.csv_logger: Optional[CSVLogger] = None
        output_config = self.config.get('output', {})
        if output_config.get('save_csv', False):
            csv_path = output_config.get('csv_path', 'output/counts.csv')
            self.csv_logger = CSVLogger(csv_path, class_keys=self.class_keys)
        
        # Current video processor
        self.video_processor: Optional[VideoProcessor] = None
        self.counting_line = None
        self.counting_line_orientation = 'horizontal'

    def _build_tracker(self) -> FingerlingTracker:
        """Create a tracker from config. Each job gets a fresh one, so no tracks carry over."""
        tracking_config = self.config.get('tracking', {})
        counting_config = self.config.get('counting', {})
        return FingerlingTracker(
            max_age=tracking_config.get('max_age', 30),
            min_hits=tracking_config.get('min_hits', 3),
            iou_threshold=tracking_config.get('iou_threshold', 0.3),
            max_distance=tracking_config.get('max_distance', 100),
            counting_mode=counting_config.get('mode', 'unique_track'),
            count_min_hits=counting_config.get('count_min_hits', 1),
            count_direction=counting_config.get('count_direction', 'any')
        )

    def _run_settings(self) -> Dict[str, Any]:
        """The settings that determine a count, saved with every run for traceability."""
        model_config = self.config.get('model', {})
        tracking_config = self.config.get('tracking', {})
        counting_config = self.config.get('counting', {})
        return {
            'model_file': Path(str(self.weights_path or 'none')).name,
            'model_sha256_12': self.model_fingerprint,
            'confidence_threshold': getattr(self.detector, 'confidence_threshold',
                                            model_config.get('confidence_threshold')),
            'nms_iou_threshold': getattr(self.detector, 'iou_threshold',
                                         model_config.get('iou_threshold')),
            'counting_mode': self.tracker.counting_mode,
            'count_direction': self.tracker.count_direction,
            'counting_line_position': counting_config.get('counting_line_position', 0.5),
            'counting_line_orientation': counting_config.get('counting_line_orientation', 'horizontal'),
            'min_hits': self.tracker.min_hits,
            'max_distance_px': self.tracker.max_distance,
            'max_age_frames': tracking_config.get('max_age', 30),
            'roi': self.config.get('video', {}).get('roi'),
        }

    def _start_run_record(self) -> Optional[RunRecorder]:
        if not self.save_runs:
            return None
        counting_config = self.config.get('counting', {})
        try:
            return RunRecorder(
                runs_dir=self.runs_dir,
                source_label=str(self.video_source),
                settings=self._run_settings(),
                class_keys=self.class_keys,
                save_crops=self.save_event_crops,
                correction_factor=float(counting_config.get('count_correction_factor', 1.0) or 1.0),
                correction_note=str(counting_config.get('count_correction_note', '') or ''),
            )
        except OSError as e:
            print(f"Warning: could not create run record ({e}). Counting continues without it.")
            return None

    def _finish_run_record(self, recorder: Optional[RunRecorder], status: str,
                           frames_done: int, error: str = '') -> Optional[Dict[str, Any]]:
        if recorder is None:
            return None
        try:
            info = self.video_processor.get_info() if self.video_processor else {}
            summary = recorder.finish(self._normalized_counts(self.tracker.get_counts()),
                                      status, frames_done, info, error)
        except Exception as e:
            print(f"Warning: could not finalise run record ({e}).")
            return None
        print(f"\nRun saved: {recorder.dir}")
        if self.streaming_server:
            self.streaming_server.notify_run_saved(summary)
        return summary

    def _process_new_source(self, source: Union[str, int]) -> None:
        """
        Process a new source (called from web server).

        A newer request supersedes this one; the running loop exits at its next
        frame, and this job starts only after it has fully finished.

        Args:
            source: New video/image source to process.
        """
        def job(job_id: int) -> None:
            self.stop_requested = False
            self._reset_requested = False
            self.tracker = self._build_tracker()
            self._process_source_locked(source, job_id)

        self._run_job(job)

    def run_exclusive(self, fn, *args):
        """Run fn(*args) as a job: it waits for, and supersedes, any running processing loop."""
        return self._run_job(lambda _job_id: fn(*args))

    def _run_job(self, fn):
        with self._job_seq_lock:
            self._job_seq += 1
            job_id = self._job_seq

        with self._job_lock:
            if job_id != self._job_seq:
                return None  # an even newer request arrived while this one was waiting
            return fn(job_id)

    def _process_source_locked(self, source: Union[str, int], job_id: int) -> None:
        source_str = str(source)
        if isinstance(source, str) and (ImageProcessor.is_image_file(source_str) or ImageProcessor.is_image_url(source_str)):
            started_at = datetime.now()
            image_result = self.process_image_file(source_str, no_annotations=False)
            if 'error' in image_result:
                raise RuntimeError(image_result['error'])

            if self.streaming_server:
                self.streaming_server.update_frame(image_result['annotated_image'])
                self.streaming_server.update_data(
                    frame_number=1,
                    counts=image_result['counts'],
                    current_detections=len(image_result['detections']),
                    active_tracks=len(image_result['detections']),
                    size_distribution=image_result['size_distribution'],
                    fps=0.0,
                    source_type='image',
                    is_live=False
                )

                import base64
                annotated_b64 = None
                try:
                    _, buf = cv2.imencode('.jpg', image_result['annotated_image'],
                                         [cv2.IMWRITE_JPEG_QUALITY, 80])
                    annotated_b64 = base64.b64encode(buf).decode('ascii')
                except Exception:
                    pass
                self.streaming_server.set_image_result({
                    'source': source_str,
                    'counts': image_result['counts'],
                    'size_distribution': image_result['size_distribution'],
                    'detections': len(image_result['detections']),
                    'annotated_image_b64': annotated_b64,
                    'label_summary': ', '.join(
                        f"{class_key.replace('_', ' ').title()}: {int(image_result['counts'].get(class_key, 0) or 0)}"
                        for class_key in ['fingerling', 'post_fingerling', 'juvenile']
                        if int(image_result['counts'].get(class_key, 0) or 0) > 0
                    ) or 'No detections'
                })
                if self.save_runs:
                    self.streaming_server.record_image_run(
                        source_str, image_result['counts'], len(image_result['detections']),
                        image_result['annotated_image'], started_at)
            return
        
        # Update source and process
        self.video_source = source
        self.counting_line = None
        self._create_video_processor()

        # Run processing (blocking in this thread)
        summary = self._run_processing_loop(job_id)
        if summary and summary.get('status') == 'error':
            raise RuntimeError(summary.get('error') or 'Processing failed')
    
    def _create_video_processor(self) -> None:
        """Create or recreate video processor for current source."""
        video_config = self.config.get('video', {})
        
        if self.video_processor:
            self.video_processor.close()
        
        self.video_processor = VideoProcessor(
            source=self.video_source,
            target_fps=video_config.get('fps'),
            frame_width=video_config.get('frame_width'),
            frame_height=video_config.get('frame_height'),
            buffer_size=video_config.get('buffer_size', 10),
            auto_reconnect=True
        )
    
    def _setup_counting_line(self, frame_width: int, frame_height: int) -> None:
        """Setup counting line based on frame dimensions."""
        counting_config = self.config.get('counting', {})
        use_line_mode = self.tracker.counting_mode == 'line_crossing'
        
        if use_line_mode and counting_config.get('use_counting_line', True):
            position = counting_config.get('counting_line_position', 0.5)
            orientation = counting_config.get('counting_line_orientation', 'horizontal')
            
            if orientation == 'horizontal':
                y = int(frame_height * position)
                self.tracker.set_counting_line(0, y, frame_width, y, orientation)
                self.counting_line = (0, y, frame_width, y)
            else:
                x = int(frame_width * position)
                self.tracker.set_counting_line(x, 0, x, frame_height, orientation)
                self.counting_line = (x, 0, x, frame_height)
            
            self.counting_line_orientation = orientation
        else:
            self.counting_line = None
            self.counting_line_orientation = 'horizontal'
    
    def _resolve_roi(self, frame_w: int, frame_h: int) -> Optional[tuple]:
        """Resolve configured video.roi (relative 0-1 or pixel [x1, y1, x2, y2]) to pixel coords."""
        raw = self.config.get('video', {}).get('roi')
        if not raw or len(raw) != 4:
            return None
        try:
            vals = [float(v) for v in raw]
        except (TypeError, ValueError):
            return None
        # Treat all values <= 1.0 as relative fractions of frame size
        if all(0.0 <= v <= 1.0 for v in vals):
            x1, y1 = int(round(vals[0] * frame_w)), int(round(vals[1] * frame_h))
            x2, y2 = int(round(vals[2] * frame_w)), int(round(vals[3] * frame_h))
        else:
            x1, y1, x2, y2 = (int(round(v)) for v in vals)
        x1 = max(0, min(x1, frame_w - 1))
        y1 = max(0, min(y1, frame_h - 1))
        x2 = max(x1 + 1, min(x2, frame_w))
        y2 = max(y1 + 1, min(y2, frame_h))
        if x1 == 0 and y1 == 0 and x2 == frame_w and y2 == frame_h:
            return None
        return (x1, y1, x2, y2)

    def _detect_with_roi(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Run detector on configured channel ROI (if any) and map boxes back to full frame."""
        frame_h, frame_w = frame.shape[:2]
        roi = self._resolve_roi(frame_w, frame_h)
        if roi is None:
            return self.detector.detect(frame)

        rx1, ry1, rx2, ry2 = roi
        cropped = frame[ry1:ry2, rx1:rx2]
        detections = self.detector.detect(cropped)
        mapped: List[Dict[str, Any]] = []
        for det in detections:
            d = dict(det)
            bx1, by1, bx2, by2 = d['bbox']
            d['bbox'] = [bx1 + rx1, by1 + ry1, bx2 + rx1, by2 + ry1]
            cx, cy = d['center']
            d['center'] = (cx + rx1, cy + ry1)
            mapped.append(d)
        return mapped

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Process a single frame through the pipeline.
        
        Args:
            frame: Input video frame.
            
        Returns:
            Processing results dictionary.
        """
        # Detect fingerlings (optionally masked to configured channel ROI)
        detections = self._detect_with_roi(frame)
        
        # Update tracker
        tracks = self.tracker.update(detections)
        
        # Get statistics
        stats = self.tracker.get_statistics()
        elapsed = time.time() - self.start_time
        stats['fps'] = self.frame_count / max(elapsed, 0.001)
        stats['counts'] = self._normalized_counts(stats.get('counts'))
        
        # Get class distribution for current frame
        size_dist: Dict[str, int] = {}
        for det in detections:
            class_key = det.get('class_name', 'unknown')
            size_dist[class_key] = size_dist.get(class_key, 0) + 1
        
        return {
            'detections': detections,
            'tracks': tracks,
            'stats': stats,
            'size_distribution': size_dist
        }
    
    def process_image(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Process a single image (no tracking, just detection and classification).
        
        Args:
            image: Input image.
            
        Returns:
            Processing results dictionary.
        """
        # Detect fingerlings
        detections = self._detect_with_roi(image)
        
        # Get class distribution
        size_dist: Dict[str, int] = {}
        for det in detections:
            class_key = det.get('class_name', 'unknown')
            size_dist[class_key] = size_dist.get(class_key, 0) + 1

        # Calculate totals
        counts = {'total': len(detections)}
        for class_key in self.class_keys:
            counts[class_key] = size_dist.get(class_key, 0)
        counts['unknown'] = size_dist.get('unknown', 0)
        
        return {
            'detections': detections,
            'counts': counts,
            'size_distribution': size_dist
        }
    
    def process_image_file(self, image_path: str, no_annotations: bool = False) -> Dict[str, Any]:
        """
        Process an image file or URL.
        
        Args:
            image_path: Path to image file or URL.
            no_annotations: If True, skip drawing overlays on the returned image.
            
        Returns:
            Processing results with optional annotated image.
        """
        # Load image
        image = ImageProcessor.load_image(image_path)
        if image is None:
            return {'error': f'Failed to load image: {image_path}'}
        
        # Process
        results = self.process_image(image)
        
        if not no_annotations:
            # Annotate for local image preview or offline use.
            annotated = self.visualizer.draw_detections(image, results['detections'])
            annotated = self.visualizer.draw_statistics(annotated, {
                'counts': results['counts'],
                'active_tracks': len(results['detections'])
            })
            results['annotated_image'] = annotated
        else:
            results['annotated_image'] = image.copy()

        results['source'] = image_path
        
        return results
    
    def process_image_batch(self, image_paths: List[str], no_annotations: bool = False) -> Dict[str, Any]:
        """
        Process multiple images.
        
        Args:
            image_paths: List of image paths or URLs.
            no_annotations: If True, skip drawing overlays on each image.
            
        Returns:
            Dictionary with batch processing results.
        """
        results = []
        total_counts = {'total': 0, 'unknown': 0}
        for class_key in self.class_keys:
            total_counts[class_key] = 0
        
        for path in image_paths:
            result = self.process_image_file(path, no_annotations=no_annotations)
            results.append(result)
            
            if 'counts' in result:
                for key in total_counts:
                    total_counts[key] += result['counts'].get(key, 0)
        
        return {
            'individual_results': results,
            'total_counts': total_counts,
            'image_count': len(image_paths)
        }
    
    def run(self) -> Dict[str, int]:
        """
        Run the fingerling counter.
        
        Returns:
            Final counts dictionary.
        """
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Create video processor
        self._create_video_processor()
        
        # Open video source
        if not self.video_processor.open():
            print("Error: Could not open video source")
            return {}
        
        # Get video info
        video_info = self.video_processor.get_info()
        print(f"\nProcessing: {video_info['source']}")
        print(f"Type: {video_info['source_type']}")
        print(f"Resolution: {video_info['width']}x{video_info['height']} @ {video_info['fps']:.1f} FPS")
        if video_info['is_live']:
            print("Mode: LIVE (continuous streaming)")
        
        # Setup counting line
        self._setup_counting_line(video_info['width'], video_info['height'])
        
        # Start streaming server
        if self.streaming_server:
            self.streaming_server.start(background=True)
        
        # Open video writer
        if self.video_writer:
            self.video_writer.open()
        
        self.is_running = True
        self.start_time = time.time()
        self.frame_count = 0
        
        print("\nProcessing started. Press 'q' to quit.\n")
        
        try:
            self._run_processing_loop()
        finally:
            self._cleanup()
        
        # Get final counts
        final_counts = self._normalized_counts(self.tracker.get_counts())
        self.console_streamer.print_summary(final_counts)
        
        return final_counts
    
    def _run_processing_loop(self, job_id: int = 0) -> Optional[Dict[str, Any]]:
        """
        Main processing loop.

        Returns the run summary (also written to output/runs/<run_id>/), or None
        when run recording is disabled.
        """
        self.is_running = True
        self.is_processing = True
        self.stop_requested = False
        self.start_time = time.time()
        self.frame_count = 0

        recorder = self._start_run_record()
        status, error = 'completed', ''
        frames_done = 0   # frames in the current run record (restarts after a reset)
        frames_read = 0   # frames read from the source in total
        summary = None

        try:
            for frame_data in self.video_processor.frames():
                if not self.is_running or self.stop_requested:
                    status = 'stopped'
                    break
                if job_id != self._job_seq:
                    status = 'superseded'
                    break
                if self._reset_requested:
                    self._reset_requested = False
                    # Close the record with the counts so far, then start from zero.
                    self._finish_run_record(recorder, 'reset', frames_done)
                    self.tracker.reset_counts()
                    recorder = self._start_run_record()
                    frames_done = 0

                self._process_one_frame(frame_data, recorder)
                frames_done += 1
                frames_read += 1
                if self._quit_requested:  # 'q' pressed in the local preview window
                    status = 'stopped'
                    break
            else:
                if frames_read == 0:
                    status, error = 'error', f'No frames could be read from: {self.video_source}'
        except Exception as e:
            status, error = 'error', f'{type(e).__name__}: {e}'
            raise
        finally:
            self.is_processing = False
            summary = self._finish_run_record(recorder, status, frames_done, error)
            if recorder is None and status == 'error':
                summary = {'status': status, 'error': error}

        return summary

    def _process_one_frame(self, frame_data, recorder: Optional[RunRecorder]) -> None:
        """Detect, track, count, record and publish one frame."""
        self._quit_requested = False
        frame = frame_data.frame
        self.frame_count = frame_data.frame_number

        if self.counting_line is None:
            frame_h, frame_w = frame.shape[:2]
            self._setup_counting_line(frame_w, frame_h)

        # Process frame
        results = self.process_frame(frame)

        # Per-fish audit trail
        new_events = self.tracker.drain_events()
        if recorder is not None and new_events:
            if self.video_processor.is_live:
                video_time = frame_data.timestamp
            else:
                video_time = frame_data.frame_number / (self.video_processor.original_fps or 30.0)
            recorder.record(new_events, frame, video_time)

        # Always produce an annotated frame for viewers (boxes + labels).
        frame_h, frame_w = frame.shape[:2]
        annotated_frame = self.visualizer.draw_all(
            frame,
            detections=results['detections'],
            tracks=results['tracks'],
            counting_line=self.counting_line,
            counting_line_orientation=self.counting_line_orientation,
            count_direction=self.tracker.count_direction,
            roi=self._resolve_roi(frame_w, frame_h),
            stats=results['stats']
        )

        # Update streaming server
        if self.streaming_server:
            self.streaming_server.update_frame(annotated_frame)
            self.streaming_server.update_data(
                frame_number=self.frame_count,
                counts=results['stats']['counts'],
                current_detections=len(results['detections']),
                active_tracks=results['stats']['active_tracks'],
                size_distribution=results['size_distribution'],
                fps=results['stats']['fps'],
                source_type=self.video_processor.source_type,
                is_live=self.video_processor.is_live
            )

        # Console update
        self.console_streamer.update(
            frame_number=self.frame_count,
            counts=results['stats']['counts'],
            size_distribution=results['size_distribution'],
            fps=results['stats']['fps']
        )

        # Save video frame
        if self.video_writer:
            self.video_writer.write(annotated_frame)

        # Log to CSV
        if self.csv_logger and self.frame_count % 30 == 0:
            self.csv_logger.log(
                frame_number=self.frame_count,
                counts=results['stats']['counts'],
                fps=results['stats']['fps']
            )

        # Display
        if self.use_display:
            try:
                cv2.imshow('Fingerling Counter', annotated_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self._quit_requested = True
                elif key == ord('r'):
                    self._reset_requested = True
                    print("\nCounts reset!")
                elif key == ord('s'):
                    screenshot_path = f"screenshot_{self.frame_count}.jpg"
                    cv2.imwrite(screenshot_path, annotated_frame)
                    print(f"\nScreenshot saved: {screenshot_path}")
            except cv2.error:
                # OpenCV headless mode - disable display
                if self.use_display:
                    print("\nNote: Display not available (headless mode). Using web dashboard only.")
                    self.use_display = False

    def run_web_server(self) -> None:
        """
        Run as web server only (for file uploads and URL processing).
        
        The web interface allows users to upload files or enter URLs
        for processing.
        """
        if not self.streaming_server:
            print("Error: Streaming server not available")
            return
        
        port = self.streaming_server.port
        print("\n" + "=" * 50)
        print("Fingerling Counter - Web Server Mode")
        print("=" * 50)
        print(f"Dashboard (this computer):   http://localhost:{port}")
        lan_ip = _lan_ip()
        if lan_ip:
            print(f"Dashboard (same Wi-Fi/LAN):  http://{lan_ip}:{port}")
        print(f"Run records saved to:        {self.runs_dir}")
        print("Upload videos, images, or enter URLs to process")
        print("Press Ctrl+C to stop")
        print("=" * 50 + "\n")
        
        self.is_running = True
        
        # Run server in foreground (blocking)
        try:
            self.streaming_server.start(background=False)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.is_running = False
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle interrupt signal."""
        print("\nInterrupt received. Stopping...")
        self.is_running = False
    
    def _cleanup(self) -> None:
        """Cleanup resources."""
        self.is_running = False
        self.is_processing = False
        
        if self.video_processor:
            self.video_processor.close()
        
        if self.video_writer:
            self.video_writer.close()
        
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass  # Headless mode - no windows to destroy


def _lan_ip() -> Optional[str]:
    """Best-effort local network address, for phones/tablets on the same Wi-Fi. Sends nothing."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # UDP connect only selects a route; no packet is sent
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Catfish Fingerling Counter - Detect, count, and sort fingerlings by class from video/image'
    )
    
    parser.add_argument(
        '-s', '--source',
        default=0,
        help='Video source: file path, camera index (0, 1, ...), URL, or image path'
    )
    parser.add_argument(
        '--video',
        default=None,
        help='Video file path (alias for --source)'
    )
    parser.add_argument(
        '-c', '--config',
        default=None,
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '-w', '--weights',
        default=None,
        help='Path to model weights file'
    )
    parser.add_argument(
        '--model-engine',
        default=None,
        help='Model engine backend (default from config, e.g., ultralytics)'
    )
    parser.add_argument(
        '--pretrained-model',
        default=None,
        help='Pretrained checkpoint when --weights is not provided (e.g., yolov26n.pt)'
    )
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='Output video file path'
    )
    parser.add_argument(
        '--no-display',
        action='store_true',
        help='Disable video display window'
    )
    parser.add_argument(
        '--no-streaming',
        action='store_true',
        help='Disable web streaming server'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('PORT', 5000)),
        help='Streaming server port (default: 5000)'
    )
    parser.add_argument(
        '--web-server',
        action='store_true',
        help='Run as web server only (for uploads and URL processing)'
    )
    parser.add_argument(
        '--image',
        default=None,
        help='Process single image file or URL'
    )
    parser.add_argument(
        '--image-dir',
        default=None,
        help='Process all images in directory'
    )
    
    args = parser.parse_args()
    
    # Parse video source
    resolved_source = args.video if args.video is not None else args.source

    try:
        source = int(resolved_source)
    except ValueError:
        source = resolved_source
    
    # Handle single image processing
    if args.image:
        counter = FingerlingCounter(
            config_path=args.config,
            weights_path=args.weights,
            model_engine=args.model_engine,
            pretrained_model=args.pretrained_model,
            streaming_port=args.port,
            use_streaming=False,
            use_display=True
        )
        
        result = counter.process_image_file(args.image)
        
        if 'error' in result:
            print(f"Error: {result['error']}")
            return 1
        
        print("\n" + "=" * 40)
        print("IMAGE PROCESSING RESULTS")
        print("=" * 40)
        print(f"Total Fingerlings: {result['counts']['total']}")
        print(f"  - Fingerling:     {result['counts'].get('fingerling', 0)}")
        print(f"  - Post-Fingerling:{result['counts'].get('post_fingerling', 0)}")
        print(f"  - Juvenile:       {result['counts'].get('juvenile', 0)}")
        print(f"  - Unknown:        {result['counts'].get('unknown', 0)}")
        print("=" * 40)
        
        # Display result
        if not args.no_display:
            cv2.imshow('Fingerling Detection Result', result['annotated_image'])
            print("\nPress any key to close...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        
        # Save annotated image
        if args.output:
            cv2.imwrite(args.output, result['annotated_image'])
            print(f"Saved annotated image to: {args.output}")
        
        return 0
    
    # Handle image directory processing
    if args.image_dir:
        counter = FingerlingCounter(
            config_path=args.config,
            weights_path=args.weights,
            model_engine=args.model_engine,
            pretrained_model=args.pretrained_model,
            streaming_port=args.port,
            use_streaming=False,
            use_display=False
        )
        
        from video.processor import ImageProcessor
        images = ImageProcessor.load_images_from_directory(args.image_dir)
        image_paths = [path for path, _ in images]
        
        if not image_paths:
            print(f"No images found in: {args.image_dir}")
            return 1
        
        results = counter.process_image_batch(image_paths)
        
        print("\n" + "=" * 40)
        print("BATCH IMAGE PROCESSING RESULTS")
        print("=" * 40)
        print(f"Images Processed: {results['image_count']}")
        print(f"Total Fingerlings: {results['total_counts']['total']}")
        print(f"  - Fingerling:      {results['total_counts'].get('fingerling', 0)}")
        print(f"  - Post-Fingerling: {results['total_counts'].get('post_fingerling', 0)}")
        print(f"  - Juvenile:        {results['total_counts'].get('juvenile', 0)}")
        print(f"  - Unknown:         {results['total_counts'].get('unknown', 0)}")
        print("=" * 40)
        
        return 0
    
    # Create counter
    counter = FingerlingCounter(
        config_path=args.config,
        video_source=source,
        weights_path=args.weights,
        model_engine=args.model_engine,
        pretrained_model=args.pretrained_model,
        streaming_port=args.port,
        use_streaming=not args.no_streaming,
        use_display=not args.no_display,
        output_path=args.output,
        web_server_mode=args.web_server
    )
    
    # Run in appropriate mode
    if args.web_server:
        counter.run_web_server()
        return 0
    else:
        counts = counter.run()
        return 0 if counts else 1


if __name__ == '__main__':
    sys.exit(main())
