"""
Dataset preparation utilities for COCO zip exports.

This converts Roboflow-style COCO split exports into a YOLO directory layout
that Ultralytics training can use directly.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


def normalize_class_name(name: str) -> str:
    """Normalize noisy label variants to canonical classes."""
    normalized = name.strip().lower().replace('-', '_').replace(' ', '_')

    if 'juvenile' in normalized and ('post' in normalized or 'pos' in normalized):
        return 'post_fingerling'
    if 'post' in normalized or 'posfinger' in normalized:
        return 'post_fingerling'
    if normalized == 'juvenile' or normalized.startswith('juvenile_'):
        return 'juvenile'
    if 'fingerling' in normalized:
        return 'fingerling'
    return normalized if normalized else 'unknown'


def coco_bbox_to_yolo(
    bbox: List[float], image_width: int, image_height: int
) -> Tuple[float, float, float, float]:
    """Convert COCO bbox [x, y, w, h] to YOLO normalized format."""
    x, y, w, h = bbox
    x_center = (x + w / 2.0) / image_width
    y_center = (y + h / 2.0) / image_height
    width = w / image_width
    height = h / image_height
    return x_center, y_center, width, height


def _extract_zip(zip_path: Path, extract_to: Path) -> None:
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)


def _collect_split_dirs(extracted_root: Path) -> Dict[str, Path]:
    # Support both valid and val naming.
    split_aliases = {
        'train': ['train'],
        'val': ['val', 'valid'],
        'test': ['test']
    }

    resolved: Dict[str, Path] = {}
    for split_key, candidates in split_aliases.items():
        for candidate in candidates:
            candidate_path = extracted_root / candidate
            if candidate_path.exists():
                resolved[split_key] = candidate_path
                break
    if 'train' not in resolved or 'val' not in resolved:
        raise FileNotFoundError('Dataset must contain train and valid/val folders.')
    return resolved


def _convert_split(
    split_name: str,
    split_dir: Path,
    output_root: Path,
    class_to_index: Dict[str, int],
) -> None:
    images_out = output_root / 'images' / split_name
    labels_out = output_root / 'labels' / split_name
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)

    annotation_path = split_dir / '_annotations.coco.json'
    if not annotation_path.exists():
        raise FileNotFoundError(f'Missing annotation file: {annotation_path}')

    with open(annotation_path, 'r', encoding='utf-8') as f:
        coco = json.load(f)

    image_lookup = {image['id']: image for image in coco.get('images', [])}

    labels_by_image: Dict[int, List[str]] = {image_id: [] for image_id in image_lookup}
    category_by_id = {
        category['id']: normalize_class_name(category.get('name', 'unknown'))
        for category in coco.get('categories', [])
    }

    for ann in coco.get('annotations', []):
        image_id = ann['image_id']
        image_info = image_lookup.get(image_id)
        if image_info is None:
            continue

        class_key = category_by_id.get(ann.get('category_id'), 'unknown')
        if class_key not in class_to_index:
            continue

        x_center, y_center, width, height = coco_bbox_to_yolo(
            ann['bbox'], image_info['width'], image_info['height']
        )
        class_id = class_to_index[class_key]
        labels_by_image[image_id].append(
            f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        )

    for image_id, image_info in image_lookup.items():
        source_image = split_dir / image_info['file_name']
        if not source_image.exists():
            continue

        target_image = images_out / image_info['file_name']
        target_image.write_bytes(source_image.read_bytes())

        label_path = labels_out / f"{Path(image_info['file_name']).stem}.txt"
        label_path.write_text('\n'.join(labels_by_image.get(image_id, [])), encoding='utf-8')


def prepare_coco_zip_dataset(
    zip_path: str,
    output_root: str = 'data/fish_fingerling_yolo',
    output_yaml: str = 'data/fish_fingerling.yaml',
) -> str:
    """
    Extract and convert a COCO zip dataset into YOLO training format.

    Returns the generated dataset yaml path.
    """
    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise FileNotFoundError(f'Zip file not found: {zip_file}')

    output_root_path = Path(output_root)
    extracted_root = output_root_path / '_extracted'
    _extract_zip(zip_file, extracted_root)

    split_dirs = _collect_split_dirs(extracted_root)

    class_names = ['fingerling', 'post_fingerling', 'juvenile']
    class_to_index = {name: index for index, name in enumerate(class_names)}

    _convert_split('train', split_dirs['train'], output_root_path, class_to_index)
    _convert_split('val', split_dirs['val'], output_root_path, class_to_index)
    if 'test' in split_dirs:
        _convert_split('test', split_dirs['test'], output_root_path, class_to_index)

    dataset_yaml_path = Path(output_yaml)
    dataset_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        'path': str(output_root_path.resolve()),
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'names': {idx: name for idx, name in enumerate(class_names)},
        'nc': len(class_names),
    }

    with open(dataset_yaml_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, sort_keys=False)

    return str(dataset_yaml_path)
