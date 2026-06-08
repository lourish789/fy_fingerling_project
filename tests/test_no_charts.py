def test_dashboard_has_no_chart_references():
    import pathlib
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

    all_text = ''
    for p in repo_files:
        try:
            all_text += p.read_text(encoding='utf-8')
        except Exception:
            continue

    for token in forbidden:
        assert token not in all_text, f"Found forbidden chart token in repository: {token}"
