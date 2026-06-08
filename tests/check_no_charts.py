import pathlib
import sys

repo_root = pathlib.Path(__file__).resolve().parents[1]
src_dir = repo_root / 'src'
repo_files = list(src_dir.rglob('*.py'))
forbidden = [
    'cdn.jsdelivr.net/npm/chart.js',
    'distributionChart',
    'new Chart(',
    'Chart(',
    'Draw bar chart',
    'chart_x',
    'bar_width',
]

found = []
for p in repo_files:
    try:
        txt = p.read_text(encoding='utf-8')
    except Exception:
        continue
    for token in forbidden:
        if token in txt:
            found.append((str(p), token))

if found:
    print('Found forbidden chart tokens:')
    for f in found:
        print(f[0], '-', f[1])
    sys.exit(2)
else:
    print('No chart tokens found.')
    sys.exit(0)
