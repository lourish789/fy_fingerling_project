# Review artefacts

Everything here was produced while checking `Olaiya_2026_Smartphone_Catfish_Fingerling_Counting_Manuscript.pdf`
against this repository. See `../MANUSCRIPT_REVIEW.md` for the findings.

All runs used `models/best.pt`, Ultralytics 8.4.21, `imgsz 640`, CPU only (Intel i5-6300U).

## Scripts

| File | What it does | How to run |
|---|---|---|
| `run_pipeline.py` | Replicates the shipped pipeline (same weights, same `FingerlingTracker`) over a video and logs every counted event with frame, track id, class and bbox. | `python docs/review_artifacts/run_pipeline.py VID.mp4 --conf 0.15 --mode unique_track --min-hits 2 --count-min-hits 2 --dump out.json` |
| `conf_sweep.py` | Confidence sweep on val/test with detection metrics **and** image-level counting metrics (MAE, RMSE, bias, MAPE). | `python docs/review_artifacts/conf_sweep.py out.json` |
| `stats_check.py` | Re-derives every statistic in §3.3, §3.4 and Table 5, plus a cluster bootstrap over the nine rounds. | `python docs/review_artifacts/stats_check.py` |
| `bench_runtime.py` | PyTorch vs ONNX latency and detection parity on CPU. | `python docs/review_artifacts/bench_runtime.py` |
| `make_clahe_val.py` | Writes CLAHE-preprocessed copies of the val/test splits so `model.val()` can measure the deployed preprocessing. | edit the output path, then run |

Run them from the repository root with the project virtualenv.

## Run outputs

| File | Contents |
|---|---|
| `v2_shipped.json` | `VID_20260617_151857.mp4`, shipped config (conf 0.15, `unique_track`) → **111 counts**, plus all 111 counted events. |
| `v2_manuscript.json` | Same video, manuscript config (conf 0.50, `line_crossing`, min_hits 3) → **3 counts**. |
| `v1_shipped.json` | `VID_20260617_151331.mp4`, shipped config → **49 counts**. |
| `v1_manuscript.json` | Same video, manuscript config → **0 counts**. |
| `conf_sweep.json` | Full threshold sweep, val and test, raw and CLAHE. |

## Images

| File | What it shows |
|---|---|
| `counted_detections_audit_1of2.jpg`, `counted_detections_audit_2of2.jpg` | Every one of the 111 detections the shipped config counted on `VID_20260617_151857.mp4`, as labelled crops. 26 are on a fish; 85 are on wet pavement, slab joints, puddles or the pipe's outer wall. |
| `false_positives_empty_channel_frame1920.jpg` | Frame 1920: the channel is completely empty, yet three `fingerling` boxes are drawn on the surrounding pavement. |
| `true_detection_juvenile_frame1680.jpg` | Frame 1680: a correct `juvenile 0.82` on a real fish — alongside a `juvenile 0.27` false positive on the pavement in the same frame. |
| `video1_highest_confidence_detections.jpg` | The highest-confidence detections in `VID_20260617_151331.mp4`. The two strongest in the entire clip — `fingerling 0.79` and `fingerling 0.80` — are both background, which is why raising the confidence threshold alone does not fix the false positives. |
