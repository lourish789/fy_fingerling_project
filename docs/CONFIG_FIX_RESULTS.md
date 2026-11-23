# Config fix — measured before/after on the field footage

**Date:** 2026-11-05 · **Weights:** `models/best.pt` (unchanged) · **Backend:** PyTorch/Ultralytics
8.4.21, CPU, imgsz 640 · **Every frame processed, stride 1.**

Reproduce with `docs/review_artifacts/run_ab.py` (run from the repository root). Raw per-event
output: `docs/review_artifacts/config_fix_ab_results.json`.

---

## 1. What changed

| | OLD arm (config as it shipped) | NEW arm (config as it now ships) |
|---|---|---|
| Confidence threshold | 0.15 | **0.50** |
| NMS IoU | 0.45 | **0.50** |
| Counting mode | `unique_track` | **`line_crossing`** @ y = 0.50 |
| Direction gate | none | **downstream only** |
| `min_hits` / `count_min_hits` | 2 / 2 | **3 / 3** |
| Class at count time | last matched frame | **majority vote over track** |

Code changes: `config/config.yaml`, `src/models/tracker.py` (`Track.class_votes`,
`Track.get_voted_class()`, direction gate in `_check_line_crossings()`), `src/app/counter.py`
(passes `count_direction`), `src/streaming/server.py` (CSV header newline bug).

## 2. Headline result

| Video | Fish actually present | OLD count | NEW count |
|---|---|---|---|
| `VID_20260617_151331.mp4` (2 294 frames, 85.6 s) | ≈ 0–1 | **49** | **0** |
| `VID_20260617_151857.mp4` (2 815 frames, 102.1 s) | 1–2 | **111** | **2** |
| **Total** | **≈ 1–3** | **160** | **2** |

**158 of 160 phantom counts removed (98.75%).**

Supporting detail:

| Metric | 151331 OLD → NEW | 151857 OLD → NEW |
|---|---|---|
| Raw detections | 437 → 66 (−85%) | 2 514 → 206 (−92%) |
| Frames with ≥1 detection | 393 → 66 | 1 861 → 197 |
| Tracks created | 90 → 15 | 140 → 49 |
| Throughput (CPU) | 2.53 → 3.83 FPS | 2.53 → 3.12 FPS |

Throughput improves because the tracker has far fewer spurious detections to associate.

## 3. The two surviving counts are still false positives

Both counted events on `VID_20260617_151857.mp4` were inspected frame by frame. **Neither is a
fish.** Both are the turbulent water surface *inside* the channel, detected as `juvenile`:

| Frame | Track | Direction | Class (votes) | Confidence | Box (px) | Reality |
|---|---|---|---|---|---|---|
| 732 | 8 | down | juvenile (3/3) | **0.782** | 756,409 → 1345,690 | water surface in pipe |
| 1366 | 27 | down | juvenile (3/3) | 0.647 | 482,451 → 1070,725 | water surface / cut rim |

Evidence: `docs/review_artifacts/fixed_config_fp_waterline_f732.jpg`,
`fixed_config_fp_waterline_f1366.jpg`.

**Three consequences, all of which matter for the paper:**

1. **Framing the camera on the channel alone does not eliminate false positives.** The earlier
   review attributed the false positives to out-of-channel background — pavement, puddles, pipe
   exterior — and recommended an enclosure that sees only the channel. These two detections are
   *inside* the channel, on open water. The enclosure recommendation is still right, but it is not
   sufficient, and the paper should not claim it is.
2. **Raising the confidence threshold cannot fix this.** The model assigns **0.78** to empty
   turbulent water. No threshold that retains real fingerlings (which are detected far less
   confidently) will reject this. Only negative training examples will — which is the single
   highest-value outstanding fix (`MANUSCRIPT_REVIEW.md` §1.5).
3. **The direction gate was defeated by camera motion.** The pipe is static in the world, but the
   camera pans, so a static-in-world false positive translates downward in frame and reads as a
   downstream crossing. On fixed-camera footage — which is how the validation rounds were shot —
   the gate is considerably stronger than this test shows. **This footage is a worst case for the
   gate, not a representative one.**

## 4. What the majority vote changed

Re-scoring the OLD arm's counted events under both rules:

| Video | Counted events | Would be sorted into a *different* size class by the last-frame rule |
|---|---|---|
| `VID_20260617_151331.mp4` | 49 | 3 (6%) |
| `VID_20260617_151857.mp4` | 111 | **26 (23%)** |

Roughly one counted fish in four was being size-sorted by whichever label happened to land on its
final frame. Since size sorting *is* the class assignment, this was a material defect in the
grading claim, not a cosmetic one.

## 5. Honest limits of this test

* **Neither video contains a usable number of real fish.** They are rig-documentation clips:
  handheld, panning, channel empty for most of the runtime. They measure *false positives* well and
  *recall* not at all.
* **The NEW configuration counted zero real fish in either clip.** With 1–3 fish actually present
  and both counted events being false positives, recall on this footage is effectively zero. That
  is not a fair recall estimate — the fish are mostly out of frame — but it is not evidence of good
  recall either, and nothing here should be cited as such.
* **This does not revalidate the 86.5% counting result.** That came from fixed-camera tank rounds
  with hand-counted references. This test establishes only that the shipped configuration now
  behaves like the configuration the manuscript describes.

## 6. Still outstanding

1. **Background/negative images** — 30–50 frames of the empty rig *and the empty water surface*,
   with empty label files, then retrain. Section 3 shows why this is now the top priority.
2. **Per-fish event log** — `timestamp, track_id, class, frame, bbox`, so the auditability claim in
   the paper becomes true.
3. **Re-run the detection metrics** through the deployed path (ONNX + CLAHE) and report which
   configuration produced which table.
