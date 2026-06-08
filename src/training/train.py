"""
Training Script for Fingerling Detection Model

This module provides functionality to train a custom YOLO model
on catfish fingerling datasets.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml
import shutil

from ultralytics import YOLO


class FingerlingTrainer:
    """
    Trainer for custom fingerling detection model.
    
    Uses YOLO checkpoints as base and fine-tunes on fingerling dataset.
    """
    
    def __init__(
        self,
        data_yaml: str,
        base_model: str = "yolov26n.pt",
        model_engine: str = "ultralytics",
        project_name: str = "fingerling_detector",
        output_dir: str = "runs"
    ):
        """
        Initialize trainer.
        
        Args:
            data_yaml: Path to dataset YAML configuration.
            base_model: Base YOLO model to fine-tune.
            model_engine: Training engine backend selector.
            project_name: Name for training project.
            output_dir: Directory for training outputs.
        """
        self.data_yaml = Path(data_yaml)
        self.base_model = base_model
        self.model_engine = model_engine
        self.project_name = project_name
        self.output_dir = Path(output_dir)
        
        # Validate data config
        if not self.data_yaml.exists():
            raise FileNotFoundError(f"Data config not found: {self.data_yaml}")
        
        # Load model
        self.model = self._load_training_model(base_model)

    def _load_training_model(self, base_model: str) -> YOLO:
        """Load training model with fallback for checkpoint availability."""
        if self.model_engine.lower() != "ultralytics":
            raise ValueError(
                f"Unsupported model_engine='{self.model_engine}'. Supported: ultralytics"
            )

        candidates = [base_model]
        if base_model != "yolov8n.pt":
            candidates.append("yolov8n.pt")

        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                print(f"Loading training checkpoint: {candidate}")
                return YOLO(candidate)
            except Exception as exc:
                last_error = exc
                print(f"Warning: failed to load '{candidate}': {exc}")

        raise RuntimeError(
            "Unable to initialize a training checkpoint. "
            "Tried: " + ", ".join(candidates)
        ) from last_error
    
    def train(
        self,
        epochs: int = 100,
        batch_size: int = 16,
        image_size: int = 640,
        patience: int = 20,
        device: str = "auto",
        workers: int = 8,
        resume: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Train the model.
        
        Args:
            epochs: Number of training epochs.
            batch_size: Batch size for training.
            image_size: Input image size.
            patience: Early stopping patience.
            device: Training device.
            workers: Number of data loader workers.
            resume: Resume from last checkpoint.
            **kwargs: Additional training arguments.
            
        Returns:
            Training results dictionary.
        """
        print(f"\n{'='*50}")
        print("Starting Fingerling Detector Training")
        print(f"{'='*50}")
        print(f"Base model: {self.base_model}")
        print(f"Dataset: {self.data_yaml}")
        print(f"Epochs: {epochs}")
        print(f"Batch size: {batch_size}")
        print(f"Image size: {image_size}")
        print(f"{'='*50}\n")
        
        # Determine device
        if device == "auto":
            import torch
            if torch.cuda.is_available():
                device = 0  # First GPU
            else:
                device = "cpu"
        
        # Train
        results = self.model.train(
            data=str(self.data_yaml),
            epochs=epochs,
            batch=batch_size,
            imgsz=image_size,
            patience=patience,
            device=device,
            workers=workers,
            project=str(self.output_dir),
            name=self.project_name,
            exist_ok=True,
            resume=resume,
            # Data augmentation for aquatic environments
            hsv_h=0.015,  # Image HSV-Hue augmentation
            hsv_s=0.7,    # Image HSV-Saturation augmentation
            hsv_v=0.4,    # Image HSV-Value augmentation
            degrees=10,   # Image rotation
            translate=0.1,
            scale=0.5,
            shear=2.0,
            perspective=0.0001,
            flipud=0.5,   # Flip up-down
            fliplr=0.5,   # Flip left-right
            mosaic=1.0,
            mixup=0.1,
            **kwargs
        )
        
        print(f"\nTraining complete!")
        print(f"Best weights saved to: {self.output_dir / self.project_name / 'weights' / 'best.pt'}")
        
        return results
    
    def validate(self, weights: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate trained model.
        
        Args:
            weights: Path to weights file. Uses best.pt if None.
            
        Returns:
            Validation metrics.
        """
        if weights:
            model = YOLO(weights)
        else:
            best_weights = self.output_dir / self.project_name / 'weights' / 'best.pt'
            if best_weights.exists():
                model = YOLO(str(best_weights))
            else:
                model = self.model
        
        results = model.val(data=str(self.data_yaml))
        
        return results
    
    def export(
        self,
        weights: Optional[str] = None,
        format: str = "onnx",
        output_dir: Optional[str] = None
    ) -> str:
        """
        Export trained model to different formats.
        
        Args:
            weights: Path to weights file.
            format: Export format (onnx, tflite, coreml, etc.).
            output_dir: Output directory.
            
        Returns:
            Path to exported model.
        """
        if weights:
            model = YOLO(weights)
        else:
            best_weights = self.output_dir / self.project_name / 'weights' / 'best.pt'
            model = YOLO(str(best_weights))
        
        export_path = model.export(format=format)
        
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(export_path, output_dir)
            export_path = str(output_dir / Path(export_path).name)
        
        print(f"Model exported to: {export_path}")
        return export_path


def create_dataset_yaml(
    train_path: str,
    val_path: str,
    test_path: Optional[str] = None,
    output_path: str = "data/fingerlings.yaml",
    class_names: Optional[List[str]] = None
) -> str:
    """
    Create dataset YAML configuration file.
    
    Args:
        train_path: Path to training images.
        val_path: Path to validation images.
        test_path: Path to test images (optional).
        output_path: Output YAML file path.
        
    Returns:
        Path to created YAML file.
    """
    class_names = class_names or ['fingerling', 'post_fingerling', 'juvenile']
    names = {index: name for index, name in enumerate(class_names)}

    config = {
        'path': str(Path(output_path).parent.absolute()),
        'train': train_path,
        'val': val_path,
        'names': names,
        'nc': len(class_names)
    }
    
    if test_path:
        config['test'] = test_path
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print(f"Dataset config created: {output_path}")
    return str(output_path)


def main():
    """Main entry point for training."""
    parser = argparse.ArgumentParser(
        description='Train fingerling detection model'
    )
    
    parser.add_argument(
        '-d', '--data',
        default=None,
        help='Path to dataset YAML configuration'
    )
    parser.add_argument(
        '-m', '--model',
        default='yolov26n.pt',
        help='Base model checkpoint (e.g., yolov26n.pt, yolov8n.pt, yolov8s.pt)'
    )
    parser.add_argument(
        '--model-engine',
        default='ultralytics',
        help='Model engine backend (currently: ultralytics)'
    )
    parser.add_argument(
        '-e', '--epochs',
        type=int,
        default=100,
        help='Number of training epochs'
    )
    parser.add_argument(
        '-b', '--batch',
        type=int,
        default=16,
        help='Batch size'
    )
    parser.add_argument(
        '-i', '--imgsz',
        type=int,
        default=640,
        help='Input image size'
    )
    parser.add_argument(
        '--device',
        default='auto',
        help='Training device (auto, 0, 1, cpu)'
    )
    parser.add_argument(
        '-o', '--output',
        default='runs',
        help='Output directory'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume training from last checkpoint'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only run validation'
    )
    parser.add_argument(
        '--export',
        default=None,
        help='Export format (onnx, tflite, coreml)'
    )
    parser.add_argument(
        '-w', '--weights',
        default=None,
        help='Path to weights file for validation/export'
    )
    parser.add_argument(
        '--prepare-zip',
        default=None,
        help='Path to a COCO zip dataset to extract and convert to YOLO format before training'
    )
    parser.add_argument(
        '--prepared-output',
        default='data/fish_fingerling_yolo',
        help='Output folder for prepared YOLO dataset'
    )
    parser.add_argument(
        '--prepared-yaml',
        default='data/fish_fingerling.yaml',
        help='Output dataset YAML path created during zip preparation'
    )
    
    args = parser.parse_args()

    if args.prepare_zip:
        from .prepare_dataset import prepare_coco_zip_dataset
        prepared_yaml = prepare_coco_zip_dataset(
            zip_path=args.prepare_zip,
            output_root=args.prepared_output,
            output_yaml=args.prepared_yaml
        )
        args.data = prepared_yaml

    if not args.data:
        parser.error('Provide --data or use --prepare-zip to build one automatically.')
    
    trainer = FingerlingTrainer(
        data_yaml=args.data,
        base_model=args.model,
        model_engine=args.model_engine,
        output_dir=args.output
    )
    
    if args.validate_only:
        results = trainer.validate(weights=args.weights)
        print(f"Validation results: {results}")
    elif args.export:
        export_path = trainer.export(
            weights=args.weights,
            format=args.export
        )
        print(f"Exported to: {export_path}")
    else:
        results = trainer.train(
            epochs=args.epochs,
            batch_size=args.batch,
            image_size=args.imgsz,
            device=args.device,
            resume=args.resume
        )


if __name__ == '__main__':
    main()
