"""
Data Preparation Utilities for Fingerling Detection

Provides tools for:
- Image labeling assistance
- Data augmentation
- Dataset splitting
- Format conversion
"""

import os
import random
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import json

import cv2
import numpy as np


class DatasetPreparator:
    """
    Utility class for preparing fingerling detection datasets.
    """
    
    def __init__(self, data_dir: str):
        """
        Initialize dataset preparator.
        
        Args:
            data_dir: Root directory for dataset.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create directory structure
        self.images_dir = self.data_dir / 'images'
        self.labels_dir = self.data_dir / 'labels'
        
        for split in ['train', 'val', 'test']:
            (self.images_dir / split).mkdir(parents=True, exist_ok=True)
            (self.labels_dir / split).mkdir(parents=True, exist_ok=True)
    
    def extract_frames_from_video(
        self,
        video_path: str,
        output_dir: str,
        frame_interval: int = 30,
        max_frames: Optional[int] = None
    ) -> List[str]:
        """
        Extract frames from video for labeling.
        
        Args:
            video_path: Path to input video.
            output_dir: Directory for extracted frames.
            frame_interval: Extract every N frames.
            max_frames: Maximum number of frames to extract.
            
        Returns:
            List of extracted frame paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        frame_paths = []
        frame_count = 0
        extracted = 0
        
        video_name = Path(video_path).stem
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % frame_interval == 0:
                frame_path = output_dir / f"{video_name}_frame_{frame_count:06d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                frame_paths.append(str(frame_path))
                extracted += 1
                
                if max_frames and extracted >= max_frames:
                    break
            
            frame_count += 1
        
        cap.release()
        print(f"Extracted {extracted} frames to {output_dir}")
        
        return frame_paths
    
    def split_dataset(
        self,
        image_dir: str,
        train_ratio: float = 0.8,
        val_ratio: float = 0.15,
        test_ratio: float = 0.05,
        seed: int = 42
    ) -> Dict[str, List[str]]:
        """
        Split dataset into train/val/test sets.
        
        Args:
            image_dir: Directory containing images.
            train_ratio: Ratio for training set.
            val_ratio: Ratio for validation set.
            test_ratio: Ratio for test set.
            seed: Random seed for reproducibility.
            
        Returns:
            Dictionary mapping split names to file lists.
        """
        random.seed(seed)
        
        image_dir = Path(image_dir)
        images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png'))
        
        random.shuffle(images)
        
        n = len(images)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)
        
        splits = {
            'train': images[:train_end],
            'val': images[train_end:val_end],
            'test': images[val_end:]
        }
        
        # Copy files to appropriate directories
        for split_name, files in splits.items():
            for img_path in files:
                # Copy image
                dest_img = self.images_dir / split_name / img_path.name
                shutil.copy(img_path, dest_img)
                
                # Copy label if exists
                label_path = img_path.with_suffix('.txt')
                if label_path.exists():
                    dest_label = self.labels_dir / split_name / label_path.name
                    shutil.copy(label_path, dest_label)
        
        print(f"Dataset split: train={len(splits['train'])}, val={len(splits['val'])}, test={len(splits['test'])}")
        
        return {k: [str(f) for f in v] for k, v in splits.items()}
    
    def convert_labelme_to_yolo(
        self,
        json_dir: str,
        output_dir: str,
        class_map: Optional[Dict[str, int]] = None
    ) -> None:
        """
        Convert LabelMe JSON annotations to YOLO format.
        
        Args:
            json_dir: Directory containing LabelMe JSON files.
            output_dir: Output directory for YOLO labels.
            class_map: Mapping from class names to indices.
        """
        json_dir = Path(json_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if class_map is None:
            class_map = {
                'fingerling': 0,
                'post_fingerling': 1,
                'juvenile': 2
            }
        
        for json_path in json_dir.glob('*.json'):
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            img_width = data['imageWidth']
            img_height = data['imageHeight']
            
            yolo_labels = []
            
            for shape in data['shapes']:
                label = shape['label']
                if label not in class_map:
                    continue
                
                class_id = class_map[label]
                points = shape['points']
                
                if shape['shape_type'] == 'rectangle':
                    x1, y1 = points[0]
                    x2, y2 = points[1]
                elif shape['shape_type'] == 'polygon':
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    x1, y1 = min(xs), min(ys)
                    x2, y2 = max(xs), max(ys)
                else:
                    continue
                
                # Convert to YOLO format (center x, center y, width, height - normalized)
                x_center = ((x1 + x2) / 2) / img_width
                y_center = ((y1 + y2) / 2) / img_height
                width = (x2 - x1) / img_width
                height = (y2 - y1) / img_height
                
                yolo_labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
            
            # Write YOLO label file
            output_path = output_dir / json_path.with_suffix('.txt').name
            with open(output_path, 'w') as f:
                f.write('\n'.join(yolo_labels))
        
        print(f"Converted {len(list(json_dir.glob('*.json')))} annotations to YOLO format")
    
    def augment_image(
        self,
        image: np.ndarray,
        labels: List[List[float]],
        augmentation_type: str = 'random'
    ) -> Tuple[np.ndarray, List[List[float]]]:
        """
        Apply augmentation to image and labels.
        
        Args:
            image: Input image.
            labels: List of YOLO format labels [class, x, y, w, h].
            augmentation_type: Type of augmentation.
            
        Returns:
            Tuple of (augmented_image, augmented_labels).
        """
        aug_image = image.copy()
        aug_labels = [l.copy() for l in labels]
        
        if augmentation_type == 'random':
            augmentation_type = random.choice(['flip_h', 'flip_v', 'brightness', 'contrast', 'blur'])
        
        if augmentation_type == 'flip_h':
            aug_image = cv2.flip(aug_image, 1)
            for label in aug_labels:
                label[1] = 1.0 - label[1]  # Flip x coordinate
        
        elif augmentation_type == 'flip_v':
            aug_image = cv2.flip(aug_image, 0)
            for label in aug_labels:
                label[2] = 1.0 - label[2]  # Flip y coordinate
        
        elif augmentation_type == 'brightness':
            factor = random.uniform(0.7, 1.3)
            aug_image = np.clip(aug_image * factor, 0, 255).astype(np.uint8)
        
        elif augmentation_type == 'contrast':
            factor = random.uniform(0.7, 1.3)
            mean = np.mean(aug_image)
            aug_image = np.clip((aug_image - mean) * factor + mean, 0, 255).astype(np.uint8)
        
        elif augmentation_type == 'blur':
            kernel_size = random.choice([3, 5])
            aug_image = cv2.GaussianBlur(aug_image, (kernel_size, kernel_size), 0)
        
        return aug_image, aug_labels
    
    def create_sample_annotations(
        self,
        image_dir: str,
        output_dir: str
    ) -> None:
        """
        Create sample/template annotation files for images.
        
        Args:
            image_dir: Directory containing images.
            output_dir: Output directory for annotation files.
        """
        image_dir = Path(image_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for img_path in list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png')):
            label_path = output_dir / img_path.with_suffix('.txt').name
            
            if not label_path.exists():
                # Create empty label file
                label_path.touch()
        
        print(f"Created template annotation files in {output_dir}")
        print("Use a labeling tool like labelImg to annotate the images")


class AutoLabeler:
    """
    Semi-automatic labeling using a pretrained model.
    
    Useful for bootstrapping dataset creation.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize auto-labeler.
        
        Args:
            model_path: Path to pretrained model.
        """
        from ultralytics import YOLO
        
        if model_path:
            self.model = YOLO(model_path)
        else:
            # Use pretrained COCO model and filter for fish-like objects
            self.model = YOLO('yolov8n.pt')
    
    def generate_pseudo_labels(
        self,
        image_dir: str,
        output_dir: str,
        confidence_threshold: float = 0.3,
        target_classes: Optional[List[int]] = None
    ) -> int:
        """
        Generate pseudo-labels using pretrained model.
        
        Args:
            image_dir: Directory containing images.
            output_dir: Output directory for labels.
            confidence_threshold: Minimum confidence for detections.
            target_classes: COCO class IDs to use (None = all).
            
        Returns:
            Number of images labeled.
        """
        image_dir = Path(image_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        images = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png'))
        labeled_count = 0
        
        for img_path in images:
            results = self.model.predict(
                str(img_path),
                conf=confidence_threshold,
                verbose=False
            )
            
            labels = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    
                    if target_classes and cls_id not in target_classes:
                        continue
                    
                    # Get normalized coordinates
                    xyxyn = boxes.xyxyn[i].cpu().numpy()
                    x1, y1, x2, y2 = xyxyn
                    
                    x_center = (x1 + x2) / 2
                    y_center = (y1 + y2) / 2
                    width = x2 - x1
                    height = y2 - y1
                    
                    # Use class 0 (fingerling) for all detections
                    labels.append(f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
            
            if labels:
                label_path = output_dir / img_path.with_suffix('.txt').name
                with open(label_path, 'w') as f:
                    f.write('\n'.join(labels))
                labeled_count += 1
        
        print(f"Generated pseudo-labels for {labeled_count} images")
        return labeled_count


def main():
    """Main entry point for data preparation."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Prepare dataset for training')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Extract frames
    extract_parser = subparsers.add_parser('extract', help='Extract frames from video')
    extract_parser.add_argument('-v', '--video', required=True, help='Input video path')
    extract_parser.add_argument('-o', '--output', required=True, help='Output directory')
    extract_parser.add_argument('-i', '--interval', type=int, default=30, help='Frame interval')
    extract_parser.add_argument('-m', '--max', type=int, default=None, help='Max frames')
    
    # Split dataset
    split_parser = subparsers.add_parser('split', help='Split dataset')
    split_parser.add_argument('-d', '--dir', required=True, help='Image directory')
    split_parser.add_argument('-o', '--output', required=True, help='Output directory')
    split_parser.add_argument('--train', type=float, default=0.8, help='Train ratio')
    split_parser.add_argument('--val', type=float, default=0.15, help='Val ratio')
    
    # Convert annotations
    convert_parser = subparsers.add_parser('convert', help='Convert annotations')
    convert_parser.add_argument('-i', '--input', required=True, help='Input JSON directory')
    convert_parser.add_argument('-o', '--output', required=True, help='Output directory')
    
    args = parser.parse_args()
    
    if args.command == 'extract':
        prep = DatasetPreparator(args.output)
        prep.extract_frames_from_video(
            args.video,
            args.output,
            frame_interval=args.interval,
            max_frames=args.max
        )
    
    elif args.command == 'split':
        prep = DatasetPreparator(args.output)
        prep.split_dataset(args.dir)
    
    elif args.command == 'convert':
        prep = DatasetPreparator(Path(args.output).parent)
        prep.convert_labelme_to_yolo(args.input, args.output)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
