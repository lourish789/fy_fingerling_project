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

import cv2
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.detector import FingerlingDetector, FingerlingDetectorFallback
from models.tracker import FingerlingTracker
from video.processor import VideoProcessor, VideoWriter, ImageProcessor, URLVideoHandler
from video.visualization import Visualizer, VisualizationConfig
from streaming.server import StreamingServer, ConsoleStreamer, CSVLogger


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
        
        # Detector
        try:
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
            self.detector = FingerlingDetectorFallback()
        
        # Tracker
        tracking_config = self.config.get('tracking', {})
        counting_config = self.config.get('counting', {})
        self.tracker = FingerlingTracker(
            max_age=tracking_config.get('max_age', 30),
            min_hits=tracking_config.get('min_hits', 3),
            iou_threshold=tracking_config.get('iou_threshold', 0.3),
            max_distance=tracking_config.get('max_distance', 100),
            counting_mode=counting_config.get('mode', 'unique_track'),
            count_min_hits=counting_config.get('count_min_hits', 1)
        )
        
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
                    reset_callback=self._reset_counts_from_server
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
    
    def _process_new_source(self, source: Union[str, int]) -> None:
        """
        Process a new source (called from web server).
        
        Args:
            source: New video/image source to process.
        """
        # Stop current processing
        self.stop_requested = True
        time.sleep(0.5)  # Wait for current processing to stop
        
        # Reset state
        self.tracker.reset_counts()
        self.stop_requested = False

        source_str = str(source)
        if isinstance(source, str) and (ImageProcessor.is_image_file(source_str) or ImageProcessor.is_image_url(source_str)):
            image_result = self.process_image_file(source_str, no_annotations=True)
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

                self.streaming_server.set_image_result({
                    'source': source_str,
                    'counts': image_result['counts'],
                    'size_distribution': image_result['size_distribution'],
                    'detections': len(image_result['detections']),
                    'label_summary': ', '.join(
                        f"{class_key.replace('_', ' ').title()}: {int(image_result['counts'].get(class_key, 0) or 0)}"
                        for class_key in ['fingerling', 'post_fingerling', 'juvenile']
                        if int(image_result['counts'].get(class_key, 0) or 0) > 0
                    ) or 'No detections'
                })
            return
        
        # Update source and process
        self.video_source = source
        self.counting_line = None
        self._create_video_processor()
        
        # Run processing (blocking in this thread)
        self._run_processing_loop()
    
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
    
    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Process a single frame through the pipeline.
        
        Args:
            frame: Input video frame.
            
        Returns:
            Processing results dictionary.
        """
        # Detect fingerlings
        detections = self.detector.detect(frame)
        
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
        detections = self.detector.detect(image)
        
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
    
    def _run_processing_loop(self) -> None:
        """Main processing loop."""
        self.is_processing = True
        self.stop_requested = False
        
        for frame_data in self.video_processor.frames():
            if not self.is_running or self.stop_requested:
                break
            
            frame = frame_data.frame
            self.frame_count = frame_data.frame_number

            if self.counting_line is None:
                frame_h, frame_w = frame.shape[:2]
                self._setup_counting_line(frame_w, frame_h)
            
            # Process frame
            results = self.process_frame(frame)
            
            # Always produce an annotated frame for viewers (boxes + labels).
            annotated_frame = self.visualizer.draw_all(
                frame,
                detections=results['detections'],
                tracks=results['tracks'],
                counting_line=self.counting_line,
                counting_line_orientation=self.counting_line_orientation,
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
                        break
                    elif key == ord('r'):
                        self.tracker.reset_counts()
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
        
        self.is_processing = False
    
    def run_web_server(self) -> None:
        """
        Run as web server only (for file uploads and URL processing).
        
        The web interface allows users to upload files or enter URLs
        for processing.
        """
        if not self.streaming_server:
            print("Error: Streaming server not available")
            return
        
        print("\n" + "=" * 50)
        print("Fingerling Counter - Web Server Mode")
        print("=" * 50)
        print(f"Dashboard: http://localhost:{self.streaming_server.port}")
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
