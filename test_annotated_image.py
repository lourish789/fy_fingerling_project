#!/usr/bin/env python3
"""Direct test of counter to verify annotated image generation."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from app.counter import FingerlingCounter

# Initialize counter
print("Initializing counter...")
counter = FingerlingCounter(use_streaming=False)

# Test image path
test_image = Path("data/fish_fingerling_yolo/images/train/IMG_20260228_130356_jpg.rf.d4beaf6f0568f0918d6eecf1ee781cf2.jpg")

if not test_image.exists():
    print(f"ERROR: Test image not found: {test_image}")
    sys.exit(1)

# Process with annotations
print(f"\nProcessing {test_image.name} with annotations...")
result = counter.process_image_file(str(test_image), no_annotations=False)

# Check results
print(f"\nResult keys: {list(result.keys())}")
print(f"Counts: {result.get('counts', {})}")
print(f"Detections: {result.get('detections', 0)}")

if 'annotated_image' in result:
    ann_img = result['annotated_image']
    if ann_img is not None:
        import numpy as np
        if isinstance(ann_img, np.ndarray):
            print(f"✓ Annotated image generated: shape={ann_img.shape}, dtype={ann_img.dtype}")
        else:
            print(f"✗ Annotated image is wrong type: {type(ann_img)}")
    else:
        print("✗ Annotated image is None")
else:
    print("✗ No annotated_image in result")

# Process without annotations
print(f"\nProcessing {test_image.name} without annotations...")
result2 = counter.process_image_file(str(test_image), no_annotations=True)
print(f"Counts: {result2.get('counts', {})}")

print("\n✓ Test completed successfully!")
