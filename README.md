# Catfish Fingerling Counter 🐟

An AI-powered system for counting and sorting catfish fingerlings by class from video, live camera, images, or web URLs. The model uses YOLO for detection, custom tracking algorithms for counting, and provides real-time streaming output.

Architecture blueprint: `docs/ARCHITECTURE.md`

## Features

- **Multi-Source Input**: 
  - Live camera/webcam feed
  - Video files (MP4, AVI, etc.)
  - RTSP/IP camera streams
  - YouTube and web video URLs
  - Image files (JPG, PNG, etc.)
  - Image directories (batch processing)
- **Real-time Detection**: YOLOv8-based fingerling detection
- **Class-Based Sorting**: Automatic sorting into Fingerling, Post-Fingerling, and Juvenile classes
- **Object Tracking**: SORT-based tracking for accurate counting
- **Counting Line**: Virtual counting line for precise enumeration
- **Web Dashboard**: Interactive web interface with:
  - Live video streaming
  - File upload support
  - URL/YouTube video processing
  - Camera controls
  - Real-time count display
- **Console Output**: Live terminal updates
- **CSV Logging**: Export count data over time
- **Video Output**: Save annotated video with counts

## Class Categories

| Category | Description |
|----------|-------------|
| Fingerling | Early growth stage |
| Post-Fingerling | Intermediate stage |
| Juvenile | Advanced pre-adult stage |

## Installation

### Prerequisites

- Python 3.9 or higher
- CUDA-capable GPU (recommended for real-time processing)
- Webcam or video file for input

### Setup

1. **Clone/Download the project**

2. **Create virtual environment** (recommended):
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify installation**:
   ```bash
   python -c "import torch; print(f'PyTorch: {torch.__version__}')"
  python -c "from ultralytics import YOLO; print('Ultralytics YOLO: OK')"
   ```

## Architecture-First Workflow

Before environment setup, review architecture and interfaces first:

1. Read `docs/ARCHITECTURE.md`
2. Confirm class labels and counting contracts
3. Select model checkpoint strategy (`yolov26n.pt` preferred, fallback to `yolov8n.pt`)
4. Configure Python environment and install dependencies

## Quick Start

### Video/Camera Processing

```bash
# Use webcam (default)
python main.py

# Use specific camera
python main.py --source 1

# Use video file
python main.py --source path/to/video.mp4

# Use IP camera/RTSP stream
python main.py --source "rtsp://username:password@ip:port/stream"

# Use YouTube video
python main.py --source "https://www.youtube.com/watch?v=VIDEO_ID"

# Save output video
python main.py --source video.mp4 --output output.mp4

# Prefer YOLOv26 checkpoint when available (falls back to YOLOv8n)
python main.py --source video.mp4 --pretrained-model yolov26n.pt
```

### Image Processing

```bash
# Process single image
python main.py --image fingerlings.jpg

# Process image from URL
python main.py --image "https://example.com/image.jpg"

# Process all images in a directory
python main.py --image-dir ./images

# Save annotated result
python main.py --image fingerlings.jpg --output result.jpg
```

### Web Server Mode

Run as a web server for uploading files and processing URLs:

```bash
python main.py --web-server
```

Then open your browser to `http://localhost:5000`

The web interface allows you to:
- Start/stop live camera feed
- Upload video or image files
- Enter YouTube or video URLs for processing
- View real-time counts and statistics

### Web Dashboard

When running, open your browser to:
```
http://localhost:5000
```

The dashboard shows:
- Live video feed with annotations
- Real-time counts by class
- Class distribution chart
- Upload and URL input controls
- Camera start/stop buttons
- FPS and frame information

### Keyboard Controls

While the display window is active:
- `q` - Quit the application
- `r` - Reset counts
- `s` - Save screenshot

## Configuration

Edit `config/config.yaml` to customize:

```yaml
# Model settings
model:
  confidence_threshold: 0.5  # Detection confidence
  device: "auto"  # "auto", "cuda", "cpu"

# Model classes
classes:
  - fingerling
  - post_fingerling
  - juvenile

# Counting line position
counting:
  counting_line_position: 0.5  # Middle of frame
  counting_line_orientation: "horizontal"

# Streaming server
streaming:
  port: 5000
```

## Training Custom Model

For best results, train on your own fingerling dataset:

### 1. Prepare Dataset

```bash
# Extract frames from video
python -m src.training.data_prep extract \
    --video fingerlings.mp4 \
    --output data/raw_frames \
    --interval 30

# Split into train/val/test
python -m src.training.data_prep split \
    --dir data/labeled_images \
    --output data/dataset
```

### 2. Label Images

Use a labeling tool like [LabelImg](https://github.com/heartexlabs/labelImg) or [CVAT](https://cvat.ai/):

1. Open images from `data/raw_frames`
2. Draw bounding boxes around each fingerling
3. Save annotations in YOLO format
4. Save label files to `data/dataset/labels/train`

### 3. Create Dataset Configuration

Create `data/fingerlings.yaml`:
```yaml
path: ./data/dataset
train: images/train
val: images/val

names:
  0: fingerling
  1: post_fingerling
  2: juvenile
```

### 4. Train Model

```bash
python -m src.training.train \
    --data data/fingerlings.yaml \
  --model yolov26n.pt \
  --model-engine ultralytics \
    --epochs 100 \
    --batch 16 \
    --imgsz 640

# Or build YOLO labels directly from a Roboflow COCO zip, then train
python -m src.training.train \
  --prepare-zip fish-fingerling.v1i.coco.zip \
  --prepared-output data/fish_fingerling_yolo \
  --prepared-yaml data/fish_fingerling.yaml \
  --model yolov26n.pt \
  --model-engine ultralytics \
  --epochs 100 \
  --batch 16 \
  --imgsz 640
```

### 5. Use Trained Model

```bash
python main.py \
    --source video.mp4 \
    --weights runs/fingerling_detector/weights/best.pt
```

## Project Structure

```
fingerling_counting_model/
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
├── config/
│   └── config.yaml        # Configuration file
├── src/
│   ├── models/
│   │   ├── detector.py    # YOLOv8 detection model
│   │   ├── size_classifier.py  # Size classification
│   │   └── tracker.py     # Object tracking
│   ├── video/
│   │   ├── processor.py   # Video input handling
│   │   └── visualization.py  # Drawing utilities
│   ├── streaming/
│   │   └── server.py      # Web streaming server
│   ├── training/
│   │   ├── train.py       # Model training
│   │   └── data_prep.py   # Dataset preparation
│   └── app/
│       └── counter.py     # Main application
├── models/                 # Trained model weights
├── data/                   # Training data
├── output/                 # Output files
└── logs/                   # Log files
```

## API Usage

```python
from src.app.counter import FingerlingCounter

# Create counter
counter = FingerlingCounter(
    video_source="video.mp4",
    weights_path="models/best.pt",
    use_streaming=True,
    use_display=True
)

# Run counting
final_counts = counter.run()

print(f"Total: {final_counts['total']}")
print(f"Fingerling: {final_counts['fingerling']}")
print(f"Post-Fingerling: {final_counts['post_fingerling']}")
print(f"Juvenile: {final_counts['juvenile']}")
print(f"Unknown: {final_counts.get('unknown', 0)}")
```

## Calibration

For accurate size estimation, calibrate the system:

1. Place a ruler or known-size object in the camera view
2. Measure its pixel length in the video
3. Update `config.yaml`:
   ```yaml
   calibration:
     pixels_per_mm: 5.0  # Adjust based on measurement
   ```

## Performance Tips

1. **GPU Acceleration**: Ensure CUDA is properly installed for faster processing
2. **Resolution**: Lower resolution = faster processing
3. **Frame Skip**: Process every Nth frame for faster counting
4. **Batch Processing**: For offline video, use batch detection

## Troubleshooting

### "CUDA out of memory"
- Reduce batch size
- Use smaller model (yolov8n.pt instead of larger checkpoints)
- Reduce input resolution

### "No detections"
- Lower confidence threshold in config
- Ensure proper lighting
- Train custom model on your data

### "Counts are inaccurate"
- Adjust tracking parameters
- Calibrate counting line position
- Ensure fingerlings cross the counting line

## License

MIT License - See LICENSE file

## Acknowledgments

- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [OpenCV](https://opencv.org/)
- [Flask](https://flask.palletsprojects.com/)
