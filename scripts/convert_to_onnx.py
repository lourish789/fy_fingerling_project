#!/usr/bin/env python3
"""
Convert a trained YOLOv8/v9/v10 .pt model to ONNX for CPU-optimised
production inference on Render's free tier.

Run this LOCALLY (requires PyTorch + Ultralytics) before deploying:

    python scripts/convert_to_onnx.py --weights models/best.pt

The output file (models/best.onnx) is the only artefact that needs to be
present on the production server — no PyTorch required at runtime.

Dependencies (local dev only):
    pip install ultralytics onnx onnxsim
"""

import argparse
import sys
from pathlib import Path


def convert(weights: str, output: str, imgsz: int, opset: int, simplify: bool):
    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit(
            "ultralytics is not installed.\n"
            "Run: pip install ultralytics"
        )

    weights_path = Path(weights)
    if not weights_path.exists():
        sys.exit(f"Weights file not found: {weights_path}")

    print(f"Loading model: {weights_path}")
    model = YOLO(str(weights_path))

    print(f"Exporting to ONNX (opset={opset}, imgsz={imgsz}, simplify={simplify}) ...")
    export_path = model.export(
        format="onnx",
        imgsz=imgsz,
        opset=opset,
        simplify=simplify,
        dynamic=False,
    )

    if export_path:
        src = Path(export_path)
        dst = Path(output)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src != dst:
            src.rename(dst)
        print(f"\nSuccess! ONNX model saved to: {dst}")
        print(f"File size: {dst.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        sys.exit("Export failed — no output path returned by Ultralytics.")

    # Optional: run onnxsim to reduce model complexity
    if simplify:
        try:
            import onnx
            from onnxsim import simplify as onnx_simplify

            print("\nRunning onnxsim for extra simplification ...")
            model_onnx = onnx.load(str(dst))
            model_simplified, ok = onnx_simplify(model_onnx)
            if ok:
                onnx.save(model_simplified, str(dst))
                print(f"onnxsim: model simplified successfully ({dst.stat().st_size / 1024 / 1024:.1f} MB)")
            else:
                print("onnxsim: simplification check failed — keeping original export.")
        except ImportError:
            print("onnxsim not installed — skipping extra simplification.")
            print("To install: pip install onnxsim")


def main():
    parser = argparse.ArgumentParser(
        description="Convert YOLO .pt weights to ONNX for production deployment."
    )
    parser.add_argument(
        "--weights",
        default="models/best.pt",
        help="Path to input .pt model (default: models/best.pt)"
    )
    parser.add_argument(
        "--output",
        default="models/best.onnx",
        help="Path for output .onnx model (default: models/best.onnx)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size in pixels (default: 640)"
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=12,
        help="ONNX opset version (default: 12, works with onnxruntime ≥1.10)"
    )
    parser.add_argument(
        "--no-simplify",
        action="store_true",
        help="Disable ONNX graph simplification"
    )
    args = parser.parse_args()

    convert(
        weights=args.weights,
        output=args.output,
        imgsz=args.imgsz,
        opset=args.opset,
        simplify=not args.no_simplify,
    )


if __name__ == "__main__":
    main()
