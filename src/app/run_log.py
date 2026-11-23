"""
Per-run audit records.

Every counting run (one video, stream or camera session) gets its own folder:

    output/runs/<run_id>/
        events.csv      one row per counted fish, written as it happens
        crops/          optional image of each counted fish, for spot checks
        summary.json    totals, settings and model used, written at the end
        report.html     printable one-page summary for the batch

events.csv is flushed after every row, so a crash or power cut keeps the
fish counted up to that point.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

EVENT_COLUMNS = [
    "seq", "wall_time", "video_time_s", "frame", "track_id", "class", "votes",
    "hits", "mean_confidence", "direction", "x1", "y1", "x2", "y2", "crop",
]

_RUN_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def file_fingerprint(path: Optional[str]) -> str:
    """Short SHA-256 of a file (identifies exactly which model produced a count)."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except (OSError, TypeError):
        return "unknown"


class RunRecorder:
    """Writes the audit trail for one counting run."""

    def __init__(
        self,
        runs_dir: Path,
        source_label: str,
        settings: Dict[str, Any],
        class_keys: List[str],
        save_crops: bool = True,
        correction_factor: float = 1.0,
        correction_note: str = "",
    ):
        self.started_at = datetime.now()
        stem = _RUN_ID_SAFE.sub("-", Path(str(source_label)).stem)[:40].strip("-") or "run"
        base = f"{self.started_at:%Y%m%d_%H%M%S}_{stem}"
        self.run_id = base
        self.dir = Path(runs_dir) / base
        n = 1
        while self.dir.exists():
            n += 1
            self.run_id = f"{base}_{n}"
            self.dir = Path(runs_dir) / self.run_id
        self.dir.mkdir(parents=True)

        self.source_label = Path(str(source_label)).name or str(source_label)
        self.settings = settings
        self.class_keys = list(class_keys)
        self.save_crops = save_crops
        self.correction_factor = float(correction_factor or 1.0)
        self.correction_note = correction_note
        self.n_events = 0

        self._crops_dir = self.dir / "crops"
        if save_crops:
            self._crops_dir.mkdir()

        self._events_file = open(self.dir / "events.csv", "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._events_file)
        self._writer.writerow(EVENT_COLUMNS)
        self._events_file.flush()

    # ── During the run ──────────────────────────────────────────────────────
    def record(self, events: List[Dict[str, Any]], frame: np.ndarray, video_time_s: float) -> None:
        for ev in events:
            x1, y1, x2, y2 = ev["bbox"]
            crop_name = ""
            if self.save_crops and frame is not None:
                crop_name = self._save_crop(ev, frame)
            votes = ";".join(f"{k}:{v}" for k, v in sorted(ev.get("votes", {}).items()))
            self._writer.writerow([
                ev["seq"], datetime.now().isoformat(timespec="seconds"), f"{video_time_s:.2f}",
                ev["frame"], ev["track_id"], ev["class"], votes, ev["hits"],
                f"{ev['mean_confidence']:.3f}", ev["direction"], x1, y1, x2, y2, crop_name,
            ])
            self.n_events += 1
        if events:
            self._events_file.flush()

    def _save_crop(self, ev: Dict[str, Any], frame: np.ndarray) -> str:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = ev["bbox"]
        pad = int(0.25 * max(x2 - x1, y2 - y1)) + 8
        crop = frame[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
        if crop.size == 0:
            return ""
        scale = 200.0 / max(crop.shape[:2])
        if scale < 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        name = f"{ev['seq']:06d}_{ev['class']}.jpg"
        cv2.imwrite(str(self._crops_dir / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return f"crops/{name}"

    # ── End of run ──────────────────────────────────────────────────────────
    def finish(self, counts: Dict[str, int], status: str, frames_processed: int,
               video_info: Optional[Dict[str, Any]] = None, error: str = "") -> Dict[str, Any]:
        try:
            self._events_file.close()
        except Exception:
            pass

        ended_at = datetime.now()
        elapsed = max((ended_at - self.started_at).total_seconds(), 1e-6)
        total = int(counts.get("total", 0))
        info = video_info or {}

        summary: Dict[str, Any] = {
            "run_id": self.run_id,
            "source": self.source_label,
            "status": status,
            "error": error,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "processing_seconds": round(elapsed, 1),
            "frames_processed": int(frames_processed),
            "source_frames": int(info.get("total_frames") or 0),
            "source_fps": round(float(info.get("fps") or 0), 2),
            "processing_fps": round(frames_processed / elapsed, 2),
            "counts": {k: int(counts.get(k, 0)) for k in ["total", *self.class_keys, "unknown"]},
            "events_logged": self.n_events,
            "correction_factor": self.correction_factor,
            "corrected_total": (round(total * self.correction_factor)
                                if self.correction_factor != 1.0 else None),
            "correction_note": self.correction_note,
            "settings": self.settings,
            "files": {
                "events_csv": "events.csv",
                "summary_json": "summary.json",
                "report_html": "report.html",
            },
        }
        if status != "completed":
            summary["warning"] = (
                f"Run ended as '{status}' before the end of the source. "
                "Counts cover only the part that was processed."
            )

        with open(self.dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        (self.dir / "report.html").write_text(render_report(summary), encoding="utf-8")
        return summary


def render_report(s: Dict[str, Any]) -> str:
    """A plain, printable one-page batch report (no scripts, no external assets)."""
    e = html.escape
    counts = s["counts"]
    class_rows = "".join(
        f"<tr><td>{e(k.replace('_', ' ').title())}</td><td class='n'>{v}</td></tr>"
        for k, v in counts.items() if k != "total"
    )
    st = s.get("settings", {})
    setting_rows = "".join(
        f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>" for k, v in st.items()
    )
    corrected = ""
    if s.get("corrected_total") is not None:
        corrected = (
            f"<p class='big'>Calibrated estimate: <b>{s['corrected_total']}</b> "
            f"<span class='dim'>(raw {counts['total']} × {s['correction_factor']:.3f})</span></p>"
            f"<p class='dim'>{e(s.get('correction_note') or '')}</p>"
        )
    warning = f"<p class='warn'>{e(s['warning'])}</p>" if s.get("warning") else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AquaCount report {e(s['run_id'])}</title>
<style>
 body {{ font: 15px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: #111;
        background: #fff; max-width: 720px; margin: 24px auto; padding: 0 16px; }}
 h1 {{ font-size: 22px; margin: 0 0 4px; }}
 .dim {{ color: #666; }} .big {{ font-size: 20px; }}
 .warn {{ background: #fff4e5; border-left: 4px solid #e8a33d; padding: 8px 12px; }}
 table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
 td {{ border-bottom: 1px solid #ddd; padding: 6px 8px; }} td.n {{ text-align: right; font-weight: 600; }}
 .total td {{ font-size: 18px; font-weight: 700; border-bottom: 2px solid #111; }}
 @media print {{ body {{ margin: 0; }} }}
</style></head><body>
<h1>AquaCount: batch count report</h1>
<p class="dim">Run {e(s['run_id'])} · source {e(s['source'])} · status {e(s['status'])}</p>
{warning}
<table>
 <tr class="total"><td>Total counted (machine)</td><td class="n">{counts['total']}</td></tr>
 {class_rows}
</table>
{corrected}
<table>
 <tr><td>Started</td><td>{e(s['started_at'])}</td></tr>
 <tr><td>Ended</td><td>{e(s['ended_at'])}</td></tr>
 <tr><td>Frames processed</td><td>{s['frames_processed']} of {s['source_frames'] or 'live'}</td></tr>
 <tr><td>Processing speed</td><td>{s['processing_fps']} frames/s (source {s['source_fps']} frames/s)</td></tr>
 <tr><td>Fish events logged</td><td>{s['events_logged']} (see events.csv)</td></tr>
</table>
<p class="dim">Settings used</p>
<table>{setting_rows}</table>
<p class="dim">Machine counts are estimates. Check them against a hand count before
relying on them for a sale. See docs/HATCHERY_DEPLOYMENT.md, section "Calibration".</p>
</body></html>
"""
