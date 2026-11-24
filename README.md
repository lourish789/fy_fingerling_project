# AquaCount — Catfish Fingerling Intelligence System

> Real-time AI-powered detection, tracking, and classification of catfish
> fingerlings by developmental stage — Fingerling · Post-Fingerling · Juvenile.

> **Using it in a hatchery?** Run it on a laptop at the hatchery, offline, with a
> fixed camera over the transfer channel: double-click `run_hatchery.bat`.
> Setup, daily use, **calibration** and retraining are in
> [docs/HATCHERY_DEPLOYMENT.md](docs/HATCHERY_DEPLOYMENT.md). The hosted Render free
> tier below is a demo only: it is too slow to process real batch videos.

> **Web app & accounts (v2).** The dashboard is now a mobile-first installable web
> app (`web/`) with sign-in (email/password or Google), per-user count history,
> insights and an admin view. Every API route except `/api/health` needs a signed-in
> user. Architecture, setup, Google sign-in and deployment:
> [docs/WEB_APP.md](docs/WEB_APP.md).

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
│   web/  React PWA (Vercel CDN, or served by the backend offline)    │
│   ┌──────────────────┐   ┌────────────────────────────────────────┐  │
│   │  Live count      │   │  Home · History · Insights · Profile   │  │
│   │  (annotated feed)│   │  Settings · Admin   (signed-in users)  │  │
│   └────────┬─────────┘   └────────────────────────────────────────┘  │
│            │  REST + Bearer token        ↑ Socket.IO (polling)      │
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
| ONNX Runtime instead of PyTorch | PyTorch ≈ 1.8 GB; ONNX Runtime ≈ 150 MB — fits Render's 512 MB RAM and lightweight hatchery laptops |
| `gthread` worker in Gunicorn | Built-in threaded worker pairs cleanly with Flask-SocketIO `async_mode='threading'` (no `eventlet` needed) |
| Web app built into `web/dist` | The backend serves the built PWA (fonts and libraries bundled, service worker cache), so the hatchery app works 100% offline |
| Accounts in `src/api` | Short-lived access tokens + rotating refresh cookie; SQLite offline, Postgres hosted |
| Socket.IO polling transport | Works through Render's reverse proxy without WebSocket upgrade issues |
| Thin bounding boxes (1 px) | Discrete overlays that don't obscure the fish being examined |
| Stats overlay = counts only | Frame number, FPS, and telemetry removed from video; shown in dashboard |

---

## 2. Repository Structure

```
fingerling_counting_model/
├── web/                        ← Mobile-first PWA (React + TypeScript + Vite)
│   ├── src/pages/              ← Login, sign-up, onboarding, home, count, history,
│   │                              run detail, insights, profile, settings, admin
│   └── src/components/         ← Design system, layout shell, nav bars, auth guards
├── src/
│   ├── api/                    ← Accounts, sessions, run history, insights, admin
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

# 7. Web app, with hot reload (proxies /api and /socket.io to port 5000)
cd web && npm ci && npm run dev
# Then open:  http://localhost:5173   (create the first account: it becomes admin)
# Or build once and let the backend serve it:  npm run build  -> http://localhost:5000
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
| Start Command | `gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT --timeout 120 "src.streaming.wsgi:app"` |
| Health Check Path | `/api/health` |
| Plan | Free |

### Environment Variables (set in Render dashboard)

| Variable | Value |
|---|---|
| `MODEL_PATH` | `models/best.onnx` |

*(Render sets `PORT` automatically — do not add it manually.)*

Detection and counting thresholds come **only** from `config/config.yaml`
(validated setting: confidence 0.50, line crossing, downstream only). If an old
`CONFIDENCE_THRESHOLD` variable is still set in the Render dashboard, delete it;
the backend ignores it.

### Cold-Start Mitigation

Render free tier shuts down idle services after ~15 min.
Use [UptimeRobot](https://uptimerobot.com) (free) to ping
`https://<service>.onrender.com/api/health` every 14 minutes (the only public route).

---

## 6. Deploying the Frontend (Vercel)

`vercel.json` builds `web/` and serves `web/dist`. It also forwards `/api/auth/*`
to the Render backend, so the sign-in cookie is first-party (Safari blocks the
third-party kind).

1. [Create a Vercel account](https://vercel.com) and import the repository.
2. **Project Settings → General**: Framework Preset *Other*, Root Directory blank.
   Build, install and output settings come from `vercel.json`.
3. **Project Settings → Environment Variables**: `VITE_API_URL` =
   `https://aquacount-backend.onrender.com` (the build fails without it).
4. If your Render service has another name, replace `aquacount-backend.onrender.com`
   in `vercel.json` (the `/api/auth` rewrite and the Content-Security-Policy).
5. Set the deployment branch to **`dev`** and **Deploy**.
6. On Render, set `APP_URL` and `CORS_ORIGINS` to the Vercel address.

Google sign-in, Postgres and email setup: [docs/WEB_APP.md](docs/WEB_APP.md).

---

## 7. Environment Variables

| Variable | Service | Purpose |
|---|---|---|
| `MODEL_PATH` | Render | Path to ONNX file relative to repo root |
| `PORT` | Render | Auto-set by Render |
| `JWT_SECRET` | Render | Signs session tokens (Render generates it) |
| `DATABASE_URL` | Render | Postgres for accounts and history (Render's disk is wiped on restart) |
| `GOOGLE_CLIENT_ID` | Render | Enables "Continue with Google" |
| `APP_URL`, `CORS_ORIGINS` | Render | The web app's public address |
| `TRUST_PROXY` | Render | `1` behind Render's proxy |
| `VITE_API_URL` | Vercel | Backend address the web app calls |

Every backend variable is described in [`.env.example`](.env.example). On the
hatchery laptop none are required; put any you want in a `.env` file at the repo root.

---

## 8. API Reference

Base URL: `https://<render-service>.onrender.com`

Every route below except `/api/health` needs `Authorization: Bearer <access token>`
(from `/api/auth/login`, `/signup`, `/google` or `/refresh`). Accounts, history,
insights and admin endpoints are listed in [docs/WEB_APP.md](docs/WEB_APP.md#api).

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Public health check (no sign-in) |
| `GET` | `/api/status` | Tracking state, plus who started the running job |
| `GET` | `/api/counts` | Current total counts by class |
| `GET` | `/video_feed` | MJPEG video stream |
| `POST` | `/api/upload` | Single video or image upload (`multipart/form-data`, field `file`) |
| `POST` | `/api/upload_batch` | Multiple images (`multipart/form-data`, field `files[]`) |
| `POST` | `/api/process_url` | Process from URL `{"url": "https://..."}` |
| `POST` | `/api/start_camera` | Start webcam `{"camera_index": 0}` |
| `POST` | `/api/stop` | Stop active processing |
| `POST` | `/api/reset_counts` | Reset all counts to zero (closes the current run record and starts a new one) |
| `GET` | `/api/runs` | Your runs, newest first (admins: `?scope=all`); filters `status`, `kind`, `q` |
| `GET` | `/api/runs/<run_id>` | One run: summary, files, spot-check crops, and a short-lived `media_token` |
| `GET` | `/api/runs/<run_id>/<file>` | `report.html`, `events.csv`, `summary.json`, `crops/…` (bearer or `?t=<media_token>`); add `?download=1` to download |
| `GET` | `/` | The web app (`web/dist`; works offline once built) |

Only one job runs at a time. Starting a job while one is running returns
**HTTP 409**: stop the running count first. A running count is never silently replaced.

### Socket.IO Events (Server → Client)

Connect with `auth: {token: <access token>}`; connections without a valid token are refused.

| Event | Payload |
|---|---|
| `update` | `{counts, active_tracks, fps, frame_number, source_type, is_live}` |
| `processing_started` | `{source, type, job, started_by}` |
| `processing_completed` | `{job}` |
| `processing_error` | `{error, job}` |
| `counts_reset` | `{}` |
| `run_saved` | `{run_id, kind, status, counts, corrected_total, warning, links}` |
| `batch_results` | `{results[], batch_totals, total_files}` |
| `batch_csv_saved` | `{run_id, url}` |

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
| Bundle size | About 100 KB of gzipped JS on first load; less-used pages load on demand |
| CDN latency | Hashed assets are cached for a year at the edge; the app shell revalidates |
| Offline | A service worker precaches the app shell, so it opens with no connection |

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
  web/ \
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
