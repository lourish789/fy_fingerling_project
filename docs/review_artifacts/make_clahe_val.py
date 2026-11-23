import cv2, shutil
from pathlib import Path
src = Path('data/fish_fingerling_yolo')
dst = Path(r'C:/Users/hp/AppData/Local/Temp/claude/c--Users-hp-Desktop-Engr-Flourish-fingerling-counting-model/428ce032-ee18-4ada-b953-1f61ab33f938/scratchpad/clahe_ds')
for split in ['val','test']:
    (dst/'images'/split).mkdir(parents=True, exist_ok=True)
    (dst/'labels'/split).mkdir(parents=True, exist_ok=True)
    for p in sorted((src/'images'/split).glob('*')):
        img = cv2.imread(str(p))
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l,a,b = cv2.split(lab)
        cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(l)
        out = cv2.cvtColor(cv2.merge([cl,a,b]), cv2.COLOR_LAB2BGR)
        cv2.imwrite(str(dst/'images'/split/p.name), out)
    for p in sorted((src/'labels'/split).glob('*.txt')):
        shutil.copy(p, dst/'labels'/split/p.name)
    print(split, 'done', len(list((dst/'images'/split).glob('*'))))
