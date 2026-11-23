# Manuscript review — *Olaiya (2026), Smartphone-Based Counting and Size-Sorting of African Catfish Fingerlings*

Reviewed against the repository as it stands on branch `dev` (`20af01e`), the shipped dataset
(`fish-fingerling.v1i.coco.zip`), the trained checkpoint (`models/best.pt`), the production
checkpoint (`models/best.onnx`), the training notebook, and the two supplied field videos.

Every claim below was checked by executing the code or reading the artefacts, not inferred from
the prose.

---

## 0. Executive summary

| Area | Verdict |
|---|---|
| **Detection metrics (Table 3)** | **Verified exactly.** The checkpoint's own stored metrics and an independent re-run reproduce P 0.811, R 0.782, mAP@0.5 0.821, mAP@0.5:0.95 0.479 and all three per-class rows. |
| **All statistics (§3.3, §3.4, Table 5)** | **Verified exactly.** Wilson intervals, paired *t*, Bland–Altman limits, Cochran–Armitage *z*, χ², the *r* = 0.943 correlation and the 3.5–4.6 % CVs all reproduce to the printed precision. |
| **Methods §2.5 (tracking, counting, logging)** | **Does not describe the code.** The tracker is not SORT, there is no Kalman filter, no IoU association, no direction gate, no majority vote, and the shipped configuration does not use the counting line at all. |
| **Table 2 (configuration)** | **Seven rows do not match `config/config.yaml` or the checkpoint's `train_args`.** |
| **Table 1 (dataset)** | **Wrong.** 332 images, not 330; class distribution 39.5 / 39.8 / 20.8 %, not 33.3 % each. |
| **"No false positives or double counts" (Table 4)** | **Not supportable on the supplied footage.** See §3. |
| **Sample test on supplied video** | Shipped config counts **111** fish in a clip containing one or two, and **49** in a clip that is essentially empty. The config the manuscript *describes* counts **3** and **0** on the same two clips. See §3. |

The paper's numbers are honest. The paper's *description of the system that produced them* is not,
and the gap is large enough that a reviewer who ran the code would notice. Most fixes are text
changes; six are small code changes.

---

## 1. Claims contradicted by the code

### 1.1 The tracker is not SORT — CRITICAL

> §2.5: "detections are passed to the Simple Online and Realtime Tracking algorithm (SORT; Bewley
> et al., 2016), which assigns each fish a persistent identity using a Kalman filter for motion
> prediction and the Hungarian algorithm for intersection-over-union association."

In `src/models/tracker.py`:

* **No Kalman filter exists anywhere in `src/`.** `filterpy` is installed but never imported.
  `Track.predict()` (lines 55–67) is a two-point constant-velocity extrapolation:
  `predicted = center + (history[-1] − history[-2])`.
* **Association is by Euclidean centroid distance, not IoU.** `_compute_cost_matrix()` builds a
  pixel-distance matrix; `_compute_iou()` is defined at line 208 and **never called**; the
  `iou_threshold = 0.3` constructor argument is stored and never read.
* The gate that actually rejects matches is `max_distance` (160 px in `config.yaml`, 100 px default).
* Hungarian assignment via `scipy.optimize.linear_sum_assignment` is correct.

**Suggested replacement text.** "Detections are associated frame-to-frame by a lightweight
SORT-style tracker (after Bewley et al., 2016): Hungarian assignment on Euclidean centroid distance,
with a constant-velocity motion prediction and a fixed gating radius of 160 px. Unlike SORT proper
it uses neither a Kalman filter nor IoU association; the simplification was acceptable because the
observation geometry keeps fish separated and slow-moving."

Table 2 must lose the row "Association IoU 0.30" and gain "Gating radius 160 px (centroid distance)".

### 1.2 The counting line and direction gate are not what runs — CRITICAL

> §2.5: "Counting is performed by a virtual line drawn horizontally across the mid-frame at y = 0.50
> … the count is incremented only when the centroid crosses the line in the downstream direction;
> upstream crossings are discarded."
> Table 2: "Line position y = 0.50", "Direction gate: Downstream only".

Three separate problems:

1. **`config/config.yaml` ships `counting.mode: "unique_track"`.** In that mode
   `FingerlingCounter._setup_counting_line()` (`src/app/counter.py:350–371`) never creates a line,
   the visualiser never draws one, and `FingerlingTracker._count_unique_tracks()`
   (`tracker.py:330–341`) increments the total the moment a track reaches `count_min_hits` = 2 —
   anywhere in the frame, moving in any direction, or not moving at all.
2. **Even in `line_crossing` mode there is no direction gate.** `_check_line_crossings()` fires on
   `prev < line <= curr` **or** `prev > line >= curr`, i.e. both directions.
   `track.get_direction()` is called on line 323 but its return value is discarded.
   Re-counting is prevented by a one-shot `track.counted` flag, not by direction.
3. Consequently "a fish that hesitates and re-crosses is not counted twice" holds for a *single*
   track, but when track identity is lost and re-acquired — which happens constantly on this
   footage — the fish is counted again under a new id.

**This is the most consequential discrepancy.** Measured on `VID_20260617_151857.mp4`
(102 s, 2 815 frames, every frame processed):

| Configuration | Total count |
|---|---|
| As shipped (`unique_track`, conf 0.15, min_hits 2) | **111** |
| As described in the manuscript (`line_crossing` @ y = 0.50, conf 0.50, min_hits 3) | **3** |
| Distinct fish actually visible in the clip | **1–2** |

Either change `config.yaml` to `line_crossing` and implement the direction gate, or change the
manuscript to describe `unique_track`. The former is strongly preferable — the manuscript's
described method is the better one, and it is 37× closer to the truth on this footage.

### 1.3 Majority-vote class assignment does not exist — CRITICAL

> §2.5: "The class label attached to each counted fish … is the modal label over all frames in which
> the track retained its identity, a majority vote that absorbs isolated misclassified frames."
> Table 2: "Class assignment: Majority vote over track".

`Track.update()` (`tracker.py:35–52`) overwrites `class_name` with the current frame's label on
every update. The label recorded at count time is whichever class the *most recent* matched
detection carried. A repository-wide search for `most_common`, `Counter(`, `vote` or `majority` in
`src/` returns nothing.

This matters because size sorting *is* the class assignment: with per-frame overwriting, a fish
whose class flickers is sorted by a coin flip on its last frame. In the video run the same physical
juvenile was recorded under all three class labels at different moments.

Either implement the vote (≈8 lines: keep a `Counter` on `Track`, update it in `update()`, read its
mode when counting) or remove the claim.

### 1.4 Table 2 inference and tracking values do not match `config.yaml`

| Table 2 row | Manuscript | `config/config.yaml` |
|---|---|---|
| Confidence threshold | 0.50 — *"Project config.yaml"* | **0.15** (`model.confidence_threshold`) |
| NMS IoU threshold | 0.50 | **0.45** (`model.iou_threshold`) |
| Min hits | 3 frames | **2** (`tracking.min_hits`; `counting.count_min_hits` also 2) |
| Max age | 30 frames | 30 ✓ |
| Association IoU | 0.30 | stored but unused — see §1.1 |
| Line position | y = 0.50 | 0.5 ✓ *but inactive in `unique_track` mode* |

The threshold citation is the awkward one, because it points explicitly at `config.yaml`.
Note that the *metrics* in Table 3 are consistent with a ≈0.50 operating point: re-evaluating at a
fixed conf = 0.50 with greedy IoU-0.5 matching gives P 0.815 / R 0.783 / F1 0.799 against the
paper's 0.812 / 0.782 / 0.797. **Table 3 is fine; it is the pointer to `config.yaml` that is wrong.**

### 1.5 "All errors were undercounts; no false positives or double counts" — CRITICAL

Table 4 footnote, restated in the abstract ("Every error was an undercount") and §3.4.

Three independent lines of evidence contradict this at the shipped configuration:

* **On the supplied video.** Of the 111 counted detections, a visual audit of every one finds
  **26 on an actual fish and 85 (77 %) on wet pavement, paving-slab joints, puddles and the outer
  wall of the pipe** — background outside the channel entirely. Counted boxes cluster at the frame
  margins (e.g. `[1735, 0, 1920, 396]`, `[0, 443, 263, 838]`), and the same static pavement patch at
  x ≈ 1850, y ≈ 155 is re-detected and re-counted at frames 278, 472, 581, 625, 726, 797, 838, 943 …
* **On the held-out validation images.** At the shipped conf 0.15 the detector predicts
  **197 boxes against 157 true instances (125.5 %)** — a net *over*count. It becomes net-unbiased
  only near conf 0.50 (151/157 = 96.2 %).
* **Double counts are structural.** Track identity is lost and re-acquired repeatedly, so the 26
  true-fish detections correspond to at most two individuals.

**Root cause, and the most actionable finding in this review: the dataset contains zero background
images.** All 332 images in all three splits carry at least one annotated fish (0 empty label files;
Ultralytics reports `0 backgrounds` on every split). The model was never shown a negative example,
so it has no representation of "not a fish". Ultralytics' own guidance is 0–10 % background images;
at 332 images that is 20–35 negatives.

**Recommended fix** (cheap, high return): photograph 30–50 frames of the empty rig, the surrounding
pavement, wet ground and the pipe exterior; add them with empty label files; retrain. Then the
"no false positives" claim can be re-tested rather than asserted.

Until then, narrow the claim to what the data support: *"Within the 156 scored passages, every
discrepancy from the reference was an undercount. False positives were not observed under the
controlled tank conditions of the validation rounds; §4.4 reports their appearance outside that
envelope."*

### 1.6 The CSV log does not contain what is claimed

> §2.5: "Each counted fish is written to a CSV log with a timestamp, class label and track
> identifier, which permits complete post-hoc reconstruction of any round."

`CSVLogger` (`src/streaming/server.py:718–765`) writes a **per-frame snapshot**, not a per-fish
event: `timestamp, frame, total, fingerling, post_fingerling, juvenile, unknown, fps`.
There is **no track-identifier column and no per-fish row**; `output/counts.csv` confirms it.
Per-fish post-hoc reconstruction is therefore impossible, and the "auditability through the CSV log"
argument in §4.3 rests on a capability the code does not have.

**Also a genuine bug:** line 738 writes the header with an escaped `\\n` inside a non-raw f-string,
so a literal backslash-n is emitted instead of a newline and the header runs into the first data
row. Visible in `output/counts.csv`:

```
timestamp,frame,total,fingerling,post_fingerling,juvenile,unknown,fps\n2026-05-12T11:31:02.248819,30,9,...
```

Fix: `f.write(f"timestamp,frame,total,{class_columns},fps\n")`.
Adding a real per-fish event log is ~10 lines and would make the §4.3 claim true.

### 1.7 The reported detection metrics were not measured on the deployed pipeline

`FingerlingDetector.detect()` calls `_preprocess()` by default, applying CLAHE (clipLimit 2.0,
8 × 8 tiles) in LAB space to **every frame before inference**;
`OnnxFingerlingDetector._preprocess()` applies the same CLAHE unconditionally, ignoring its own
`preprocess` flag. `FingerlingCounter` calls `detect(frame)` with the default, so **CLAHE is always
on in production**.

The model was trained without CLAHE and Table 3 was computed without it. Measured effect
(same weights, CPU, imgsz 640):

| Split | Preprocessing | P | R | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|---|
| val | raw *(as reported)* | 0.811 | 0.782 | 0.796 | 0.821 | 0.479 |
| val | **+ CLAHE (as deployed)** | 0.773 | **0.835** | 0.803 | **0.837** | 0.459 |
| test | raw | 0.871 | 0.761 | 0.813 | 0.832 | 0.451 |
| test | **+ CLAHE (as deployed)** | 0.877 | **0.832** | **0.854** | **0.870** | 0.470 |

Worth *adding* rather than hiding: CLAHE buys **+5.3 pp recall on val and +7.1 pp on test**, and
recall is exactly the axis on which the system loses fish. It costs precision and tighter-IoU
localisation. Report both rows and say which one the counting runs used.

### 1.8 Training hardware and hyperparameters

From `models/best.pt` → `train_args`, corroborated by
`notebooks/colab_fingerling_training_testing.ipynb`, which passes **only**
`data, epochs, batch, imgsz, device, project, name, exist_ok, workers` — everything else is an
Ultralytics default:

| Manuscript (Table 2 / §2.4) | Actual |
|---|---|
| "a single NVIDIA GTX 1650 GPU" | `project: /content/runs`, `name: fingerling_detector_colab`, `workers: 2` → **Google Colab**. Name the accelerator actually used. |
| "PyTorch 2.0" | checkpoint written by **Ultralytics 8.4.21**, 2026-03-14. State both versions. |
| "100 / patience 20" | epochs 100 ✓, but **`patience: 100`** — early stopping could not fire; all 100 epochs ran. |
| "SGD, momentum 0.937" | **`optimizer: 'auto'`** — Ultralytics selects the optimiser itself and explicitly *ignores* the `lr0` and `momentum` recorded in args. |
| "Initial LR 0.01 / cosine decay" | `lr0: 0.01`, `lrf: 0.01` recorded but overridden by `auto`; **`cos_lr: False`** → **linear** decay, not cosine. |
| Batch 16 / 640 × 640 / weight decay 5e-4 | ✓ ✓ ✓ (Ultralytics defaults) |

**Suggested replacement.** "Training used the Ultralytics defaults throughout: 100 epochs, batch 16,
640 × 640 input, weight decay 5 × 10⁻⁴, linear learning-rate decay, and `optimizer='auto'`, under
which Ultralytics selects the optimiser, initial learning rate and momentum automatically from the
dataset size. Early stopping was left at the default patience of 100 and therefore did not trigger."

This is a *better* sentence for reproducibility than the current one, because it is checkable.

### 1.9 The augmentation list is not what was applied

> §2.3: "Eight augmentations were applied to the training partition only — horizontal and vertical
> flip, ±15° rotation, ±25 % brightness, ±15 % exposure, Gaussian blur to 2.5 px, mosaic and cutout"

* The exported dataset contains **232 training images = exactly 70 % of the 332 source images**.
  Roboflow offline augmentation would have multiplied that (3× → 696). **No augmented copies were
  exported**, so these were not Roboflow-baked augmentations.
* The augmentations actually applied, from the checkpoint, are the Ultralytics on-the-fly defaults:
  `hsv_h 0.015, hsv_s 0.7, hsv_v 0.4, translate 0.1, scale 0.5, fliplr 0.5, mosaic 1.0,
  erasing 0.4, close_mosaic 10`.
* Critically, **`degrees: 0.0`** (no rotation) and **`flipud: 0.0`** (no vertical flip) — two of the
  eight listed augmentations were *not* applied, and neither was Gaussian blur.

Replace the list with the checkpoint values. Since fish appear at any orientation in the channel,
the absence of rotation and vertical flip is also a concrete improvement lead for §5(ii).

### 1.10 Table 1 (dataset composition) is wrong

Counted directly from `_annotations.coco.json` in the shipped Roboflow export:

| | train | valid | test | **total** |
|---|---|---|---|---|
| Images | 232 | 66 | 34 | **332** |
| Annotated instances | 550 | 157 | 62 | **769** |
| — fingerling | 284 | 90 | 21 | **395** |
| — post-fingerling | 202 | 48 | 28 | **278** |
| — juvenile | 64 | 19 | 13 | **96** |

Against Table 1 as printed (110 / 110 / 110 images, 33.3 % each, 330 total):

* **332 images, not 330**; split **232 / 66 / 34**, not 231 / 66 / 33.
* The dataset is **not balanced**. By instances: 51.4 / 36.2 / 12.5 %. By dominant class per image:
  131 / 132 / 69 → 39.5 / 39.8 / 20.8 %. Juvenile is under-represented roughly 2 : 1.
* The column should be labelled **instances**, since most images contain several fish; an
  images-per-class column is ambiguous when an image holds a mixed group.

**This correction helps the paper.** §3.2 and §4.2 argue that fingerlings score worst because of
pixel support and occlusion, not data volume. With Table 1 as printed (perfectly balanced) that
argument is unfalsifiable; with the real distribution it is *demonstrated* — juvenile has the fewest
instances (96) and the best metrics (F1 0.936), so the size effect cannot be a data-quantity effect.
Say that explicitly.

### 1.11 Report the instance counts behind the per-class metrics

Juvenile F1 = 0.936 and mAP@0.5 = 0.961 rest on **19 instances in 13 images** — a very thin estimate
with a wide interval. Add an "Instances" column to Table 3 (fingerling 90, post-fingerling 48,
juvenile 19) so the reader can weight the rows.

### 1.12 The observation window is not glazed

> §2.2: "A section of the pipe was opened and glazed to form a transparent observation window."

The supplied footage shows a **PVC pipe with a rectangular window cut in the top and no glazing** —
an open channel viewed from directly above, water surface exposed to air. This is what the Fig. 1
caption already says ("open-channel observation cross-section"), so §2.2 contradicts the figure it
cites.

Remove "glazed", "transparent observation window" and "through a glazed channel"; and in §4.2
re-attribute "surface disturbance and refraction" to the free air–water surface rather than a window.

### 1.13 Equation (4) uses the wrong cross-section

Eq. (4) `A = bh = 0.10 × 0.05 = 0.005 m²` is the area of a **rectangular** channel. The footage shows
a **round pipe with the top cut away**, so the wetted section is a circular segment. For a 100 mm ID
pipe at 50 mm depth: `A = πr²/2 = 0.00393 m²`. **`b·h` overstates the true flow area by 27 %.**

Either state that the observation section is a rectangular flume (and show it in Fig. 1 Detail A),
or replace Eq. (4) with the circular-segment form `A = r²(θ − sin θ)/2`, `θ = 2·arccos((r − h)/r)`.

Equations (1)–(3) are all arithmetically correct (10.0 L, 13.25 L, 2452.5 Pa).

### 1.14 The flow rate is inconsistent with the stated head

> §2.6: "continuous flow at approximately 0.5 L min⁻¹"; §2.2 Eq. (3): 2.45 kPa, "sufficient for a
> gentle gravity discharge".

* Free gravity discharge at H = 0.25 m gives `v = √(2gH) = 2.21 m s⁻¹`. Through even a 20 mm pipe
  (Cd 0.62) that is **≈26 L min⁻¹**; through a 100 mm pipe, **≈650 L min⁻¹**. 0.5 L min⁻¹ is two to
  three orders of magnitude lower, so the flow must have been **throttled** — by a valve or a
  part-open tap the Methods does not mention. Add it; it is part of the reproducible protocol.
* At 0.5 L min⁻¹ over A = 0.005 m² the mean velocity is **1.7 mm s⁻¹**, and moving 10 L takes
  **20 minutes** — inconsistent with "a population typically cleared within five to eight minutes"
  and with the 10-minute round ceiling.
* More seriously, 1.7 mm s⁻¹ is far below any velocity that would produce the strong station-holding
  rheotaxis described in §3.1, which is the paper's headline behavioural finding. Either the figure
  is a typo (5 L min⁻¹ gives 17 mm s⁻¹ and a 2-minute transfer, which fits the narrative), or the
  relevant velocity is the local one at the constricted pipe inlet rather than the channel mean.

Re-check the number, say how it was measured (timed volume? rotameter?), and if the rheotaxis
argument depends on velocity, report the velocity at the point the fish experienced it.

### 1.15 "Real-time" needs qualifying

§1 motivates YOLO by "real-time throughput"; §2.5 describes "a real-time interface". Measured
CPU-only on an Intel i5-6300U (2 C / 4 T) — the class of machine a smallholder, or a free-tier host,
would actually use:

| Backend | Input | Mean latency | p95 | Throughput |
|---|---|---|---|---|
| PyTorch / Ultralytics | val images | 193.2 ms | 221.3 ms | 5.2 FPS |
| ONNX Runtime | val images | 141.8 ms | 168.4 ms | 7.1 FPS |
| PyTorch / Ultralytics | 1080p video frames | 124.5 ms | 142.1 ms | 8.0 FPS |
| ONNX Runtime | 1080p video frames | 150.0 ms | 175.1 ms | 6.7 FPS |

The source video is 27.6 FPS. **Without a GPU the system runs at roughly a quarter of real time.**

This is not merely a wording issue — it is an unreported contributor to the undercount. At 6 FPS the
inter-frame interval is 167 ms; a fish crossing the counting line faster than that is never seen in
two consecutive frames and cannot trigger a crossing. Add it to the §3.5 error taxonomy as a fourth
mechanism, and qualify "real-time" as "real-time on GPU; 5–8 FPS on CPU".

### 1.16 Model complexity figures are for the COCO model

> §2.4: "approximately 3.2 million parameters and 8.7 GFLOPs at 640 × 640"

Those are the 80-class COCO YOLOv8n. The trained 3-class model has **3 011 433 parameters and
8.20 GFLOPs** (3 006 233 / 8.1 GFLOPs after fusion). Quote the model actually trained.

### 1.17 The production backend is not the benchmarked one

The deployed service loads `models/best.onnx` (`counter.py:154–168`; `requirements-prod.txt`
contains `onnxruntime` but neither `torch` nor `ultralytics`). With CLAHE applied on both sides over
the 66 validation images, the ONNX path returns **224 detections vs the PyTorch path's 233
(−3.9 %; 18 of 66 images differ, max per-image difference 2)**, from letterbox and NMS implementation
differences. All reported metrics come from the PyTorch path. Either state that, or re-run Table 3
through the ONNX path.

---

## 2. Verified correct — do not change these

### 2.1 Detection metrics (Table 3)

The checkpoint's own stored `train_metrics` are
`precision 0.81152, recall 0.78199, mAP50 0.82158, mAP50-95 0.47995`. An independent re-run of
`model.val()` on the 66-image validation split reproduces every row:

| Class | Instances | P | R | F1 | mAP@0.5 | mAP@0.5:0.95 | Paper |
|---|---|---|---|---|---|---|---|
| Fingerling | 90 | 0.755 | 0.711 | 0.732 | 0.727 | 0.377 | 0.756 / 0.711 / 0.733 / 0.727 / 0.378 ✓ |
| Post-fingerling | 48 | 0.751 | 0.688 | 0.718 | 0.778 | 0.435 | 0.754 / 0.688 / 0.719 / 0.777 / 0.433 ✓ |
| Juvenile | 19 | 0.926 | 0.947 | 0.937 | 0.960 | 0.625 | 0.926 / 0.947 / 0.936 / 0.961 / 0.627 ✓ |
| **Overall** | **157** | **0.811** | **0.782** | **0.796** | **0.821** | **0.479** | 0.812 / 0.782 / 0.797 / 0.822 / 0.479 ✓ |

Differences ≤ 0.002 are rounding. **Table 3 is sound**, and "66 images, 157 instances" is exact.

One clarification to add: Ultralytics reports P and R at the maximum-F1 point of the PR curve, so
F1 = 2PR/(P+R) from those values is self-consistent — worth a footnote, since a reader computing F1
at a fixed conf = 0.50 will get a slightly different number.

### 2.2 Every statistic reproduces

| Quantity | Manuscript | Recomputed |
|---|---|---|
| Aggregate accuracy | 86.54 % (135/156) | 86.538 % ✓ |
| Wilson 95 % CI, overall | 80.3 – 91.0 | 80.3 – 91.0 ✓ |
| Wilson CI, fingerling | 72.0 – 90.7 | 72.0 – 90.7 ✓ |
| Wilson CI, post-fingerling | 75.6 – 93.6 | 75.6 – 93.6 ✓ |
| Wilson CI, juvenile | 77.9 – 96.2 | 77.9 – 96.2 ✓ |
| Mean bias | +2.33 fish/round (SD 1.00) | 2.3333, SD 1.0000 ✓ |
| Paired *t* | t = 7.00, df = 8, p = 0.00011 | t = 7.0000, df = 8, p = 0.000113 ✓ |
| Bland–Altman 95 % limits | +0.37 to +4.29 | +0.373 to +4.293 ✓ |
| Mean relative undercount | 13.1 % (SD 4.3) | 13.051 %, SD 4.299 ✓ |
| Cochran–Armitage | z = 1.048, p = 0.294 | z = 1.0484, p = 0.2945 ✓ |
| χ² homogeneity | 1.100, df 2, p = 0.577 | 1.0997, df 2, p = 0.5770 ✓ |
| mAP vs accuracy correlation | r = 0.943, p = 0.217 | r = 0.9424, p = 0.2172 ✓ |
| Within-class CV | 3.5 – 4.6 % | 3.46 / 3.69 / 4.56 % ✓ |

The statistical work is careful and correctly reported, including the appropriately cautious reading
of the size gradient. Wilson over the normal approximation, and Bland–Altman over accuracy alone,
are both the right choices.

### 2.3 One methodological note on the Wilson interval

The Wilson interval on 135/156 treats the passages as 156 independent Bernoulli trials. They are
not: the same 20 / 18 / 14 individuals were re-used across the three rounds of their class, and fish
within a round share water, light, clustering and operator state. The effective independent unit is
closer to **9 rounds** (or 52 fish) than 156 trials — a pseudoreplication concern for
*generalisation*.

Reassuringly, it does not inflate the reported precision. A cluster bootstrap resampling the nine
rounds (200 000 draws) gives **84.1 – 89.2 %**, *narrower* than the Wilson interval, because
between-round variance is small (round accuracies 85.0, 80.0, 85.0, 88.9, 83.3, 88.9, 92.9, 85.7,
92.9; SD 4.3 pp). So the Wilson interval is conservative here.

Suggested addition to §2.8 or §4.4: *"The Wilson interval treats the 156 passages as independent;
because the same individuals were re-used across rounds, the effective independent sample is the
nine rounds. A cluster bootstrap over rounds gives 84.1–89.2 %, so the reported interval is
conservative rather than optimistic, but generalisation is limited by the nine rounds, not by the
156 passages."*

### 2.4 Also verified

* Equations (1)–(3): 10.0 L, 13.25 L, 2452.5 Pa — all exact.
* Flask on TCP port 5000 (`streaming.port: 5000`).
* Class names and label mapping are consistent end-to-end: COCO ids 1/2/3 → YOLO 0/1/2 →
  `{0: fingerling, 1: post_fingerling, 2: juvenile}`, with instance counts matching on both sides
  (284 / 202 / 64 in train). No off-by-one in the class remap.
* Model: YOLOv8n (`model: yolov8n.pt` in `train_args`), 100 epochs, batch 16, 640 × 640,
  weight decay 5 × 10⁻⁴.
* Validation partition: 66 images, 157 instances — exact.

---

## 3. Sample test on the supplied footage

**Videos.** `VID_20260617_151331.mp4` (1920 × 1080, 26.8 FPS, 2 294 frames, 85.6 s) and
`VID_20260617_151857.mp4` (1920 × 1080, 27.6 FPS, 2 815 frames, 102.1 s). Both show the open-topped
PVC channel from above, handheld, panning along the pipe. They are **rig demonstrations, not
validation rounds**: the channel is empty for most of the runtime and never holds more than one or
two fish.

**Method.** The shipped pipeline was replicated exactly — same detector weights, same
`FingerlingTracker` class, parameters read from `config/config.yaml` — and run over every frame at
stride 1. Every counted event was recorded with its frame, track id, class and bounding box, and
each was then reviewed visually as an image crop.

### 3.1 Results, both videos, both configurations

**`VID_20260617_151857.mp4`** — one or two fish visibly transit the channel.

| | Shipped `config.yaml` | Manuscript §2.5 description |
|---|---|---|
| conf / NMS IoU | 0.15 / 0.45 | 0.50 / 0.45 |
| Counting mode | `unique_track`, count_min_hits 2 | `line_crossing` @ y = 0.50, min_hits 3 |
| Frames processed | 2 815 | 2 815 |
| Total detections | 2 514 | 206 |
| Frames with ≥ 1 detection | 1 861 (66 %) | 197 (7 %) |
| Tracks created | 140 | 49 |
| **Reported count** | **111** (juv 57 / fing 47 / post 7) | **3** (all juvenile) |
| True fish in clip | **1–2** | **1–2** |

**`VID_20260617_151331.mp4`** — effectively a negative control: the channel is empty for almost the
entire clip, with a single juvenile visible around frame 2100.

| | Shipped `config.yaml` | Manuscript §2.5 description |
|---|---|---|
| Frames processed | 2 294 | 2 294 |
| Total detections | 437 | 66 |
| Tracks created | 90 | 15 |
| **Reported count** | **49** (fing 31 / juv 16 / post 2) | **0** |
| True fish transiting | **≈ 0–1** | **≈ 0–1** |

The manuscript's own described configuration gets this clip **exactly right (0)**; the shipped
configuration reports 49 phantom fish.

**A nuance that matters for the fix.** Raising the confidence threshold alone does *not* remove the
background false positives — in this clip the two highest-confidence detections in the whole video
are `fingerling 0.79` on a paving-slab joint (frame 1560) and `fingerling 0.80` on the dark shadow
at the pipe's cut edge (frame 1890), both well above 0.50
(`docs/review_artifacts/video1_highest_confidence_detections.jpg`). What suppresses them is the
**line-crossing requirement**: the false positives are on static background and never cross the
counting line, whereas a transiting fish does. This is a mechanistic argument for keeping the
counting-line design that the manuscript describes, and it is worth stating in §4.2 — direction-gated
line crossing is not merely a de-duplication device, it is also the system's only working defence
against static background false positives.

### 3.2 Audit of all 111 counted detections

Every counted crop was inspected. **26 are on a real fish; 85 (77 %) are on background** — wet
paving slabs, the joints between them, puddles, and the outer wall of the pipe. The false positives
concentrate at the left and right frame margins, outside the channel entirely, and the same
stationary pavement texture is re-detected and re-counted every few dozen frames as track identity
is dropped and re-established.

The 26 true-fish detections are not 26 fish. They are the same one or two individuals, re-acquired
under a new track id each time the fish leaves and re-enters the field of view as the camera pans.

### 3.3 What this does and does not show

It does **not** invalidate the 86.5 % figure. That came from controlled tank rounds where the camera
was fixed over the channel and the frame was filled by the rig; these videos are handheld, pan
across unrelated background, and were evidently shot to document the apparatus.

It does show three things the manuscript should acknowledge:

1. **The shipped configuration is not the validated configuration** — 111 vs 3, and 49 vs 0, on
   identical input. Whatever produced Table 4, it was not the configuration in `config.yaml`.
2. **Out-of-channel background is a live failure mode**, following directly from a dataset with no
   negative examples. Any deployment where the camera sees anything but the channel over-counts badly.
3. **Track fragmentation causes double counting**, contradicting the "no double counts" claim and
   partly offsetting the undercount — two errors of opposite sign that round-level totals cannot
   separate.

**Recommendation.** Add a short §3.6, "Behaviour outside the validated envelope", reporting exactly
this. It is a *strength*, not a weakness: it shows the system was tested beyond the conditions that
flattered it, it motivates recommendations (i) and (iv) far more concretely than the current text,
and it pre-empts the first thing a reviewer with repository access would find.

---

## 4. Benchmarks worth adding to the paper

All on the shipped weights; CPU-only (i5-6300U), Ultralytics 8.4.21, imgsz 640.

### 4.1 The held-out test split has never been reported

`best.pt` was selected by fitness **on the validation split**, so Table 3 is a model-selection score,
not a clean generalisation estimate. The 34-image / 62-instance test split has been sitting unused in
the repository. Reporting it is the cheapest available improvement to the paper's rigour:

| Split | Role | P | R | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|---|
| val (66 img, 157 inst) | model selection — *reported* | 0.811 | 0.782 | 0.796 | 0.821 | 0.479 |
| **test (34 img, 62 inst)** | **held out — never reported** | **0.871** | **0.761** | **0.813** | **0.832** | **0.451** |

Per class on test: fingerling P 0.886 / R 0.741 / mAP50 0.768; post-fingerling 0.867 / 0.697 / 0.798;
juvenile 0.861 / 0.846 / 0.929.

The test result is *slightly better* than validation — the model is not overfitted to the selection
split. This converts "mAP@0.5 = 0.822 on validation" into a defensible generalisation claim.

### 4.2 Counting error metrics the paper's own §5 asks for

§5 recommends future work "reporting MAE, RMSE and MAPE alongside agreement statistics". These can
be computed today at the image level, on data already in the repository — predicted box count vs
annotated instance count per image:

| Split | Preproc. | conf | P | R | F1 | count MAE | RMSE | bias | MAPE | Σpred/Σtrue |
|---|---|---|---|---|---|---|---|---|---|---|
| val | raw | **0.15** *(shipped)* | 0.680 | 0.854 | 0.757 | 0.91 | 2.06 | **+0.61** | 32.2 % | **125.5 %** |
| val | raw | 0.25 | 0.714 | 0.828 | 0.767 | 0.74 | 1.75 | +0.38 | 26.0 % | 115.9 % |
| val | raw | 0.35 | 0.760 | 0.809 | 0.784 | 0.76 | 1.71 | +0.15 | 23.4 % | 106.4 % |
| val | raw | **0.50** *(manuscript)* | 0.815 | 0.783 | **0.799** | **0.67** | **1.58** | **−0.09** | **18.1 %** | **96.2 %** |
| val | CLAHE | 0.50 | 0.761 | 0.790 | 0.775 | 0.64 | 1.44 | +0.09 | 20.0 % | 103.8 % |
| test | raw | 0.15 | 0.750 | 0.823 | 0.785 | 0.35 | 0.73 | +0.18 | 18.0 % | 109.7 % |
| test | raw | **0.35** | 0.877 | 0.806 | **0.840** | **0.21** | **0.51** | −0.15 | **6.8 %** | 91.9 % |
| test | raw | 0.50 | 0.906 | 0.774 | 0.835 | 0.27 | 0.66 | −0.27 | 8.1 % | 85.5 % |
| test | CLAHE | 0.35 | 0.841 | 0.855 | **0.848** | 0.38 | 0.75 | **+0.03** | 18.2 % | **101.6 %** |

Three results follow, all of which the paper would want:

* **conf = 0.50 is close to count-unbiased on validation** (96.2 % of true instances recovered),
  and conf 0.15 over-counts by 25.5 %. This independently corroborates that the Table 4 rounds ran
  at ≈0.50, and confirms that `config.yaml`'s 0.15 is a regression rather than the validated setting.
* **The optimal threshold differs between splits and between metrics** — F1 peaks at 0.50 on val and
  0.35 on test; count bias crosses zero near 0.45 on val and 0.30 on test. This is direct evidence
  for the paper's own recommendation (ii), and it shows that *the threshold that maximises F1 is not
  the threshold that minimises counting error* — worth stating explicitly, since counting is the task.
* **CLAHE + conf 0.35 on test gives the best count-unbiasedness of any setting tested**
  (bias +0.03, Σpred/Σtrue = 101.6 %).

### 4.3 Runtime and deployability

See the table in §1.15. Add it to §4.3, where the paper compares against commercial counters on
cost — throughput is the other axis on which that comparison should be made, and 5–8 FPS on CPU
against a commercial channel counter's continuous operation is a real limitation the cost argument
currently obscures.

### 4.4 Backend parity

PyTorch vs ONNX Runtime, CLAHE on both sides, 66 validation images: **233 vs 224 detections
(−3.9 %), 18 of 66 images differ, max per-image difference 2.** Worth one sentence in §2.5 or a
declaration under Data and Code Availability, since the deployed artefact is the ONNX one.

---

## 5. Prioritised actions

**Code — do these first; they are small and they change what the paper can claim**

1. `config/config.yaml`: set `counting.mode: "line_crossing"`, `confidence_threshold: 0.50`,
   `iou_threshold: 0.50`, `min_hits: 3`, `count_min_hits: 3` — make the shipped configuration the
   validated one. (Turns 111 into 3 on one supplied video and 49 into 0 on the other.)
2. `tracker.py::_check_line_crossings()`: implement the direction gate the paper describes — count
   only `prev < line <= curr` (downstream), discard the reverse.
3. `tracker.py`: add a `collections.Counter` to `Track`, update it in `update()`, read its mode at
   count time — the majority vote of §2.5.
4. `server.py:738`: fix the escaped `\\n` in the CSV header.
5. `server.py`: add a per-fish event log (`timestamp, track_id, class, frame, bbox`) so the §4.3
   auditability claim becomes true.
6. Add 30–50 background images with empty labels and retrain — the fix for §1.5.

**Manuscript — must change (factually wrong)**

7. §2.5 + Table 2: rewrite the tracker description (§1.1), counting logic (§1.2) and class
   assignment (§1.3); correct the four Table 2 values in §1.4.
8. Table 1 + §2.3: correct to 332 images / 769 instances and the real class distribution (§1.10);
   correct the augmentation list (§1.9).
9. §2.4 + Table 2: correct the training hardware, patience, optimiser and LR schedule (§1.8), and
   the parameter / GFLOP count (§1.16).
10. §2.5: correct the CSV description (§1.6).
11. Table 4 footnote + abstract: narrow the "no false positives, no double counts" claim (§1.5).
12. §2.2 + §4.2: remove "glazed / transparent window" (§1.12).
13. §2.2 Eq. (4): fix the cross-section, or state that the channel is rectangular (§1.13).
14. §2.6 + §2.2: reconcile 0.5 L min⁻¹ with the head and the clearing time, and state how flow was
    regulated and measured (§1.14).

**Manuscript — should add (strengthens the paper)**

15. Report the held-out test split (§4.1).
16. Report the CLAHE / no-CLAHE comparison and state which was used for Table 3 (§1.7).
17. Add the image-level MAE / RMSE / MAPE table and threshold sweep (§4.2) — this delivers, in the
    present paper, what §5 currently defers to future work.
18. Add CPU throughput and qualify "real-time" (§1.15); add frame-rate-limited misses as a fourth
    error mechanism in §3.5.
19. Add an instances column to Table 3 (§1.11).
20. Add §3.6 on behaviour outside the validated envelope, using the video result (§3.3).
21. Add the pseudoreplication note and cluster bootstrap to §2.8 / §4.4 (§2.3).
22. Declare the ONNX / PyTorch divergence (§4.4).
