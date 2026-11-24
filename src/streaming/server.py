"""
Streaming Server for Fingerling Counter

Provides real-time streaming of video and counting data
via HTTP/WebSocket endpoints with file upload support.
"""

import json
import time
import threading
import base64
import ipaddress
import os
import re
import shutil
import tempfile
import uuid
from typing import Dict, Any, Optional, Generator, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from queue import Queue, Empty
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np

try:
    from flask import Flask, Response, g, jsonify, request
    from flask_cors import CORS
    from flask_socketio import SocketIO, emit
    from werkzeug.utils import secure_filename
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Warning: Flask not available. Install with: pip install flask flask-socketio")

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,120}$')
# How a job started from the dashboard is labelled in run history.
JOB_KIND_TO_RUN_KIND = {'upload': 'video', 'url': 'url', 'camera': 'camera', 'batch_upload': 'batch'}


def is_safe_media_url(url: str) -> tuple[bool, str]:
    """Validate media URL scheme and reject loopback / cloud-metadata SSRF targets.

    RFC1918 LAN addresses (e.g. 192.168.x.x phone IP-camera apps on hatchery Wi-Fi)
    are intentionally allowed. Set ALLOW_LOCAL_URLS=1 to allow loopback for local tests.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, 'Malformed URL'

    if parsed.scheme.lower() not in ('http', 'https', 'rtsp', 'rtmp'):
        return False, 'URL must start with http(s)://, rtsp:// or rtmp://'

    host = (parsed.hostname or '').strip().lower()
    if not host:
        return False, 'URL is missing a hostname'

    if os.environ.get('ALLOW_LOCAL_URLS') == '1':
        return True, ''

    if host in ('localhost', 'localhost.localdomain') or host.endswith('.localhost'):
        return False, 'Loopback URLs are not allowed'

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
            return False, 'Loopback and link-local/metadata addresses are not allowed'
    except ValueError:
        pass  # domain name, not an IP literal

    return True, ''


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
        reset_callback: Optional[Callable] = None,
        runs_dir: Optional[str] = None,
        database_url: Optional[str] = None
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
            runs_dir: Folder holding per-run records (served for download).
            database_url: Accounts/history database (default: DATABASE_URL env, else
                SQLite in instance/).
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
        self.runs_dir = Path(runs_dir) if runs_dir else REPO_ROOT / 'output' / 'runs'

        # One job at a time. _job_seq identifies the newest job so that a job
        # which was stopped and replaced does not report "completed" over it.
        self._job_state_lock = threading.Lock()
        self._job_seq = 0
        self._worker_thread: Optional[threading.Thread] = None
        # Who started the running job and what it is (shown to other operators).
        self._job_info: Optional[Dict[str, Any]] = None
        # Owner/kind of the job running on the current worker thread, so run records
        # saved from deep inside the counting loop land in the right user's history.
        self._job_ctx = threading.local()
        # Set by the API layer: persists each saved run (summary, kind, owner_id).
        self.on_run_saved: Optional[Callable[[Dict[str, Any], str, Optional[int]], None]] = None

        # Settings in a .env file at the repo root (hatchery laptop) apply before anything reads them.
        from api.config import load_dotenv
        load_dotenv()

        # Flask app
        self.app = Flask(__name__)
        cors_env = os.environ.get('CORS_ORIGINS', '*').strip() or '*'
        cors_origins = '*' if cors_env == '*' else [o.strip() for o in cors_env.split(',') if o.strip()]
        # Data calls use a bearer token, not cookies, so credentials are only needed
        # when origins are listed explicitly (cross-site refresh cookie setups).
        CORS(self.app, resources={r"/*": {"origins": cors_origins}},
             expose_headers=['Retry-After'], supports_credentials=cors_origins != '*')
        self.app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24).hex()
        self.app.config['UPLOAD_FOLDER'] = self.upload_folder
        self.app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
        self.socketio = SocketIO(self.app, cors_allowed_origins=cors_origins, async_mode='threading')
        
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

        # Accounts, sign-in, per-user history and the web app (src/api).
        from api import init_api
        self.api = init_api(self.app, self, database_url=database_url)
    
    def _allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def _setup_routes(self) -> None:
        """Setup the counting-station routes.

        The web app, accounts, run history and downloads live in src/api, which also
        puts every route here behind sign-in (see api._install_guard).
        """
        from api.http import rate_limit

        # Starting jobs is cheap to request and expensive to run.
        limit_jobs = rate_limit('start-job', 30, 60, by='user')

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
                data = self.current_data.to_dict() if self.current_data else {'status': 'no data'}
            data['is_processing'] = self.is_processing
            data['job'] = self._public_job_info()
            return jsonify(data)
        
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
        @limit_jobs
        def upload_file():
            """Handle file upload."""
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            if file and self._allowed_file(file.filename):
                if self.is_processing:
                    return self._busy_response()
                if not self.process_callback:
                    return jsonify({'error': 'Server is not accepting jobs'}), 503
                filename, filepath, upload_dir = self._save_upload(file)
                if not self._start_job('upload', filename, self.process_callback, (filepath,),
                                       cleanup=[upload_dir], owner=self._actor()):
                    shutil.rmtree(upload_dir, ignore_errors=True)
                    return self._busy_response()

                return jsonify({
                    'success': True,
                    'filename': filename,
                    'message': 'File uploaded successfully. Processing started.'
                })
            
            return jsonify({'error': 'File type not allowed'}), 400
        
        @self.app.route('/api/upload_batch', methods=['POST'])
        @limit_jobs
        def upload_batch():
            """Handle multiple image uploads for batch processing."""
            if 'files' not in request.files:
                return jsonify({'error': 'No files provided'}), 400
            
            files = request.files.getlist('files')
            if not files:
                return jsonify({'error': 'No files selected'}), 400
            
            if self.is_processing:
                return self._busy_response()

            uploaded_files = []
            upload_dirs = []
            for file in files:
                if file.filename and self._allowed_file(file.filename):
                    filename, filepath, upload_dir = self._save_upload(file)
                    upload_dirs.append(upload_dir)
                    uploaded_files.append({'filename': filename, 'filepath': filepath})

            if uploaded_files:
                runner = self._process_batch_files
                if getattr(self, 'counter', None) is not None:
                    # Same queue as video jobs, so a batch never overlaps a count.
                    runner = lambda f: self.counter.run_exclusive(self._process_batch_files, f)
                if not self._start_job('batch_upload', f'{len(uploaded_files)} image(s)', runner,
                                       (uploaded_files,), cleanup=upload_dirs, owner=self._actor()):
                    for d in upload_dirs:
                        shutil.rmtree(d, ignore_errors=True)
                    return self._busy_response()

                return jsonify({
                    'success': True,
                    'files': [{'filename': f['filename']} for f in uploaded_files],
                    'count': len(uploaded_files),
                    'message': f'Uploaded {len(uploaded_files)} file(s). Processing started.'
                })
            
            return jsonify({'error': 'No valid files provided'}), 400
        
        @self.app.route('/api/process_url', methods=['POST'])
        @limit_jobs
        def process_url():
            """Process video/image from URL."""
            data = request.get_json(silent=True)
            if not data or 'url' not in data:
                return jsonify({'error': 'No URL provided'}), 400
            
            url = str(data['url']).strip()
            url_ok, url_err = is_safe_media_url(url)
            if not url_ok:
                return jsonify({'error': url_err}), 400
            if not self.process_callback:
                return jsonify({'error': 'Server is not accepting jobs'}), 503
            if not self._start_job('url', url, self.process_callback, (url,), owner=self._actor()):
                return self._busy_response()

            return jsonify({
                'success': True,
                'url': url,
                'message': 'URL processing started.'
            })
        
        @self.app.route('/api/start_camera', methods=['POST'])
        @limit_jobs
        def start_camera():
            """Start processing from camera."""
            data = request.get_json(silent=True) or {}
            try:
                camera_index = int(data.get('camera_index', 0))
            except (TypeError, ValueError):
                return jsonify({'error': 'camera_index must be a whole number'}), 400
            if not self.process_callback:
                return jsonify({'error': 'Server is not accepting jobs'}), 503
            if not self._start_job('camera', f'camera {camera_index}', self.process_callback,
                                   (camera_index,), owner=self._actor()):
                return self._busy_response()

            return jsonify({
                'success': True,
                'camera_index': camera_index,
                'message': 'Camera processing started.'
            })
        
        @self.app.route('/api/stop', methods=['POST'])
        def stop_processing():
            """Signal active processing to stop cleanly.

            Do not clear `is_processing` while the worker thread is still wrapping
            up its current frame and saving the run record; the worker's `finally`
            block clears `is_processing` once teardown is complete.
            """
            with self._job_state_lock:
                worker_alive = bool(self._worker_thread and self._worker_thread.is_alive())
                if not worker_alive:
                    self.is_processing = False
            if self.stop_callback:
                self.stop_callback()
            self.socketio.emit('processing_stopped', {})
            return jsonify({'success': True, 'message': 'Stop requested.' if worker_alive else 'Processing stopped.'})
        
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
        def handle_connect(auth=None):
            """Only signed-in dashboards receive frames and counts."""
            from api import authenticate_token
            token = (auth or {}).get('token') if isinstance(auth, dict) else None
            user, _claims, _code = authenticate_token(self.api, str(token or ''), 'access')
            if user is None:
                raise ConnectionRefusedError('unauthorized')
            with self.data_lock:
                if self.current_data:
                    emit('update', self.current_data.to_dict())
        
        @self.socketio.on('disconnect')
        def handle_disconnect(*_args):
            pass
    
    def _busy_response(self):
        return jsonify({
            'error': 'A count is already running. Stop it before starting another.',
            'busy': True
        }), 409

    def _save_upload(self, file):
        """Save an upload in its own folder: no name collisions, and easy to delete afterwards."""
        original = Path(file.filename)
        stem = secure_filename(original.stem) or 'upload'
        ext = original.suffix.lower()
        upload_dir = os.path.join(self.upload_folder, uuid.uuid4().hex[:12])
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{stem}{ext}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        return filename, filepath, upload_dir

    @staticmethod
    def _actor() -> Optional[Dict[str, Any]]:
        """The signed-in user making this request, as {'id', 'name'}."""
        user = getattr(g, 'user', None)
        if user is None:
            return None
        return {'id': user.id, 'name': user.name or user.email}

    def _public_job_info(self) -> Optional[Dict[str, Any]]:
        info = self._job_info if self.is_processing else None
        if not info:
            return None
        return {'kind': info['kind'], 'label': info['label'], 'started_at': info['started_at'],
                'started_by': info.get('owner_name')}

    def _start_job(self, kind: str, label: str, target: Callable, args: tuple,
                   cleanup: Optional[list] = None, owner: Optional[Dict[str, Any]] = None) -> bool:
        """
        Run `target(*args)` in a background thread as the single active job.

        Returns False, and starts nothing, if a job is already running. `owner`
        ({'id', 'name'}) is who started it: their history receives its run records.
        """
        with self._job_state_lock:
            if self.is_processing:
                return False
            self.is_processing = True
            self._job_seq += 1
            job = self._job_seq
            self._job_info = {
                'kind': kind, 'label': label, 'started_at': datetime.now().isoformat(timespec='seconds'),
                'owner_id': (owner or {}).get('id'), 'owner_name': (owner or {}).get('name'),
            }

        def runner():
            self._job_ctx.owner_id = (owner or {}).get('id')
            self._job_ctx.kind = kind
            self.socketio.emit('processing_started', {
                'source': label, 'type': kind, 'job': job,
                'started_by': (owner or {}).get('name')})
            try:
                target(*args)
            except Exception as e:
                if job == self._job_seq:
                    self.socketio.emit('processing_error', {'error': str(e), 'job': job})
            finally:
                for d in cleanup or []:
                    shutil.rmtree(d, ignore_errors=True)
                with self._job_state_lock:
                    is_latest = job == self._job_seq
                    if is_latest:
                        self.is_processing = False
                        self._worker_thread = None
                if is_latest:
                    self.socketio.emit('processing_completed', {'job': job})

        thread = threading.Thread(target=runner, daemon=True)
        with self._job_state_lock:
            self._worker_thread = thread
        thread.start()
        return True

    def _persist_run(self, summary: Dict[str, Any], kind: str) -> None:
        """Hand a finished run to the API layer, attributed to whoever started this job."""
        if not self.on_run_saved:
            return
        try:
            self.on_run_saved(summary, kind, getattr(self._job_ctx, 'owner_id', None))
        except Exception as e:  # history is a convenience; never break the count over it
            print(f"Warning: could not record run {summary.get('run_id')} in history ({e}).")

    def notify_run_saved(self, summary: Dict[str, Any]) -> None:
        """Record the run in its owner's history and tell dashboards it is ready."""
        run_id = summary.get('run_id', '')
        kind = summary.get('kind') or JOB_KIND_TO_RUN_KIND.get(getattr(self._job_ctx, 'kind', None), 'video')
        self._persist_run(summary, kind)
        base = f"/api/runs/{run_id}/"
        payload = {
            'run_id': run_id,
            'kind': kind,
            'status': summary.get('status'),
            'counts': summary.get('counts', {}),
            'corrected_total': summary.get('corrected_total'),
            'correction_factor': summary.get('correction_factor'),
            'warning': summary.get('warning', ''),
            'links': {
                'report': base + 'report.html',
                'events_csv': base + 'events.csv?download=1',
                'summary_json': base + 'summary.json?download=1',
            },
        }
        try:
            self.socketio.emit('run_saved', payload)
        except Exception:
            pass

    def _new_run_dir(self, label: str) -> tuple:
        stem = re.sub(r'[^A-Za-z0-9_-]+', '-', label)[:40].strip('-') or 'run'
        run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{stem}-{uuid.uuid4().hex[:4]}"
        out_dir = self.runs_dir / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        return run_id, out_dir

    def record_image_run(self, source: str, counts: Dict[str, Any], detections: int,
                         annotated_image: Optional[np.ndarray], started_at: datetime) -> None:
        """Keep a single-image count in history: summary.json plus the annotated image."""
        try:
            run_id, out_dir = self._new_run_dir(f"image-{Path(str(source)).stem}")
            files = {'summary_json': 'summary.json'}
            if annotated_image is not None:
                cv2.imwrite(str(out_dir / 'annotated.jpg'), annotated_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                files['annotated'] = 'annotated.jpg'
            summary = {
                'run_id': run_id, 'kind': 'image', 'source': Path(str(source)).name or str(source),
                'status': 'completed', 'started_at': started_at.isoformat(timespec='seconds'),
                'ended_at': datetime.now().isoformat(timespec='seconds'),
                'processing_seconds': round((datetime.now() - started_at).total_seconds(), 2),
                'frames_processed': 1,
                'counts': {k: int(counts.get(k, 0) or 0)
                           for k in ('total', 'fingerling', 'post_fingerling', 'juvenile', 'unknown')},
                'detections': int(detections), 'files': files,
            }
            (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"Warning: could not save image run record ({e}).")
            return
        self._persist_run(summary, 'image')
        try:
            self.socketio.emit('run_saved', {'run_id': run_id, 'kind': 'image', 'status': 'completed',
                                             'counts': summary['counts'], 'corrected_total': None,
                                             'warning': '', 'links': {}})
        except Exception:
            pass

    def _process_batch_files(self, files: list) -> None:
        """Process multiple image files in batch."""
        self.batch_results = []
        batch_totals = {
            'total': 0,
            'fingerling': 0,
            'post_fingerling': 0,
            'juvenile': 0,
            'unknown': 0
        }
        
        # The run folder is created up front so annotated images are written as they
        # are produced, instead of being held in memory for the whole batch.
        started_at = datetime.now()
        run_id, out_dir, images_dir = None, None, None
        try:
            run_id = f"{started_at.strftime('%Y%m%d_%H%M%S')}_batch-{uuid.uuid4().hex[:4]}"
            out_dir = self.runs_dir / run_id
            images_dir = out_dir / 'images'
            images_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Warning: could not create batch record folder ({e}).")
            out_dir = images_dir = None

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
                
                # Convert annotated image to base64 if available, and keep a copy on disk
                image_base64 = None
                image_rel = None
                try:
                    annotated_image = result_data.get('annotated_image')
                    if annotated_image is not None:
                        _, buffer = cv2.imencode('.jpg', annotated_image)
                        image_base64 = base64.b64encode(buffer).decode('utf-8')
                        if images_dir is not None:
                            stored = annotated_image
                            h, w = stored.shape[:2]
                            if w > 1280:
                                stored = cv2.resize(stored, (1280, int(h * 1280 / w)),
                                                    interpolation=cv2.INTER_AREA)
                            stem = secure_filename(Path(file_info['filename']).stem)[:40] or 'image'
                            image_rel = f"images/{idx + 1:03d}_{stem}.jpg"
                            cv2.imwrite(str(out_dir / image_rel), stored, [cv2.IMWRITE_JPEG_QUALITY, 82])
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
                
                raw_detections = result_data.get('detections', 0)
                detection_count = len(raw_detections) if isinstance(raw_detections, list) else int(raw_detections or 0)

                self.batch_results.append({
                    'filename': file_info['filename'],
                    'status': 'success',
                    'counts': counts_by_class,
                    'detections': detection_count,
                    'label_summary': ', '.join(label_summary_parts) if label_summary_parts else 'No detections',
                    'annotated_image': image_base64,
                    'image': image_rel
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

        # Save CSV summary for this batch as a downloadable run record
        if out_dir is None:
            return
        try:
            csv_path = out_dir / 'batch_summary.csv'
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
                self.socketio.emit('batch_csv_saved', {
                    'run_id': run_id,
                    'url': f'/api/runs/{run_id}/batch_summary.csv?download=1'
                })
            except Exception:
                pass
        except Exception as e:
            print(f"Failed to write batch CSV: {e}")
            return

        # summary.json makes the batch a first-class run in history (no base64 inside).
        ended_at = datetime.now()
        summary = {
            'run_id': run_id, 'kind': 'batch', 'source': f'{len(files)} image(s)',
            'status': 'completed', 'started_at': started_at.isoformat(timespec='seconds'),
            'ended_at': ended_at.isoformat(timespec='seconds'),
            'processing_seconds': round((ended_at - started_at).total_seconds(), 2),
            'frames_processed': len(files), 'total_files': len(files), 'counts': batch_totals,
            'results': [{k: v for k, v in r.items() if k != 'annotated_image'} for r in self.batch_results],
            'files': {'batch_summary_csv': 'batch_summary.csv', 'summary_json': 'summary.json'},
        }
        try:
            (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        except OSError as e:
            print(f"Warning: could not write batch summary.json ({e}).")
        self._persist_run(summary, 'batch')
        try:
            self.socketio.emit('run_saved', {'run_id': run_id, 'kind': 'batch', 'status': 'completed',
                                             'counts': batch_totals, 'corrected_total': None,
                                             'warning': '', 'links': {}})
        except Exception:
            pass
    
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
        # Local / hatchery-laptop mode only (Render runs gunicorn, which never
        # calls this). Werkzeug's threaded server is fine for a handful of
        # dashboards on a LAN; without the flag Flask-SocketIO refuses to start
        # when launched without a console, e.g. from a desktop shortcut.
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
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
            f.write(f"timestamp,frame,total,{class_columns},fps\n")
    
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


