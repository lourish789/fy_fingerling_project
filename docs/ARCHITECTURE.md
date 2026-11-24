# Fingerling Counting System Architecture

## 1) Objectives
- Detect catfish fingerlings from images, videos, URLs, and live camera.
- Count and sort detections into: fingerling, post_fingerling, juvenile.
- Provide backend APIs and a simple frontend dashboard for testing.
- Keep model runtime pluggable so YOLO families can be swapped (YOLOv8 now, YOLOv26-ready path).

## 2) High-Level Layers

1. Ingestion Layer
- Inputs: camera index, local media, stream URL, uploaded files.
- Module: `src/video/processor.py`

2. Inference Layer
- Loads model engine and runs detection (with optional channel ROI cropping via `video.roi`).
- Modules: `src/models/detector.py` (PyTorch/Ultralytics dev runtime) and `src/models/onnx_detector.py` (CPU-only ONNX Runtime production engine).
- Engine strategy:
  - `onnxruntime` for production/hatchery laptops (`models/best.onnx`)
  - `ultralytics` + checkpoint weights for training/local dev (YOLOv26-ready fallback)

3. Tracking and Counting Layer
- Associates detections across frames via centroid-distance Hungarian assignment (`max_distance=160 px`) with 2-point constant-velocity prediction.
- Counts on direction-gated line-crossing logic (`y = 0.50`, downstream only) with `sides_seen` tracking and majority-vote class assignment.
- Module: `src/models/tracker.py`

4. Audit Trail & Calibration Layer
- Records per-fish counting events (`events.csv`), cropped thumbnails (`crops/`), machine-readable run metadata (`summary.json` with SHA-256 model fingerprint), and printable batch reports (`report.html`).
- Modules: `src/app/run_log.py`, `scripts/calibrate.py`

5. Annotation and Visualization Layer
- Draws thin boxes, track IDs, directional counting line arrows, optional channel ROI frame, and compact count overlays.
- Module: `src/video/visualization.py`

6. Serving Layer (Backend)
- REST endpoints for upload, batch upload, URL processing (with SSRF guard), camera start/stop and reset. Each job records who started it.
- Socket.IO stream for live frames, counters, status, and run notifications (signed-in clients only); MJPEG `/video_feed` endpoint for local/same-origin use.
- Modules: `src/streaming/server.py`, `src/streaming/wsgi.py`

6b. Accounts & History Layer (Backend)
- Email/password and Google sign-in, rotating refresh-token sessions, password reset, profile and preferences, per-user run history (`/api/runs`), insights, admin (users, station config). Every `/api` route is private unless marked public.
- SQLite (`instance/`) offline; Postgres via `DATABASE_URL` when hosted. Run files stay in `output/runs/`.
- Modules: `src/api/` (details in `docs/WEB_APP.md`)

7. Web UI Layer (Frontend)
- Mobile-first installable PWA (React + TypeScript + Vite): bottom tab bar on phones, sidebar on tablets/desktops, light/dark design system, offline app shell.
- Screens: sign-in/sign-up/password reset, onboarding, home, live count (feed, class counters, camera/upload/batch/stream sources), history, run detail (report, fish log, spot-check crops), insights, profile & security, settings, admin.
- Built into `web/dist`, served by the backend (hatchery, offline) or by Vercel (cloud). Source: `web/src/`.

7. Training Layer
- Dataset preparation from COCO zip to YOLO labels.
- Training, validation, and export CLI.
- Modules: `src/training/prepare_dataset.py`, `src/training/train.py`

8. Orchestration Layer
- CLI entrypoint and processing loop.
- Module: `src/app/counter.py`, `main.py`

## 3) End-to-End Runtime Data Flow
1. User selects source from CLI or dashboard.
2. Frames are decoded and normalized by video/image processors.
3. Detector returns bounding boxes with class names and confidence.
4. Tracker assigns stable IDs and updates crossing-based counts.
5. Visualizer draws overlays on the current frame.
6. Backend publishes:
- MJPEG frame stream (`/video_feed`)
- Socket updates (`update`, `processing_*`)
- JSON status/count APIs (`/api/status`, `/api/counts`)
7. Frontend updates counters and chart in real time.
8. Optional: CSV logger writes running totals to `output/counts.csv`.

## 4) Training Flow
1. Input dataset zip (COCO export).
2. Convert annotations to YOLO txt labels.
3. Generate dataset yaml with class mapping.
4. Train model with selected checkpoint (YOLOv26-first supported by config/CLI).
5. Validate, export, and place best weights in `models/`.

## 5) Proposed Production Layout

```
fingerling_counting_model/
  config/
    config.yaml
  data/
    raw/
    prepared/
  docs/
    ARCHITECTURE.md
  models/
    README.md
    fingerling_yolov26.pt   # preferred when available
    fingerling_yolov8.pt    # fallback
  output/
  logs/
  src/
    app/
    models/
    streaming/
    training/
    video/
```

## 6) Interfaces and Contracts
- Detection contract: list of dicts with bbox, confidence, class_name, center, area.
- Counting contract: dict with total + per-class counters + unknown.
- Stream payload contract: frame metadata + counts + active tracks + fps.
- Frontend contract: reads same class keys as backend (`fingerling`, `post_fingerling`, `juvenile`, `unknown`).

## 7) YOLOv26 Integration Strategy
- Keep inference API unchanged.
- Select engine and checkpoint from config/CLI.
- Attempt YOLOv26 checkpoint first when configured.
- Fall back to YOLOv8 checkpoint if YOLOv26 checkpoint is unavailable.
- No backend/frontend change required when switching checkpoint family.

## 8) Non-Functional Notes
- Windows-safe path handling for spaces/apostrophes.
- CPU fallback if CUDA is unavailable.
- Graceful stop/reset for long-running streams.
- Input file type filtering in upload API.
