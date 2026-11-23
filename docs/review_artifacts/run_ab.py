"""A/B run of the counting pipeline: old shipped config vs new fixed config.

Reads the real config/config.yaml for the "new" arm so the test exercises what
actually ships, and hard-codes the pre-fix values for the "old" arm.
"""
import sys, time, json, argparse
from pathlib import Path
import cv2, yaml

ROOT = Path(__file__).resolve()
PROJ = Path(sys.argv[-1]) if False else Path.cwd()
sys.path.insert(0, str((PROJ / 'src').resolve()))

from ultralytics import YOLO
from models.tracker import FingerlingTracker

NAMES = {0: 'fingerling', 1: 'post_fingerling', 2: 'juvenile'}


def run(model, video, arm, p, stride=1, limit=None):
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_src = cap.get(cv2.CAP_PROP_FPS)

    tr = FingerlingTracker(
        max_age=p['max_age'], min_hits=p['min_hits'],
        iou_threshold=0.3, max_distance=p['max_distance'],
        counting_mode=p['mode'], count_min_hits=p['count_min_hits'],
        count_direction=p.get('count_direction', 'any'),
    )
    if p['mode'] == 'line_crossing':
        y = int(H * p.get('line_pos', 0.5))
        tr.set_counting_line(0, y, W, y, 'horizontal')

    i = nproc = det_total = frames_with_det = 0
    infer_ms = 0.0
    events = []
    seen = set()
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if stride > 1 and i % stride:
            i += 1
            continue
        ts = time.time()
        r = model.predict(frame, conf=p['conf'], iou=p['iou'], imgsz=640,
                          verbose=False, device='cpu')[0]
        infer_ms += (time.time() - ts) * 1000
        dets = []
        for b in r.boxes:
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            c = int(b.cls.item())
            dets.append({'bbox': [x1, y1, x2, y2],
                         'center': ((x1 + x2) // 2, (y1 + y2) // 2),
                         'class_name': NAMES[c],
                         'confidence': float(b.conf.item())})
        det_total += len(dets)
        frames_with_det += 1 if dets else 0
        tr.update(dets)
        for t in tr.tracks:
            if t.counted and t.track_id not in seen:
                seen.add(t.track_id)
                events.append({
                    'frame': i, 'track': t.track_id,
                    'voted_cls': t.get_voted_class(),
                    'last_cls': t.class_name,
                    'votes': dict(t.class_votes),
                    'direction': t.direction,
                    'center': list(t.center), 'bbox': list(t.bbox),
                    'conf': round(t.confidence, 3),
                })
        nproc += 1
        i += 1
        if limit and nproc >= limit:
            break
    cap.release()

    counts = tr.get_counts()
    flicker = sum(1 for e in events if e['voted_cls'] != e['last_cls'])
    return {
        'arm': arm, 'video': Path(video).name,
        'params': p,
        'src_fps': round(fps_src, 1), 'frames_processed': nproc,
        'detections_total': det_total,
        'frames_with_detection': frames_with_det,
        'mean_det_per_frame': round(det_total / max(1, nproc), 3),
        'tracks_created': tr.next_id - 1,
        'COUNT_total': counts.get('total', 0),
        'per_class': {k: v for k, v in counts.items() if k != 'total'},
        'events_where_vote_changed_label': flicker,
        'mean_inference_ms': round(infer_ms / max(1, nproc), 1),
        'throughput_fps': round(nproc / max(0.001, (time.time() - t0)), 2),
        'wall_s': round(time.time() - t0, 1),
        'events': events,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stride', type=int, default=1)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--out', default='ab_results.json')
    a = ap.parse_args()

    cfg = yaml.safe_load((PROJ / 'config' / 'config.yaml').read_text())
    new = {
        'conf': cfg['model']['confidence_threshold'],
        'iou': cfg['model']['iou_threshold'],
        'mode': cfg['counting']['mode'],
        'min_hits': cfg['tracking']['min_hits'],
        'count_min_hits': cfg['counting']['count_min_hits'],
        'count_direction': cfg['counting'].get('count_direction', 'any'),
        'max_age': cfg['tracking']['max_age'],
        'max_distance': cfg['tracking']['max_distance'],
        'line_pos': cfg['counting']['counting_line_position'],
    }
    old = {'conf': 0.15, 'iou': 0.45, 'mode': 'unique_track', 'min_hits': 2,
           'count_min_hits': 2, 'count_direction': 'any', 'max_age': 30,
           'max_distance': 160, 'line_pos': 0.5}

    model = YOLO(str(PROJ / 'models' / 'best.pt'))
    videos = sorted(PROJ.glob('VID_*.mp4'))
    results = []
    for v in videos:
        for arm, p in (('OLD (pre-fix shipped)', old), ('NEW (fixed config)', new)):
            print(f'--- {arm} :: {v.name}', flush=True)
            res = run(model, v, arm, p, stride=a.stride, limit=a.limit)
            print(json.dumps({k: res[k] for k in
                              ('arm', 'video', 'COUNT_total', 'per_class',
                               'tracks_created', 'detections_total',
                               'events_where_vote_changed_label',
                               'throughput_fps')}, indent=2), flush=True)
            results.append(res)
    Path(a.out).write_text(json.dumps(results, indent=2))
    print('WROTE', a.out, flush=True)


if __name__ == '__main__':
    main()
