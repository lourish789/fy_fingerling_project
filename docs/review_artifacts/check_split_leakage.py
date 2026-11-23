import re, sys
from pathlib import Path
base = Path.cwd()
def stamps(split):
    out=[]
    for f in sorted((base/split).glob('*.jpg')):
        m = re.search(r'IMG_(\d{8})_(\d{6})(?:_(\d{3}))?', f.name)
        if not m: continue
        hh,mm,ss = int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6])
        t = hh*3600+mm*60+ss
        out.append((t, f.name, split))
    return out
tr, va, te = stamps('train'), stamps('valid'), stamps('test')
alltr = sorted(tr)
print(f"train {len(tr)}  valid {len(va)}  test {len(te)}")
span = max(t for t,_,_ in tr+va+te) - min(t for t,_,_ in tr+va+te)
print(f"whole dataset captured within {span/60:.1f} minutes of one morning")
for name, other in (('valid', va), ('test', te)):
    close=[]
    for t,f,_ in other:
        d = min(abs(t-t2) for t2,_,_ in alltr)
        close.append(d)
    for thr in (0,1,2,5):
        n = sum(1 for d in close if d<=thr)
        print(f"  {name}: {n}/{len(other)} ({100*n/len(other):.0f}%) images within {thr}s of a TRAIN image")
