# AquaCount — Catfish Fingerling Intelligence System

> Real-time AI-powered detection, tracking, and classification of catfish
> fingerlings by developmental stage — Fingerling · Post-Fingerling · Juvenile.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Repository Structure](#2-repository-structure)
3. [Local Setup](#3-local-setup)
4. [Model Conversion (PyTorch → ONNX)](#4-model-conversion-pytorch--onnx)
5. [Deploying the Backend (Render)](#5-deploying-the-backend-render)
6. [Deploying the Frontend (Vercel)](#6-deploying-the-frontend-vercel)
7. [Environment Variables](#7-environment-variables)
8. [API Reference](#8-api-reference)
9. [Free-Tier Optimisation Notes](#9-free-tier-optimisation-notes)
10. [Git Setup for dev Branch](#10-git-setup-for-dev-branch)

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         BROWSER / CLIENT                             │
│   frontend/index.html  (served by Vercel CDN — free tier)           │
│   ┌──────────────────┐   ┌────────────────────────────────────────┐  │
│   │  Video Feed      │   │  Stats Dashboard  (Chart.js counters)  │  │
│   │  + Digital Zoom  │   │  Batch Results   Live Indicator        │  │
│   └────────┬─────────┘   └────────────────────────────────────────┘  │
│            │  MJPEG stream               ↑ Socket.IO (WS/polling)   │
└────────────┼──────────────────────────────────────────────────────────┘
             │                             │
             ▼                             │
┌──────────────────────────────────────────────────────────────────────┐
│                    BACKEND  (Render Free Tier)                       │
│   Gunicorn + Eventlet  →  Flask + Flask-SocketIO                    │
│                                                                      │
│  ┌────────────────┐   ┌─────────────────┐   ┌──────────────────┐    │
│  │  REST API      │   │  VideoProcessor │   │  FingerlingTrack │    │
│  │  /api/upload   │──▶│  (cv2, ffmpeg)  │──▶│  (SORT + Hungar.)│    │
│  │  /api/batch    │   └────────┬────────┘   └────────┬─────────┘    │
│  │  /api/url      │            │                     │              │
│  └────────────────┘            ▼                     ▼              │
│                     ┌────────────────────┐  ┌────────────────────┐  │
│                     │  OnnxDetector      │  │  StreamingServer   │  │
│                     │  onnxruntime (CPU) │  │  /video_feed MJPEG │  │
│                     │  best.onnx  ~6 MB  │  │  socket.emit update│  │
│                     └────────────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
             │
             ▼
     models/best.onnx   ←  converted locally from models/best.pt
```

**Key design decisions:**

| Choice | Reason |
|---|---|
| ONNX Runtime instead of PyTorch | PyTorch ≈ 1.8 GB; ONNX Runtime ≈ 150 MB — fits Render's 512 MB RAM |
| Eventlet worker in Gunicorn | Flask-SocketIO requires async worker for concurrent WebSocket + HTTP |
| Vercel for static frontend | Single HTML file — zero build step, instant global CDN delivery |
| Socket.IO polling transport | Works through Render's reverse proxy without WebSocket upgrade issues |
| Thin bounding boxes (1 px) | Discrete overlays that don't obscure the fish being examined |
| Stats overlay = counts only | Frame number, FPS, and telemetry removed from video; shown in dashboard |

---

## 2. Repository Structure

```
fingerling_counting_model/
├── frontend/
│   └── index.html              ← Modernised engineering dashboard (Vercel)
├── src/
│   ├── app/
│   │   └── counter.py          ← FingerlingCounter — main application class
│   ├── models/
│   │   ├── detector.py         ← PyTorch/Ultralytics detector (local dev)
│   │   ├── onnx_detector.py    ← ONNX detector (production)
│   │   ├── tracker.py          ← SORT tracker (Hungarian algorithm)
│   │   └── size_classifier.py
│   ├── streaming/
│   │   ├── server.py           ← Flask + SocketIO streaming server
│   │   └── wsgi.py             ← Gunicorn WSGI entry point (Render)
│   └── video/
│       ├── processor.py        ← Video / image I/O + URL / YouTube support
│       └── visualization.py    ← Clean annotation overlay (thin boxes, counts only)
├── scripts/
│   └── convert_to_onnx.py      ← Local PyTorch → ONNX conversion utility
├── models/
│   ├── best.pt                 ← (not committed — too large for git)
│   └── best.onnx               ← Committed production artefact (~6–15 MB)
├── config/
│   └── config.yaml
├── main.py                     ← CLI entry point
├── requirements.txt            ← Full development dependencies
├── requirements-prod.txt       ← Minimal production dependencies (no PyTorch)
├── Procfile                    ← Render start command
├── render.yaml                 ← Render service definition
├── vercel.json                 ← Vercel routing config
└── .gitignore                  ← Excludes .venv, data, runs, videos, notebooks
```

---

## 3. Local Setup

### Prerequisites
- Python 3.10 or 3.11
- Git

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/lourish789/fy_fingerling_project.git
cd fy_fingerling_project

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install full development dependencies
pip install -r requirements.txt

# 4. Place your trained model weights
cp /path/to/your/best.pt models/best.pt

# 5. (Optional) Convert to ONNX for local testing of the production path
python scripts/convert_to_onnx.py --weights models/best.pt

# 6. Run the web server locally
python main.py --web-server --port 5000

# 7. Serve the frontend
python -m http.server 8080 --directory frontend
# Then open:  http://localhost:8080
# The frontend auto-detects localhost and connects to http://localhost:5000
```

### CLI Quick Reference

```
python main.py --source 0              # live webcam
python main.py --source video.mp4      # video file
python main.py --image photo.jpg       # single image
python main.py --image-dir ./images    # batch directory
python main.py --web-server            # upload/URL dashboard
python main.py --weights models/best.onnx  # use ONNX model
python main.py --no-display            # headless (server) mode
python main.py --port 5000             # custom port
```

---

## 4. Model Conversion (PyTorch → ONNX)

Run this **once, locally**, before your first deployment.
Requires PyTorch + Ultralytics (already in `requirements.txt`).

```bash
# Install optional simplification tool
pip install onnxsim

# Convert (default: models/best.pt → models/best.onnx at imgsz=640)
python scripts/convert_to_onnx.py

# With explicit options
python scripts/convert_to_onnx.py \
  --weights models/best.pt \
  --output  models/best.onnx \
  --imgsz   640 \
  --opset   12
```

The script:
1. Loads `best.pt` with Ultralytics YOLO
2. Exports to ONNX with static input shape
3. Optionally runs `onnxsim` to reduce graph complexity
4. Prints the final file size (typically 5–15 MB for YOLOv8n/v9n)

**Commit `models/best.onnx`** so Render can access it at container startup.

---

## 5. Deploying the Backend (Render)

### Option A — render.yaml (recommended)

`render.yaml` at the repository root auto-configures the service.

1. Push your `dev` branch to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com):
   - **New** → **Web Service** → Connect GitHub repo → select **`dev`** branch.
   - Render detects `render.yaml` and pre-fills all settings.
3. Click **Create Web Service**.

### Option B — Manual configuration

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements-prod.txt` |
| Start Command | `gunicorn --worker-class eventlet --workers 1 --bind 0.0.0.0:$PORT --timeout 120 "src.streaming.wsgi:app"` |
| Health Check Path | `/api/status` |
| Plan | Free |

### Environment Variables (set in Render dashboard)

| Variable | Value |
|---|---|
| `MODEL_PATH` | `models/best.onnx` |
| `CONFIDENCE_THRESHOLD` | `0.25` |

*(Render sets `PORT` automatically — do not add it manually.)*

### Cold-Start Mitigation

Render free tier shuts down idle services after ~15 min.
Use [UptimeRobot](https://uptimerobot.com) (free) to ping
`https://<service>.onrender.com/api/status` every 14 minutes.

---

## 6. Deploying the Frontend (Vercel)

The frontend is a single static file — no build required.

### Steps

1. [Create a Vercel account](https://vercel.com) and connect your GitHub repo.
2. **New Project** → import the repository.
3. Set these in **Project Settings → General**:

   | Setting | Value |
   |---|---|
   | Framework Preset | Other |
   | Root Directory | *(leave blank)* |
   | Output Directory | `frontend` |
   | Build Command | *(leave blank)* |
   | Install Command | *(leave blank)* |

4. Set deployment branch to **`dev`** in **Project Settings → Git**.
5. Click **Deploy**.

### Point the Frontend at Your Backend

After both services are live, open the frontend with the `?backend=` parameter:

```
https://your-vercel-app.vercel.app/?backend=https://aquacount-backend.onrender.com
```

Or permanently hard-code your Render URL in `frontend/index.html`
(search for `your-render-backend.onrender.com` and replace it).

---

## 7. Environment Variables

| Variable | Service | Purpose |
|---|---|---|
| `MODEL_PATH` | Render | Path to ONNX file relative to repo root |
| `CONFIDENCE_THRESHOLD` | Render | Detection threshold (0.0–1.0) |
| `PORT` | Render | Auto-set by Render |

---

## 8. API Reference

Base URL: `https://<render-service>.onrender.com`

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Health check; returns tracking state |
| `GET` | `/api/counts` | Current total counts by class |
| `GET` | `/video_feed` | MJPEG video stream |
| `POST` | `/api/upload` | Single video or image upload (`multipart/form-data`, field `file`) |
| `POST` | `/api/upload_batch` | Multiple images (`multipart/form-data`, field `files[]`) |
| `POST` | `/api/process_url` | Process from URL `{"url": "https://..."}` |
| `POST` | `/api/start_camera` | Start webcam `{"camera_index": 0}` |
| `POST` | `/api/stop` | Stop active processing |
| `POST` | `/api/reset_counts` | Reset all counts to zero |

### Socket.IO Events (Server → Client)

| Event | Payload |
|---|---|
| `update` | `{counts, active_tracks, fps, frame_number, source_type, is_live}` |
| `processing_started` | `{source, type}` |
| `processing_completed` | `{}` |
| `processing_error` | `{error}` |
| `counts_reset` | `{}` |
| `batch_results` | `{results[], batch_totals, total_files}` |
| `batch_csv_saved` | `{csv_path}` |

---

## 9. Free-Tier Optimisation Notes

### Render (backend)

| Concern | Mitigation |
|---|---|
| RAM limit 512 MB | ONNX Runtime replaces PyTorch (saves ~1.5 GB) |
| Shared CPU | Single Gunicorn worker; no GPU code paths |
| 30-second idle timeout | `--timeout 120` in Gunicorn; Socket.IO uses long polling |
| Cold starts | UptimeRobot ping every 14 min keeps service warm |
| Large file uploads | Flask `MAX_CONTENT_LENGTH` capped at 500 MB |
| MJPEG bandwidth | JPEG quality set to 80 in `_generate_frames()` |

### Vercel (frontend)

| Concern | Mitigation |
|---|---|
| Build cost | Zero — single static HTML, no npm, no bundler |
| CDN latency | Vercel edge delivers the file from the nearest PoP |
| JS dependency size | Chart.js and Socket.io loaded from CDN (cached by browser) |

---

## 10. Git Setup for dev Branch

```bash
# One-time identity config
git config user.name  "lourish789"
git config user.email "flourisholaiya@gmail.com"

# Add remote (if not set)
git remote add origin https://github.com/lourish789/fy_fingerling_project.git

# Create and switch to dev branch
git checkout -b dev

# Stage all production-ready files
git add \
  frontend/index.html \
  src/ \
  scripts/ \
  models/best.onnx \
  config/ \
  main.py \
  requirements.txt \
  requirements-prod.txt \
  Procfile \
  render.yaml \
  vercel.json \
  .gitignore \
  README.md

# Commit
git commit -m "feat: production refactor — ONNX backend, modernised dashboard, digital zoom"

# Push and set dev as the upstream tracking branch
git push -u origin dev
```

Set **`dev`** as the deployment branch in both Vercel and Render dashboards.

---

*AquaCount v1.0 — Aquaculture Intelligence for Sustainable Fish Farming*
*Developed by Engr. Flourish Olaiya*
