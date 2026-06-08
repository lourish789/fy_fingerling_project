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
- Loads model engine and runs detection.
- Modules: `src/models/detector.py`
- Engine strategy:
  - `ultralytics` + checkpoint weights
  - YOLOv26 checkpoints are supported by configuration when available.

3. Tracking and Counting Layer
- Associates detections across frames.
- Counts on line-crossing logic.
- Module: `src/models/tracker.py`

4. Annotation and Visualization Layer
- Draws boxes, IDs, class labels, and summary overlays.
- Module: `src/video/visualization.py`

5. Serving Layer (Backend)
- REST endpoints for upload, URL processing, camera start/stop.
- WebSocket stream for live counters + status.
- MJPEG video feed endpoint.
- Module: `src/streaming/server.py`

6. Web UI Layer (Frontend)
- Single-page dashboard embedded in backend template.
- Live video, class counts, chart, controls for source selection.
- Module: `src/streaming/server.py` (embedded HTML/JS)

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
