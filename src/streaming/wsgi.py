"""
WSGI entry point for production deployment on Render.

Gunicorn targets this module:
    gunicorn --worker-class eventlet -w 1 "src.streaming.wsgi:app"

On startup, this module:
1. Initialises the FingerlingCounter in web-server mode (uploads only —
   no local camera or display in a cloud environment).
2. Monkey-patches stdlib with eventlet so Socket.IO works with async I/O.
3. Exposes `app` (the Flask application) and `socketio` for gunicorn.
"""

import os
import sys
from pathlib import Path

# ── Make src/ importable ────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'src'))

# ── Eventlet monkey-patch must come before any other network imports ─────────
import eventlet
eventlet.monkey_patch()

# ── Application ──────────────────────────────────────────────────────────────
from app.counter import FingerlingCounter

_model_path  = os.environ.get('MODEL_PATH', 'models/best.onnx')
_conf_thresh = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.25'))
_port        = int(os.environ.get('PORT', '5000'))

_counter = FingerlingCounter(
    weights_path=str(_ROOT / _model_path) if not os.path.isabs(_model_path) else _model_path,
    streaming_port=_port,
    use_streaming=True,
    use_display=False,           # headless — no OpenCV window
    web_server_mode=True,        # uploads + URL only
)

# Expose Flask app + SocketIO instance for gunicorn
app      = _counter.streaming_server.app
socketio = _counter.streaming_server.socketio
