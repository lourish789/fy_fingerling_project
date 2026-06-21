"""
Streaming Server for Fingerling Counter

Provides real-time streaming of video and counting data
via HTTP/WebSocket endpoints with file upload support.
"""

import json
import time
import threading
import base64
import os
import tempfile
from typing import Dict, Any, Optional, Generator, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from queue import Queue, Empty
from pathlib import Path

import cv2
import numpy as np

try:
    from flask import Flask, Response, render_template_string, jsonify, request, send_from_directory
    from flask_cors import CORS
    from flask_socketio import SocketIO, emit
    from werkzeug.utils import secure_filename
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Warning: Flask not available. Install with: pip install flask flask-socketio")


@dataclass
class StreamData:
    """Data structure for streaming updates."""
    timestamp: str
    frame_number: int
    counts: Dict[str, int]
    current_detections: int
    active_tracks: int
    size_distribution: Dict[str, int]
    fps: float
    source_type: str = "video"
    is_live: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class StreamingServer:
    """
    Flask-based streaming server for real-time updates.
    
    Provides:
    - MJPEG video stream
    - WebSocket updates for counts
    - REST API for current state
    - Web dashboard with file upload
    - Image/Video upload processing
    - URL-based video processing
    """
    
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'jpg', 'jpeg', 'png', 'bmp', 'gif'}
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        update_interval_ms: int = 100,
        upload_folder: Optional[str] = None,
        process_callback: Optional[Callable] = None,
        stop_callback: Optional[Callable] = None,
        reset_callback: Optional[Callable] = None
    ):
        """
        Initialize streaming server.
        
        Args:
            host: Server host address.
            port: Server port.
            update_interval_ms: Interval between updates in milliseconds.
            upload_folder: Folder for uploaded files.
            process_callback: Callback function to process new source.
            stop_callback: Callback to stop active processing loop.
            reset_callback: Callback to reset tracker counts/state.
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required. Install with: pip install flask flask-socketio")
        
        self.host = host
        self.port = port
        self.update_interval = update_interval_ms / 1000.0
        self.upload_folder = upload_folder or tempfile.mkdtemp()
        self.process_callback = process_callback
        self.stop_callback = stop_callback
        self.reset_callback = reset_callback
        
        # Flask app
        self.app = Flask(__name__)
        CORS(self.app, resources={r"/*": {"origins": "*"}})
        self.app.config['SECRET_KEY'] = 'fingerling_counter_secret'
        self.app.config['UPLOAD_FOLDER'] = self.upload_folder
        self.app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        # State
        self.current_frame: Optional[np.ndarray] = None
        self.current_data: Optional[StreamData] = None
        self.is_running = False
        self.is_processing = False
        self.frame_lock = threading.Lock()
        self.data_lock = threading.Lock()

        # Frame queue for MJPEG streaming (local/same-origin)
        self.frame_queue: Queue = Queue(maxsize=10)

        # Socket.IO frame emission rate-limiter (~8 fps cap)
        self._last_frame_emit: float = 0.0
        self._FRAME_MIN_INTERVAL: float = 0.12  # seconds between emitted frames
        
        # Processing results for images
        self.image_results: Dict[str, Any] = {}
        
        # Batch results storage
        self.batch_results: list = []
        
        # Setup routes
        self._setup_routes()
    
    def _allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def _setup_routes(self) -> None:
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main API endpoint."""
            return jsonify({'status': 'Fingerling Counter API is running', 'message': 'Frontend is hosted separately.'})
        
        @self.app.route('/video_feed')
        def video_feed():
            """MJPEG video stream."""
            return Response(
                self._generate_frames(),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )
        
        @self.app.route('/api/status')
        def api_status():
            """Get current status."""
            with self.data_lock:
                if self.current_data:
                    data = self.current_data.to_dict()
                    data['is_processing'] = self.is_processing
                    return jsonify(data)
                return jsonify({'status': 'no data', 'is_processing': self.is_processing})
        
        @self.app.route('/api/counts')
        def api_counts():
            """Get current counts."""
            with self.data_lock:
                if self.current_data:
                    return jsonify({
                        'counts': self.current_data.counts,
                        'distribution': self.current_data.size_distribution
                    })
                return jsonify({'counts': {}, 'distribution': {}})
        
        @self.app.route('/api/upload', methods=['POST'])
        def upload_file():
            """Handle file upload."""
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            if file and self._allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(self.upload_folder, filename)
                file.save(filepath)
                
                # Trigger processing callback
                if self.process_callback:
                    threading.Thread(
                        target=self._process_uploaded_file,
                        args=(filepath,),
                        daemon=True
                    ).start()
                
                return jsonify({
                    'success': True,
                    'filename': filename,
                    'filepath': filepath,
                    'message': 'File uploaded successfully. Processing started.'
                })
            
            return jsonify({'error': 'File type not allowed'}), 400
        
        @self.app.route('/api/upload_batch', methods=['POST'])
        def upload_batch():
            """Handle multiple image uploads for batch processing."""
            if 'files' not in request.files:
                return jsonify({'error': 'No files provided'}), 400
            
            files = request.files.getlist('files')
            if not files:
                return jsonify({'error': 'No files selected'}), 400
            
            uploaded_files = []
            for file in files:
                if file.filename and self._allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(self.upload_folder, filename)
                    file.save(filepath)
                    uploaded_files.append({'filename': filename, 'filepath': filepath})
            
            if uploaded_files:
                # Trigger batch processing callback
                if self.process_callback:
                    threading.Thread(
                        target=self._process_batch_files,
                        args=(uploaded_files,),
                        daemon=True
                    ).start()
                
                return jsonify({
                    'success': True,
                    'files': uploaded_files,
                    'count': len(uploaded_files),
                    'message': f'Uploaded {len(uploaded_files)} file(s). Processing started.'
                })
            
            return jsonify({'error': 'No valid files provided'}), 400
        
        @self.app.route('/api/process_url', methods=['POST'])
        def process_url():
            """Process video/image from URL."""
            data = request.get_json()
            if not data or 'url' not in data:
                return jsonify({'error': 'No URL provided'}), 400
            
            url = data['url']
            
            # Trigger processing callback
            if self.process_callback:
                threading.Thread(
                    target=self._process_url,
                    args=(url,),
                    daemon=True
                ).start()
            
            return jsonify({
                'success': True,
                'url': url,
                'message': 'URL processing started.'
            })
        
        @self.app.route('/api/start_camera', methods=['POST'])
        def start_camera():
            """Start processing from camera."""
            data = request.get_json() or {}
            camera_index = data.get('camera_index', 0)
            
            if self.process_callback:
                threading.Thread(
                    target=self._process_camera,
                    args=(camera_index,),
                    daemon=True
                ).start()
            
            return jsonify({
                'success': True,
                'camera_index': camera_index,
                'message': 'Camera processing started.'
            })
        
        @self.app.route('/api/stop', methods=['POST'])
        def stop_processing():
            """Stop current processing."""
            self.is_processing = False
            if self.stop_callback:
                self.stop_callback()
            self.socketio.emit('processing_stopped', {})
            return jsonify({'success': True, 'message': 'Processing stopped.'})
        
        @self.app.route('/api/reset_counts', methods=['POST'])
        def reset_counts():
            """Reset counting."""
            if self.reset_callback:
                self.reset_callback()
            self.socketio.emit('counts_reset', {})
            return jsonify({'success': True, 'message': 'Counts reset.'})
        
        @self.app.route('/api/image_result')
        def get_image_result():
            """Get processed image result."""
            return jsonify(self.image_results)
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection."""
            print("Client connected")
            with self.data_lock:
                if self.current_data:
                    emit('update', self.current_data.to_dict())
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            print("Client disconnected")
    
    def _process_uploaded_file(self, filepath: str) -> None:
        """Process uploaded file."""
        self.is_processing = True
        self.socketio.emit('processing_started', {'source': filepath, 'type': 'upload'})
        
        if self.process_callback:
            try:
                self.process_callback(filepath)
            except Exception as e:
                self.socketio.emit('processing_error', {'error': str(e)})
            finally:
                self.is_processing = False
                self.socketio.emit('processing_completed', {})
    
    def _process_batch_files(self, files: list) -> None:
        """Process multiple image files in batch."""
        self.is_processing = True
        self.socketio.emit('processing_started', {
            'source': 'batch',
            'type': 'batch_upload',
            'file_count': len(files)
        })
        
        self.batch_results = []
        batch_totals = {
            'total': 0,
            'fingerling': 0,
            'post_fingerling': 0,
            'juvenile': 0,
            'unknown': 0
        }
        
        # Process each file
        for idx, file_info in enumerate(files):
            try:
                # Emit processing update
                self.socketio.emit('batch_file_processing', {
                    'filename': file_info['filename'],
                    'index': idx + 1,
                    'total': len(files)
                })
                
                # Process file through counter if available
                result_data = {'counts': {}, 'annotated_image': None}
                
                # Try to use counter for direct processing with annotations
                if hasattr(self, 'counter') and self.counter:
                    try:
                        result_data = self.counter.process_image_file(file_info['filepath'], no_annotations=False)
                    except Exception as e:
                        print(f"Error processing {file_info['filename']} with counter: {e}")
                        if self.process_callback:
                            self.process_callback(file_info['filepath'])
                            result_data = self.image_results if self.image_results else {'counts': {}}
                elif self.process_callback:
                    self.process_callback(file_info['filepath'])
                    result_data = self.image_results if self.image_results else {'counts': {}}

                counts = result_data.get('counts', {})
                
                # Build per-class count details
                counts_by_class = {
                    'fingerling': int(counts.get('fingerling', 0) or 0),
                    'post_fingerling': int(counts.get('post_fingerling', 0) or 0),
                    'juvenile': int(counts.get('juvenile', 0) or 0),
                    'unknown': int(counts.get('unknown', 0) or 0),
                    'total': int(counts.get('total', 0) or 0)
                }
                
                # Update batch totals
                for key in batch_totals:
                    batch_totals[key] += counts_by_class.get(key, 0)
                
                # Convert annotated image to base64 if available
                image_base64 = None
                try:
                    annotated_image = result_data.get('annotated_image')
                    if annotated_image is not None:
                        _, buffer = cv2.imencode('.jpg', annotated_image)
                        image_base64 = base64.b64encode(buffer).decode('utf-8')
                except Exception as e:
                    print(f"Failed to encode image: {e}")
                
                # Build label summary
                label_summary_parts = []
                for class_key in ['fingerling', 'post_fingerling', 'juvenile']:
                    class_count = counts_by_class.get(class_key, 0)
                    if class_count > 0:
                        label_summary_parts.append(f"{class_key.replace('_', ' ').title()}: {class_count}")
                
                if counts_by_class.get('unknown', 0) > 0:
                    label_summary_parts.append(f"Unknown: {counts_by_class['unknown']}")
                
                self.batch_results.append({
                    'filename': file_info['filename'],
                    'status': 'success',
                    'counts': counts_by_class,
                    'detections': result_data.get('detections', 0),
                    'label_summary': ', '.join(label_summary_parts) if label_summary_parts else 'No detections',
                    'annotated_image': image_base64
                })
            except Exception as e:
                self.batch_results.append({
                    'filename': file_info['filename'],
                    'status': 'error',
                    'error': str(e)
                })
        
        # Emit batch results with batch totals
        self.socketio.emit('batch_results', {
            'total_files': len(files),
            'batch_totals': batch_totals,
            'results': self.batch_results
        })

        # Save CSV summary for this batch
        try:
            out_root = Path(__file__).resolve().parents[2]
            out_dir = out_root / 'output' / 'batch_summaries'
            out_dir.mkdir(parents=True, exist_ok=True)
            csv_path = out_dir / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            import csv as _csv
            with open(csv_path, 'w', newline='', encoding='utf-8') as _f:
                writer = _csv.writer(_f)
                writer.writerow(['filename','total','fingerling','post_fingerling','juvenile','unknown','detections','label_summary'])
                for r in self.batch_results:
                    counts = r.get('counts', {}) or {}
                    writer.writerow([
                        r.get('filename',''),
                        int(counts.get('total', 0) or 0),
                        int(counts.get('fingerling', 0) or 0),
                        int(counts.get('post_fingerling', 0) or 0),
                        int(counts.get('juvenile', 0) or 0),
                        int(counts.get('unknown', 0) or 0),
                        int(r.get('detections', 0) or 0),
                        r.get('label_summary','')
                    ])

            # Notify clients that CSV was saved
            try:
                self.socketio.emit('batch_csv_saved', {'csv_path': str(csv_path)})
            except:
                pass
        except Exception as e:
            print(f"Failed to write batch CSV: {e}")

        self.is_processing = False
        self.socketio.emit('processing_completed', {})
    
    def _process_url(self, url: str) -> None:
        """Process URL source."""
        self.is_processing = True
        self.socketio.emit('processing_started', {'source': url, 'type': 'url'})
        
        if self.process_callback:
            try:
                self.process_callback(url)
            except Exception as e:
                self.socketio.emit('processing_error', {'error': str(e)})
            finally:
                self.is_processing = False
                self.socketio.emit('processing_completed', {})
    
    def _process_camera(self, camera_index: int) -> None:
        """Process camera source."""
        self.is_processing = True
        self.socketio.emit('processing_started', {'source': camera_index, 'type': 'camera'})
        
        if self.process_callback:
            try:
                self.process_callback(camera_index)
            except Exception as e:
                self.socketio.emit('processing_error', {'error': str(e)})
            finally:
                self.is_processing = False
                self.socketio.emit('processing_completed', {})
    
    def _generate_frames(self) -> Generator[bytes, None, None]:
        """Generate MJPEG frames."""
        while self.is_running:
            try:
                frame = self.frame_queue.get(timeout=1.0)
                
                # Encode as JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                       
            except Empty:
                continue
            except Exception as e:
                print(f"Error generating frame: {e}")
                break
    
    def update_frame(self, frame: np.ndarray) -> None:
        """
        Update current frame for streaming.

        Emits the annotated frame to all connected Socket.IO clients as a
        base64-encoded JPEG (≤640 px wide, quality 65) at a capped rate of
        ~8 fps.  This is the primary delivery path for cross-origin web
        clients (Vercel → Render).  The MJPEG /video_feed endpoint remains
        available for same-origin / local use.

        Args:
            frame: Annotated video frame (BGR, any resolution).
        """
        with self.frame_lock:
            self.current_frame = frame.copy()

        # MJPEG queue (local / same-origin /video_feed endpoint)
        try:
            if self.frame_queue.full():
                self.frame_queue.get_nowait()
            self.frame_queue.put_nowait(frame)
        except Exception:
            pass

        # Socket.IO frame — rate-limited to ~8 fps
        now = time.time()
        if now - self._last_frame_emit < self._FRAME_MIN_INTERVAL:
            return
        self._last_frame_emit = now
        try:
            h, w = frame.shape[:2]
            if w > 640:
                scale = 640.0 / w
                small = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
            else:
                small = frame
            _, buf = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 65])
            b64 = base64.b64encode(buf).decode('ascii')
            self.socketio.emit('frame', {'img': b64})
        except Exception:
            pass
    
    def update_data(
        self,
        frame_number: int,
        counts: Dict[str, int],
        current_detections: int,
        active_tracks: int,
        size_distribution: Dict[str, int],
        fps: float,
        source_type: str = "video",
        is_live: bool = False
    ) -> None:
        """
        Update current counting data.
        
        Args:
            frame_number: Current frame number.
            counts: Total counts by category.
            current_detections: Number of detections in current frame.
            active_tracks: Number of active tracks.
            size_distribution: Current size distribution.
            fps: Current processing FPS.
            source_type: Type of video source.
            is_live: Whether source is live.
        """
        data = StreamData(
            timestamp=datetime.now().isoformat(),
            frame_number=frame_number,
            counts=counts,
            current_detections=current_detections,
            active_tracks=active_tracks,
            size_distribution=size_distribution,
            fps=fps,
            source_type=source_type,
            is_live=is_live
        )
        
        with self.data_lock:
            self.current_data = data
        
        # Emit WebSocket update
        try:
            self.socketio.emit('update', data.to_dict())
        except:
            pass
    
    def set_image_result(self, result: Dict[str, Any]) -> None:
        """Store image processing result."""
        self.image_results = result
        try:
            self.socketio.emit('image_result', result)
        except:
            pass
    
    def start(self, background: bool = True) -> None:
        """
        Start the streaming server.
        
        Args:
            background: Run in background thread.
        """
        self.is_running = True
        
        if background:
            thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            thread.start()
            print(f"Streaming server started at http://{self.host}:{self.port}")
        else:
            self._run_server()
    
    def _run_server(self) -> None:
        """Run the Flask server."""
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False
        )
    
    def stop(self) -> None:
        """Stop the streaming server."""
        self.is_running = False


class ConsoleStreamer:
    """
    Console-based streaming for real-time count updates.
    
    Useful for headless environments or simple monitoring.
    """
    
    def __init__(self, update_interval: float = 0.5):
        """
        Initialize console streamer.
        
        Args:
            update_interval: Seconds between updates.
        """
        self.update_interval = update_interval
        self.last_update = 0.0
    
    def update(
        self,
        frame_number: int,
        counts: Dict[str, int],
        size_distribution: Dict[str, int],
        fps: float
    ) -> None:
        """
        Print update to console.
        
        Args:
            frame_number: Current frame number.
            counts: Total counts.
            size_distribution: Current distribution.
            fps: Processing FPS.
        """
        current_time = time.time()
        
        if current_time - self.last_update < self.update_interval:
            return
        
        self.last_update = current_time
        
        # Clear line and print update
        total = counts.get('total', 0)
        fingerling = counts.get('fingerling', 0)
        post_fingerling = counts.get('post_fingerling', 0)
        juvenile = counts.get('juvenile', 0)
        unknown = counts.get('unknown', 0)
        
        print(
            f"\rFrame: {frame_number:6d} | "
            f"Total: {total:5d} | "
            f"F: {fingerling:4d} | "
            f"P: {post_fingerling:4d} | "
            f"J: {juvenile:4d} | "
            f"U: {unknown:4d} | "
            f"FPS: {fps:5.1f}",
            end='',
            flush=True
        )
    
    def print_summary(self, counts: Dict[str, int]) -> None:
        """Print final summary."""
        print("\n\n" + "=" * 50)
        print("FINAL COUNT SUMMARY")
        print("=" * 50)
        print(f"Total Fingerlings: {counts.get('total', 0)}")
        print(f"  - Fingerling:      {counts.get('fingerling', 0)}")
        print(f"  - Post-Fingerling: {counts.get('post_fingerling', 0)}")
        print(f"  - Juvenile:        {counts.get('juvenile', 0)}")
        print(f"  - Unknown:         {counts.get('unknown', 0)}")
        print("=" * 50)


class CSVLogger:
    """
    CSV logger for saving count data over time.
    """
    
    def __init__(self, output_path: str, class_keys: Optional[list] = None):
        """
        Initialize CSV logger.
        
        Args:
            output_path: Path to output CSV file.
        """
        from pathlib import Path
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.class_keys = class_keys or ['fingerling', 'post_fingerling', 'juvenile']
        
        # Write header
        with open(self.output_path, 'w') as f:
            class_columns = ','.join(self.class_keys + ['unknown'])
            f.write(f"timestamp,frame,total,{class_columns},fps\\n")
    
    def log(
        self,
        frame_number: int,
        counts: Dict[str, int],
        fps: float
    ) -> None:
        """
        Log current counts to CSV.
        
        Args:
            frame_number: Current frame number.
            counts: Count dictionary.
            fps: Processing FPS.
        """
        timestamp = datetime.now().isoformat()
        class_values = [str(counts.get(class_key, 0)) for class_key in self.class_keys]
        class_values.append(str(counts.get('unknown', 0)))
        
        with open(self.output_path, 'a') as f:
            f.write(
                f"{timestamp},"
                f"{frame_number},"
                f"{counts.get('total', 0)},"
                f"{','.join(class_values)},"
                f"{fps:.2f}\n"
            )


# HTML template for web dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Fingerling Counter Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <!-- Chart.js removed -->
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .dashboard {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            max-width: 1600px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        h1 {
            font-size: 2em;
            color: #00d4ff;
        }
        h2 {
            margin-bottom: 15px;
            color: #00d4ff;
        }
        .video-container {
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }
        .video-container img {
            width: 100%;
            border-radius: 10px;
        }
        .live-indicator {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #ff0000;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.8em;
            animation: pulse 1s infinite;
            display: none;
        }
        .live-indicator.active {
            display: block;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        .stat-box {
            background: rgba(0, 212, 255, 0.1);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid rgba(0, 212, 255, 0.3);
        }
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
        }
        .stat-label {
            font-size: 0.9em;
            color: #aaa;
            margin-top: 5px;
        }
        .fingerling { color: #00ff00; }
        .post-fingerling { color: #ffbf00; }
        .juvenile { color: #ffa500; }
        .unknown { color: #a0a0a0; }
        .total { color: #00d4ff; }
        /* Chart UI removed per user request */
        .status-bar {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            padding: 10px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 5px;
            font-size: 0.9em;
        }
        .upload-section {
            margin-top: 20px;
        }
        .input-group {
            margin-bottom: 15px;
        }
        .input-group label {
            display: block;
            margin-bottom: 5px;
            color: #aaa;
        }
        .input-group input[type="text"],
        .input-group input[type="file"] {
            width: 100%;
            padding: 10px;
            border: 1px solid rgba(0, 212, 255, 0.3);
            border-radius: 5px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
        }
        .input-group input[type="file"] {
            cursor: pointer;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            margin-right: 10px;
            margin-bottom: 10px;
            transition: all 0.3s;
        }
        .btn-primary {
            background: #00d4ff;
            color: #000;
        }
        .btn-primary:hover {
            background: #00a8cc;
        }
        .btn-success {
            background: #00ff00;
            color: #000;
        }
        .btn-danger {
            background: #ff4444;
            color: #fff;
        }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.2);
            color: #fff;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .button-group {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .processing-status {
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            display: none;
        }
        .processing-status.active {
            display: block;
            background: rgba(0, 212, 255, 0.2);
            animation: pulse 2s infinite;
        }
        .processing-status.error {
            display: block;
            background: rgba(255, 0, 0, 0.2);
        }
        .processing-status.success {
            display: block;
            background: rgba(0, 255, 0, 0.2);
        }
        .tabs {
            display: flex;
            margin-bottom: 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.3s;
        }
        .tab.active {
            color: #00d4ff;
            border-bottom-color: #00d4ff;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .source-info {
            font-size: 0.8em;
            color: #888;
            margin-top: 5px;
        }
        @media (max-width: 1200px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐟 Catfish Fingerling Counter</h1>
        <div>
            <span id="connection-status" style="color: #00ff00;">● Connected</span>
        </div>
    </div>
    
    <div class="dashboard">
        <div>
            <div class="card">
                <h2>Live Video Feed</h2>
                <div class="video-container">
                    <img alt="Video Feed" id="video-feed">
                    <div class="live-indicator" id="live-indicator">🔴 LIVE</div>
                </div>
                <div class="status-bar">
                    <span>Frame: <span id="frame">0</span></span>
                    <span>FPS: <span id="fps">0</span></span>
                    <span>Source: <span id="source-type">-</span></span>
                    <span id="timestamp"></span>
                </div>
            </div>
            
            <div class="card upload-section">
                <h2>Input Source</h2>
                <div class="tabs">
                    <div class="tab active" data-tab="camera">Camera</div>
                    <div class="tab" data-tab="upload">Upload File</div>
                    <div class="tab" data-tab="batch">Batch Images</div>
                    <div class="tab" data-tab="url">Video URL</div>
                </div>
                
                <div class="tab-content active" id="tab-camera">
                    <div class="input-group">
                        <label>Camera Index (0 = default webcam)</label>
                        <input type="text" id="camera-index" value="0" placeholder="0">
                    </div>
                    <button class="btn btn-success" onclick="startCamera()">📷 Start Camera</button>
                </div>
                
                <div class="tab-content" id="tab-upload">
                    <div class="input-group">
                        <label>Upload Video or Image</label>
                        <input type="file" id="file-input" accept="video/*,image/*">
                    </div>
                    <button class="btn btn-primary" onclick="uploadFile()">📤 Upload & Process</button>
                </div>
                
                <div class="tab-content" id="tab-batch">
                    <div class="input-group">
                        <label>Upload Multiple Images for Batch Analysis</label>
                        <input type="file" id="batch-file-input" accept="image/*" multiple>
                    </div>
                    <div style="font-size: 0.85em; color: #888; margin-bottom: 15px;">
                        Select multiple image files to process. Results will show annotated images with detailed counts per class.
                    </div>
                    <button class="btn btn-primary" onclick="uploadBatch()">📁 Upload & Analyze</button>
                    <div id="batch-progress" style="margin-top: 10px; display: none;">
                        <div style="font-size: 0.9em; color: #00d4ff;">Files processed: <span id="batch-count">0</span></div>
                        <div id="batch-results-list" style="max-height: 600px; overflow-y: auto; margin-top: 10px; font-size: 0.85em;"></div>
                    </div>
                </div>
                
                <div class="tab-content" id="tab-url">
                    <div class="input-group">
                        <label>Video URL (YouTube, direct link, RTSP)</label>
                        <input type="text" id="url-input" placeholder="https://www.youtube.com/watch?v=...">
                    </div>
                    <button class="btn btn-primary" onclick="processUrl()">🔗 Process URL</button>
                </div>
                
                <div class="button-group" style="margin-top: 15px;">
                    <button class="btn btn-danger" onclick="stopProcessing()">⏹ Stop</button>
                    <button class="btn btn-secondary" onclick="resetCounts()">🔄 Reset Counts</button>
                </div>
                
                <div class="processing-status" id="processing-status">
                    <span id="status-message">Processing...</span>
                </div>
            </div>
        </div>
        
        <div>
            <div class="card">
                <h2>Count Summary</h2>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-value total" id="total">0</div>
                        <div class="stat-label">Total Counted</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value fingerling" id="fingerling">0</div>
                        <div class="stat-label">Fingerling</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value post-fingerling" id="post_fingerling">0</div>
                        <div class="stat-label">Post-Fingerling</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value juvenile" id="juvenile">0</div>
                        <div class="stat-label">Juvenile</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value unknown" id="unknown">0</div>
                        <div class="stat-label">Unknown</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="active" style="color: #9b59b6;">0</div>
                        <div class="stat-label">Current Visible</div>
                    </div>
                </div>
            </div>
            
            <!-- Class Distribution chart removed -->
            
            <div class="card" style="margin-top: 20px;">
                <h2>Instructions</h2>
                <ul style="padding-left: 20px; line-height: 1.8;">
                    <li>Select input source (camera, file, or URL)</li>
                    <li>Fingerlings crossing the line are counted</li>
                    <li>Counts are grouped by class labels automatically</li>
                    <li>Click "Reset Counts" to start over</li>
                    <li>Supports: MP4, AVI, MOV, JPG, PNG</li>
                    <li>YouTube URLs supported with yt-dlp</li>
                </ul>
            </div>
        </div>
    </div>
    
    <script>
        const socket = io({ transports: ['polling'], upgrade: false });
        let isProcessing = false;
        
        // Chart removed: distribution chart disabled per user request
        
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
            });
        });
        
        // Socket events
        function setVideoFeedActive(active) {
            const videoFeed = document.getElementById('video-feed');
            if (active) {
                videoFeed.src = '/video_feed?ts=' + Date.now();
            } else {
                videoFeed.removeAttribute('src');
            }
        }

        socket.on('update', function(data) {
            document.getElementById('total').textContent = data.counts.total || 0;
            document.getElementById('fingerling').textContent = data.counts.fingerling || 0;
            document.getElementById('post_fingerling').textContent = data.counts.post_fingerling || 0;
            document.getElementById('juvenile').textContent = data.counts.juvenile || 0;
            document.getElementById('unknown').textContent = data.counts.unknown || 0;
            document.getElementById('active').textContent = data.active_tracks || 0;
            document.getElementById('frame').textContent = data.frame_number;
            document.getElementById('fps').textContent = data.fps.toFixed(1);
            document.getElementById('source-type').textContent = data.source_type || 'video';
            document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();
            
            const liveIndicator = document.getElementById('live-indicator');
            if (data.is_live) {
                liveIndicator.classList.add('active');
            } else {
                liveIndicator.classList.remove('active');
            }
            
            // distribution chart removed; UI shows numeric stats only
        });

        socket.on('connect', function() {
            document.getElementById('connection-status').innerHTML = '● Connected';
            document.getElementById('connection-status').style.color = '#00ff00';
        });

        socket.on('disconnect', function() {
            document.getElementById('connection-status').innerHTML = '● Disconnected';
            document.getElementById('connection-status').style.color = '#ff0000';
        });

        socket.on('processing_started', function(data) {
            isProcessing = true;
            if (data.type === 'camera' || data.type === 'upload' || data.type === 'url') {
                setVideoFeedActive(true);
            }
            showStatus('Processing started: ' + (data.source || 'unknown'), 'active');
        });

        socket.on('processing_completed', function() {
            isProcessing = false;
            setVideoFeedActive(false);
            showStatus('Processing completed', 'success');
        });

        socket.on('processing_error', function(data) {
            isProcessing = false;
            setVideoFeedActive(false);
            showStatus('Error: ' + data.error, 'error');
        });

        socket.on('counts_reset', function() {
            document.getElementById('total').textContent = '0';
            document.getElementById('fingerling').textContent = '0';
            document.getElementById('post_fingerling').textContent = '0';
            document.getElementById('juvenile').textContent = '0';
            document.getElementById('unknown').textContent = '0';
            document.getElementById('active').textContent = '0';
            // distribution chart removed; reset handled by numeric UI
            setVideoFeedActive(false);
        });

        socket.on('batch_results', function(data) {
            const resultsList = document.getElementById('batch-results-list');
            let html = '<div style="border-top: 1px solid rgba(255,255,255,0.2); padding-top: 10px;">';
            
            // Display batch totals summary
            const batchTotals = data.batch_totals || {};
            html += `<div style="background: rgba(0, 212, 255, 0.1); padding: 10px; border-radius: 5px; margin-bottom: 15px; border-left: 3px solid #00d4ff;">
                <div style="font-weight: bold; color: #00d4ff; margin-bottom: 5px;">📊 Batch Totals by Type</div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 0.85em;">
                    <div><span style="color: #00d4ff;">Total:</span> <span style="color: #fff; font-weight: bold;">${batchTotals.total || 0}</span></div>
                    <div><span style="color: #00ff00;">Fingerling:</span> <span style="color: #00ff00; font-weight: bold;">${batchTotals.fingerling || 0}</span></div>
                    <div><span style="color: #ffbf00;">Post-Fingerling:</span> <span style="color: #ffbf00; font-weight: bold;">${batchTotals.post_fingerling || 0}</span></div>
                    <div><span style="color: #ffa500;">Juvenile:</span> <span style="color: #ffa500; font-weight: bold;">${batchTotals.juvenile || 0}</span></div>
                    <div><span style="color: #a0a0a0;">Unknown:</span> <span style="color: #a0a0a0; font-weight: bold;">${batchTotals.unknown || 0}</span></div>
                </div>
            </div>`;
            
            // Display per-image results with annotations
            html += '<div style="font-weight: bold; color: #00d4ff; margin-bottom: 10px;">🖼️ Per-Image Results</div>';

            data.results.forEach((result, idx) => {
                const status = result.status === 'success' ? '✓' : '✗';
                const color = result.status === 'success' ? '#00ff00' : '#ff4444';
                
                html += `<div style="background: rgba(255,255,255,0.05); border-left: 3px solid ${color}; padding: 10px; margin-bottom: 10px; border-radius: 3px;">
                    <div style="color: ${color}; font-weight: bold; margin-bottom: 8px;">${status} ${result.filename}</div>`;
                
                if (result.status === 'success') {
                    const counts = result.counts || {};
                    
                    // Show annotated image if available
                    if (result.annotated_image) {
                        html += `<img src="data:image/jpeg;base64,${result.annotated_image}" style="width: 100%; max-width: 200px; border-radius: 5px; margin-bottom: 8px; border: 1px solid rgba(0,212,255,0.3);">`;
                    }
                    
                    // Show per-image counts by class
                    html += `<div style="font-size: 0.85em; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
                        <div><span style="color: #00d4ff;">Total:</span> <span style="font-weight: bold;">${counts.total || 0}</span></div>
                        <div><span style="color: #00ff00;">Fingerling:</span> <span style="color: #00ff00; font-weight: bold;">${counts.fingerling || 0}</span></div>
                        <div><span style="color: #ffbf00;">Post-Fingerling:</span> <span style="color: #ffbf00; font-weight: bold;">${counts.post_fingerling || 0}</span></div>
                        <div><span style="color: #ffa500;">Juvenile:</span> <span style="color: #ffa500; font-weight: bold;">${counts.juvenile || 0}</span></div>
                        <div><span style="color: #a0a0a0;">Unknown:</span> <span style="color: #a0a0a0; font-weight: bold;">${counts.unknown || 0}</span></div>
                    </div>`;
                    
                    // Show label summary
                    const labelSummary = result.label_summary || 'No detections';
                    html += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1); color: #aaa; font-size: 0.8em;">Summary: ${labelSummary}</div>`;
                } else if (result.error) {
                    html += `<div style="color: #ff4444; font-size: 0.85em;">Error: ${result.error}</div>`;
                }
                
                html += '</div>';
            });

            html += '</div>';
            resultsList.innerHTML = html;
            showStatus(`Batch processing complete: ${data.total_files} file(s)`, 'success');
        });

        socket.on('batch_csv_saved', function(data) {
            showStatus('Batch CSV saved: ' + data.csv_path, 'success');
        });

        function showStatus(message, type) {
            const statusEl = document.getElementById('processing-status');
            const msgEl = document.getElementById('status-message');
            statusEl.className = 'processing-status ' + type;
            msgEl.textContent = message;
        }
        
        function startCamera() {
            const index = document.getElementById('camera-index').value || 0;
            fetch('/api/start_camera', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({camera_index: parseInt(index)})
            }).then(r => r.json()).then(data => {
                if (data.success) showStatus('Starting camera...', 'active');
            });
        }
        
        function uploadFile() {
            const fileInput = document.getElementById('file-input');
            if (!fileInput.files.length) {
                alert('Please select a file');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            
            showStatus('Uploading file...', 'active');
            
            fetch('/api/upload', {
                method: 'POST',
                body: formData
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    showStatus('File uploaded, processing...', 'active');
                } else {
                    showStatus('Upload failed: ' + data.error, 'error');
                }
            }).catch(err => {
                showStatus('Upload error: ' + err, 'error');
            });
        }
        
        function uploadBatch() {
            const fileInput = document.getElementById('batch-file-input');
            if (!fileInput.files.length) {
                alert('Please select at least one image');
                return;
            }
            
            const formData = new FormData();
            for (let i = 0; i < fileInput.files.length; i++) {
                formData.append('files', fileInput.files[i]);
            }
            
            showStatus(`Uploading ${fileInput.files.length} image(s)...`, 'active');
            document.getElementById('batch-progress').style.display = 'block';
            document.getElementById('batch-results-list').innerHTML = '';
            
            fetch('/api/upload_batch', {
                method: 'POST',
                body: formData
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    showStatus(`Batch upload complete: ${data.count} file(s). Processing...`, 'active');
                    document.getElementById('batch-count').textContent = data.count;
                } else {
                    showStatus('Batch upload failed: ' + data.error, 'error');
                    document.getElementById('batch-progress').style.display = 'none';
                }
            }).catch(err => {
                showStatus('Batch upload error: ' + err, 'error');
                document.getElementById('batch-progress').style.display = 'none';
            });
        }
        
        function processUrl() {
            const url = document.getElementById('url-input').value;
            if (!url) {
                alert('Please enter a URL');
                return;
            }
            
            fetch('/api/process_url', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: url})
            }).then(r => r.json()).then(data => {
                if (data.success) showStatus('Processing URL...', 'active');
            });
        }
        
        function stopProcessing() {
            fetch('/api/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => showStatus('Processing stopped', 'success'));
        }
        
        function resetCounts() {
            fetch('/api/reset_counts', {method: 'POST'});
        }
    </script>
</body>
</html>
"""
