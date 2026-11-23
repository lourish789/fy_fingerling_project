#!/usr/bin/env python
"""
Extract candidate background (no-fish) frames from a video, for retraining.

The current model was trained on 332 images that all contain fish, so it has
never been shown "not a fish" and fires on empty turbulent water with high
confidence. Adding a few dozen verified empty frames of the rig, the water
surface and the surroundings, with EMPTY label files, is the fix.

    python scripts/extract_background_frames.py --video VID_20260617_151331.mp4

Output (YOLO layout, ready to copy into the training set after review):

    data/background_candidates/<video>/images/<video>_f000123.jpg
    data/background_candidates/<video>/labels/<video>_f000123.txt   (empty)
    data/background_candidates/<video>/candidates.csv               frame, detections, max confidence

With --hard-only, only frames where the current model fires are kept. These
"hard negatives" are the most useful ones to add.

IMPORTANT: a person must look at every image and delete any that shows a
fish, even a partial one. An empty label file on a frame with a fish teaches
the model to ignore fish.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "background_candidates")
    ap.add_argument("--every", type=int, default=15, help="keep one frame in N (default 15)")
    ap.add_argument("--max-side", type=int, default=1280, help="downscale so the long side is at most this")
    ap.add_argument("--model", type=Path, default=ROOT / "models" / "best.onnx")
    ap.add_argument("--conf", type=float, default=0.25, help="detection threshold used to flag hard negatives")
    ap.add_argument("--hard-only", action="store_true", help="keep only frames where the model fires")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many saved frames (0 = no limit)")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    from models.onnx_detector import OnnxFingerlingDetector
    detector = OnnxFingerlingDetector(str(args.model), confidence_threshold=args.conf)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        sys.exit(f"Cannot open {args.video}")
    stem = args.video.stem
    img_dir = args.out / stem / "images"
    lbl_dir = args.out / stem / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    saved, frame_no, rows = 0, 0, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_no += 1
        if frame_no % args.every:
            continue
        dets = detector.detect(frame)
        max_conf = max((d["confidence"] for d in dets), default=0.0)
        if args.hard_only and not dets:
            continue
        h, w = frame.shape[:2]
        scale = min(1.0, args.max_side / max(h, w))
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        name = f"{stem}_f{frame_no:06d}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (lbl_dir / f"{name}.txt").write_text("")
        rows.append((name, frame_no, len(dets), round(max_conf, 3)))
        saved += 1
        if args.limit and saved >= args.limit:
            break

    with open(args.out / stem / "candidates.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["image", "frame", "model_detections", "max_confidence"])
        wr.writerows(sorted(rows, key=lambda r: -r[3]))

    hard = sum(1 for r in rows if r[2] > 0)
    print(f"Saved {saved} frames to {args.out / stem} ({hard} where the current model fires).")
    print("Next: look at every image, delete any showing a fish (and its .txt), then follow")
    print("docs/HATCHERY_DEPLOYMENT.md, section 'Retraining with background images'.")


if __name__ == "__main__":
    main()
