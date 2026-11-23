"""Confidence-threshold sweep with detection AND image-level counting metrics."""
import sys, json
from pathlib import Path
import numpy as np, cv2
from ultralytics import YOLO

def load_gt(lbl, W, H):
    boxes, cls = [], []
    if not Path(lbl).exists(): return np.zeros((0,4)), np.zeros((0,),int)
    for line in open(lbl):
        p = line.split()
        if len(p) < 5: continue
        c, xc, yc, w, h = int(p[0]), *map(float, p[1:5])
        boxes.append([(xc-w/2)*W, (yc-h/2)*H, (xc+w/2)*W, (yc+h/2)*H]); cls.append(c)
    return np.array(boxes).reshape(-1,4), np.array(cls, int)

def iou_mat(a, b):
    if len(a)==0 or len(b)==0: return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:,None,0], b[None,:,0]); y1 = np.maximum(a[:,None,1], b[None,:,1])
    x2 = np.minimum(a[:,None,2], b[None,:,2]); y2 = np.minimum(a[:,None,3], b[None,:,3])
    inter = np.clip(x2-x1,0,None)*np.clip(y2-y1,0,None)
    aa = (a[:,2]-a[:,0])*(a[:,3]-a[:,1]); bb = (b[:,2]-b[:,0])*(b[:,3]-b[:,1])
    return inter/(aa[:,None]+bb[None,:]-inter+1e-9)

def evaluate(model, img_dir, lbl_dir, conf, clahe, iou_nms=0.45, iou_match=0.5):
    TP=FP=FN=0; errs=[]; gts=[]; preds=[]
    for p in sorted(Path(img_dir).glob('*')):
        img = cv2.imread(str(p))
        if img is None: continue
        H,W = img.shape[:2]
        if clahe:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB); l,a,b = cv2.split(lab)
            img = cv2.cvtColor(cv2.merge([cv2.createCLAHE(2.0,(8,8)).apply(l),a,b]), cv2.COLOR_LAB2BGR)
        r = model.predict(img, conf=conf, iou=iou_nms, imgsz=640, verbose=False, device='cpu')[0]
        db = r.boxes.xyxy.cpu().numpy() if len(r.boxes) else np.zeros((0,4))
        dc = r.boxes.conf.cpu().numpy() if len(r.boxes) else np.zeros((0,))
        order = np.argsort(-dc); db = db[order]
        gb, gc = load_gt(Path(lbl_dir)/(p.stem+'.txt'), W, H)
        M = iou_mat(db, gb); used=set(); tp=0
        for i in range(len(db)):
            best=-1; bi=-1
            for j in range(len(gb)):
                if j in used: continue
                if M[i,j] > best: best=M[i,j]; bi=j
            if bi>=0 and best>=iou_match: used.add(bi); tp+=1
        TP+=tp; FP+=len(db)-tp; FN+=len(gb)-tp
        errs.append(len(db)-len(gb)); gts.append(len(gb)); preds.append(len(db))
    P = TP/(TP+FP) if TP+FP else 0; R = TP/(TP+FN) if TP+FN else 0
    F1 = 2*P*R/(P+R) if P+R else 0
    e = np.array(errs, float); g = np.array(gts, float); pr = np.array(preds, float)
    return dict(conf=conf, clahe=clahe, TP=TP, FP=FP, FN=FN, P=round(P,3), R=round(R,3), F1=round(F1,3),
                MAE=round(np.abs(e).mean(),3), RMSE=round(float(np.sqrt((e**2).mean())),3),
                bias=round(e.mean(),3),
                MAPE_pct=round(float(100*np.mean(np.abs(e)/np.maximum(g,1))),2),
                total_gt=int(g.sum()), total_pred=int(pr.sum()),
                aggregate_count_ratio_pct=round(100*pr.sum()/g.sum(),2))

if __name__ == '__main__':
    m = YOLO('models/best.pt')
    root = Path('data/fish_fingerling_yolo')
    out=[]
    for split in ['val','test']:
        for clahe in [False, True]:
            for conf in [0.15, 0.25, 0.35, 0.50]:
                r = evaluate(m, root/'images'/split, root/'labels'/split, conf, clahe)
                r['split']=split; out.append(r)
                print(f"{split:5} clahe={str(clahe):5} conf={conf:.2f}  P={r['P']:.3f} R={r['R']:.3f} F1={r['F1']:.3f} "
                      f"| count MAE={r['MAE']:.2f} RMSE={r['RMSE']:.2f} bias={r['bias']:+.2f} MAPE={r['MAPE_pct']:.1f}% "
                      f"| agg {r['total_pred']}/{r['total_gt']} = {r['aggregate_count_ratio_pct']:.1f}%", flush=True)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
