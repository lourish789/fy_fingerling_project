"""End-to-end run of the shipped pipeline on a video, under several configurations."""
import sys, time, json, argparse
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path('src').resolve()))
from ultralytics import YOLO
from models.tracker import FingerlingTracker

NAMES = {0:'fingerling', 1:'post_fingerling', 2:'juvenile'}

def run(video, conf, iou, mode, min_hits, count_min_hits, max_dist, max_age,
        line_pos=0.5, imgsz=640, stride=1, limit=None, dump=None):
    model = YOLO('models/best.pt')
    cap = cv2.VideoCapture(video)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tr = FingerlingTracker(max_age=max_age, min_hits=min_hits, iou_threshold=0.3,
                           max_distance=max_dist, counting_mode=mode,
                           count_min_hits=count_min_hits)
    if mode == 'line_crossing':
        y = int(H*line_pos); tr.set_counting_line(0, y, W, y, 'horizontal')
    i = 0; nproc = 0; det_total = 0; frames_with_det = 0
    t0 = time.time(); infer_ms = 0.0
    counted_events = []
    prev_counted = set()
    while True:
        ok, frame = cap.read()
        if not ok: break
        if stride > 1 and i % stride:
            i += 1; continue
        ts = time.time()
        r = model.predict(frame, conf=conf, iou=iou, imgsz=imgsz, verbose=False, device='cpu')[0]
        infer_ms += (time.time()-ts)*1000
        dets = []
        for b in r.boxes:
            x1,y1,x2,y2 = [int(v) for v in b.xyxy[0].tolist()]
            c = int(b.cls.item())
            dets.append({'bbox':[x1,y1,x2,y2], 'center':((x1+x2)//2,(y1+y2)//2),
                         'class_name':NAMES[c], 'confidence':float(b.conf.item())})
        det_total += len(dets); frames_with_det += (1 if dets else 0)
        tr.update(dets)
        for t in tr.tracks:
            if t.counted and t.track_id not in prev_counted:
                prev_counted.add(t.track_id)
                counted_events.append({'frame':i, 'track':t.track_id, 'cls':t.class_name,
                                       'center':t.center, 'bbox':t.bbox, 'conf':round(t.confidence,3)})
        nproc += 1; i += 1
        if limit and nproc >= limit: break
    cap.release()
    counts = tr.get_counts()
    out = {'video':Path(video).name, 'conf':conf, 'mode':mode, 'min_hits':min_hits,
           'count_min_hits':count_min_hits, 'max_dist':max_dist, 'imgsz':imgsz,
           'frames_processed':nproc, 'detections_total':det_total,
           'frames_with_detection':frames_with_det,
           'mean_det_per_frame':round(det_total/max(1,nproc),3),
           'tracks_created':tr.next_id-1,
           'COUNT_total':counts.get('total',0),
           'per_class':{k:v for k,v in counts.items() if k!='total'},
           'wall_s':round(time.time()-t0,1),
           'mean_inference_ms':round(infer_ms/max(1,nproc),1)}
    if dump:
        Path(dump).write_text(json.dumps({'summary':out,'events':counted_events}, indent=1))
    return out, counted_events

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('--conf', type=float, default=0.15)
    ap.add_argument('--iou', type=float, default=0.45); ap.add_argument('--mode', default='unique_track')
    ap.add_argument('--min-hits', type=int, default=2); ap.add_argument('--count-min-hits', type=int, default=2)
    ap.add_argument('--max-dist', type=int, default=160); ap.add_argument('--max-age', type=int, default=30)
    ap.add_argument('--imgsz', type=int, default=640); ap.add_argument('--stride', type=int, default=1)
    ap.add_argument('--limit', type=int, default=None); ap.add_argument('--dump', default=None)
    a = ap.parse_args()
    s, ev = run(a.video, a.conf, a.iou, a.mode, a.min_hits, a.count_min_hits,
                a.max_dist, a.max_age, imgsz=a.imgsz, stride=a.stride, limit=a.limit, dump=a.dump)
    print(json.dumps(s, indent=1))
