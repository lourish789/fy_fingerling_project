"""
WSGI entry point for production deployment on Render.

Gunicorn targets this module:
    gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT "src.streaming.wsgi:app"

Flask-SocketIO is initialised with async_mode='threading' (set in server.py),
which works with gunicorn's built-in gthread worker — no eventlet or gevent needed.
"""

import os
import sys
from pathlib import Path

# ── Make src/ importable ────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / 'src'))

# ── Application ──────────────────────────────────────────────────────────────
from app.counter import FingerlingCounter

_model_path  = os.environ.get('MODEL_PATH', 'models/best.onnx')
_conf_thresh = float(os.environ.get('CONFIDENCE_THRESHOLD', '0.25'))
_port        = int(os.environ.get('PORT', '5000'))

_counter = FingerlingCounter(
    weights_path=str(_ROOT / _model_path) if not os.path.isabs(_model_path) else _model_path,
    streaming_port=_port,
    use_streaming=True,
    use_display=False,      # headless — no OpenCV window on Render
    web_server_mode=True,   # uploads + URL only
)

# Expose Flask app for gunicorn
app = _counter.streaming_server.app
