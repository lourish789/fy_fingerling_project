"""Runtime benchmark: PyTorch vs ONNX, latency + detection parity, CPU."""
import time, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path('src').resolve()))
from ultralytics import YOLO
from models.onnx_detector import OnnxFingerlingDetector

imgs = sorted(Path('data/fish_fingerling_yolo/images/val').glob('*'))[:30]
frames = [cv2.imread(str(p)) for p in imgs]
cap = cv2.VideoCapture('VID_20260617_151857.mp4')
vframes = []
for _ in range(20):
    ok, f = cap.read()
    if ok: vframes.append(f)
cap.release()

pt = YOLO('models/best.pt')
onnx = OnnxFingerlingDetector('models/best.onnx', confidence_threshold=0.15, iou_threshold=0.45)

def bench(fn, data, warm=3):
    for f in data[:warm]: fn(f)
    ts=[]
    for f in data:
        t=time.perf_counter(); fn(f); ts.append((time.perf_counter()-t)*1000)
    a=np.array(ts)
    return a.mean(), a.std(), np.percentile(a,50), np.percentile(a,95)

pt_fn   = lambda f: pt.predict(f, conf=0.15, iou=0.45, imgsz=640, verbose=False, device='cpu')[0]
onnx_fn = lambda f: onnx.detect(f)

print('CPU:', 'Intel Core i5-6300U @2.40GHz (2C/4T)')
for tag, data in [('val images (var. size)', frames), ('1080p video frames', vframes)]:
    for name, fn in [('PyTorch/Ultralytics', pt_fn), ('ONNX Runtime', onnx_fn)]:
        m,s,p50,p95 = bench(fn, data)
        print(f'{tag:24} {name:20} mean {m:7.1f} ms  sd {s:6.1f}  p50 {p50:7.1f}  p95 {p95:7.1f}  -> {1000/m:5.2f} FPS')

# parity
print()
print('=== BACKEND PARITY on 30 val images (conf 0.15) ===')
np_, no_ = 0, 0
diffs=[]
for f in frames:
    a = pt_fn(f); b = onnx_fn(f)
    na = len(a.boxes); nb = len(b)
    np_ += na; no_ += nb; diffs.append(nb-na)
d = np.array(diffs)
print(f'PyTorch total detections: {np_}   ONNX total detections: {no_}')
print(f'per-image difference: mean {d.mean():+.2f}, max |diff| {np.abs(d).max()}, images differing: {(d!=0).sum()}/{len(d)}')
