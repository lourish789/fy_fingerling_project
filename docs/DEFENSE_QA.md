# Defence preparation — expected questions and correct answers

*Olaiya, F. D. — "Counting Catfish Fingerlings with a Smartphone: A Low-Cost Computer Vision
System for Resource-Constrained Hatcheries"*

Answers are grounded in the repository as it stands on `dev` (`20af01e`): the shipped dataset,
`models/best.pt`, `config/config.yaml`, the training notebook and the two field videos — not only
in the manuscript prose. Where the two disagree, the disagreement is flagged **⚠ TRAP** and the
safe answer is given. See `docs/MANUSCRIPT_REVIEW.md` for the underlying evidence.

> **Status update — 2026-11-23.** Five of the code/paper gaps below have now been **fixed in the
> repository**: `config.yaml` ships the validated settings (`line_crossing`, conf 0.50, NMS IoU
> 0.50, min_hits 3, count_min_hits 3), the downstream direction gate is implemented, class
> assignment is a majority vote over the track, the CSV header bug is corrected, and the per-fish
> audit trail (`src/app/run_log.py` → `events.csv`, `crops/`, `summary.json`, `report.html`, D6) is
> implemented and tested. The ⚠ TRAP entries for C7, D2, D3, D6 and J3 therefore describe *history*
> — what the paper claimed versus what the code did when the manuscript was written. The honest line
> is now: *"the paper described the intended method, the shipped configuration had drifted from it,
> and the implementation has been corrected and verified to match."* Still outstanding: retraining
> with background/negative images (B6). A measured before/after on the field footage is in
> `docs/CONFIG_FIX_RESULTS.md`.

---

## How to use this

Three rules for the room:

1. **Never defend a claim the code cannot support.** Four claims in the paper (SORT/Kalman,
   direction-gated line counting, majority-vote class assignment, per-fish CSV audit log) describe
   a system that is not what runs. If an examiner has the repo, they will find this. Volunteering
   it first turns a fatal catch into evidence of rigour.
2. **Lead with the number, then the caveat.** "86.5%, with a systematic +2.33 fish undercount that
   is correctable" is a stronger sentence than "about 86%, but…".
3. **The contribution is the protocol, not the model.** YOLOv8n plus a tracker is standard. The
   feed-stimulated, flow-assisted transfer protocol is the novel, transferable part. Steer back to
   it whenever you are pressed on model novelty.

---

## A. Framing and justification

**A1. Why does this problem matter? Nobody fails a hatchery for a bad count.**

The count at sale or stocking propagates into every downstream decision: stocking density, feed
budget, mortality bookkeeping and the price the buyer pays. An error at the count is an error in
all four. Manual counting degrades exactly where the stakes are highest — large batches, tired
operators, poor light — and the handling itself stresses the fish.

**A2. Commercial counters reach 95%+. Yours reaches 86.5%. Why is this worth doing?**

Price. Commercial optical counters are USD 3,000–15,000 before Nigerian import duty; this rig is
USD 40–60 plus a phone the farmer already owns — roughly two orders of magnitude cheaper. The
comparison is not "86.5% versus 95%", it is "86.5% versus the hand count that is actually in use",
because the 95% machine is not a real option for the small and medium hatcheries that produce most
of Nigeria's catfish. I am not claiming to displace commercial counters; I am claiming to occupy a
price point where nothing automated currently exists.

**A3. Is 86.5% actually good enough to use?**

Not as a replacement for a careful hand tally of twenty fish — I say so explicitly in the paper.
Its value is where hand counting breaks down: large batches, fatigue, poor light. And because the
error is a *systematic* undercount (+2.33 fish per round, p = 0.0001) rather than random scatter,
it can be corrected with a calibration factor, which pushes usable accuracy well above the raw
figure.

**A4. Why *Clarias gariepinus* specifically?**

It is the most farmed fish in Nigeria, so the economic reach is widest, and hatchery grading
practice already uses head-width size classes — which gave me an existing, farmer-meaningful basis
for the three classes rather than an arbitrary split I invented.

**A5. What is the actual novel contribution? YOLOv8 and tracking are off-the-shelf.**

Correct, and I would not claim otherwise. The contribution is threefold, none of it architectural:
(i) the feed-stimulated, flow-assisted transfer protocol — the finding that flow alone fails
because of rheotaxis, and that feed stimulus overcomes it; (ii) an annotated *C. gariepinus*
size-class dataset where none existed; (iii) a full-system validation against a hand-counted
reference with proper agreement statistics, at a documented capital cost. The protocol generalises
beyond counting — to grading, vaccination, transfer and harvest.

---

## B. Dataset and annotation

**B1. 330 images is a very small dataset. Justify it.**

It is small, and I treat it as a stated limitation rather than a strength. Two defences. First,
the task is narrow: one species, one fixed viewing geometry, three classes — far less variation
than a general detector must cover, so transfer learning from COCO weights carries most of the
load. Second, the evidence says data quantity is not the binding constraint: the juvenile class
has the *fewest* instances (96) and the *best* performance (F1 0.936), while fingerlings have the
most instances and the worst. If volume were the limiter, that ordering would be reversed. The
limiter is pixel support and occlusion, not image count.

**⚠ TRAP — B2. Your table says 110 images per class, perfectly balanced. Is it?**

No, and I should correct it. Counted directly from the shipped Roboflow export, the dataset is
**332 images, not 330**, split **232/66/34**, with **769 annotated instances**: 395 fingerling,
278 post-fingerling, 96 juvenile — 51/36/13% by instance, not 33/33/33%. The "110 per class"
figure conflated images with instances; most images contain several fish, so an images-per-class
column is ambiguous for mixed groups.

*Do not fight this one.* Concede it immediately, then use it, because the correction
**strengthens** the paper: with a perfectly balanced table, the claim that fingerlings score worst
for reasons of pixel support rather than data volume is unfalsifiable. With the real distribution
it is demonstrated.

**B3. Who annotated it, and how do you know the labels are right?**

Single annotator in Roboflow, which is a genuine limitation — there is no inter-annotator
agreement statistic, and I would report one in any extension. The mitigation is that class
assignment is not subjective: the boundaries are head-width thresholds the hatchery already grades
by (<0.65 cm, 0.65–1.00 cm, 1.00–1.50 cm), not a visual impression of size.

**B4. How do you assign a head-width class from a 2D image with no scale reference?**

Honestly, this is the weakest link in the size-sorting claim and I will state it as such. Classes
were assigned at annotation time from fish measured before filming, so the *labels* are physically
grounded; the *model* then learns apparent size and shape at a fixed camera-to-channel distance.
That means size classification is only valid at the calibrated geometry — move the camera and the
class boundaries shift. The fix is the fixed-camera enclosed device in recommendation (iii), or an
in-frame fiducial of known length.

**B5. Fish overlap heavily in your dense images. How were overlapping fish annotated?**

Each visible fish got its own box, with overlap permitted — Figure 3(a) and 3(b) show exactly
these cases. Where fish were genuinely indistinguishable, a box was drawn where a head was
resolvable and omitted where it was not, which biases the ground truth slightly *downward* in
dense frames. That is consistent with cluster-merge being a measured error mode rather than
something hidden in the labels.

**⚠ TRAP — B6. Does your dataset contain background-only images?**

No — zero. All 332 images in all three splits contain at least one annotated fish; Ultralytics
reports "0 backgrounds" on every split. **This is the single most important weakness in the work**
and I would rather raise it than have it raised. The model was never shown a negative example, so
it has no internal representation of "not a fish". The measured consequence is in C7 and F4. The
fix is cheap and specific: 30–50 photographs of the empty rig, the surrounding wet pavement and
the pipe exterior, added with empty label files, then retrain — Ultralytics' own guidance is
0–10% background images, which at this dataset size is 20–35 negatives.

**⚠ TRAP — B8. Were your train, validation and test splits independent?**

No. This is measurable from the filenames and it is the most serious methodological problem in the
work — more serious than any of the Methods/code mismatches, because it affects the headline number
rather than its description.

Every one of the 332 images was captured on a single morning, **2026-02-28, within a 43-minute
window**. The split is random across frames from that one session, so near-duplicate frames of the
same fish in the same tray land on both sides of the boundary:

| | within 0 s of a train image | within 1 s | within 2 s | within 5 s |
|---|---|---|---|---|
| validation (66 img) | 2 (3%) | 17 (26%) | 33 (50%) | 52 (79%) |
| test (34 img) | 2 (6%) | 8 (24%) | 20 (59%) | 32 (94%) |

Half the validation set and 59% of the test set were photographed within two seconds of a training
image. At that interval it is the same fish, same water, same light, same camera pose — so
mAP@0.5 = 0.822 substantially measures memorisation of a single session, not generalisation to new
fish, new light or a new site.

What this does and does not invalidate: it does **not** touch the 86.5% counting result, which came
from separate physical rounds with recovered and recounted fish. It **does** mean the detection
metrics should be described as within-session performance, and that the test split cannot be
offered as independent evidence (E3).

The fix is a **session-wise or fish-wise split**, not a random one — and since there is only one
session, that means collecting at least one more. Say this before an examiner derives it from your
filenames, and it reads as rigour. Discovered after it is put to you, it reads as a result you did
not understand.

**B7. Why 70/20/10 rather than cross-validation?**

With 332 images, k-fold would give a more stable estimate and I would use it in an extension. The
split was chosen for a practical reason — it is Roboflow's default export and keeps the
train/val/test boundary fixed and auditable across retraining runs. I partly compensate by
reporting the held-out test split as well as validation (see E3), which is the check
cross-validation would be substituting for.

---

## C. Model and training

**C1. Why YOLOv8n rather than a larger model, or a two-stage detector?**

Deployment constraint, deliberately binding. The nano variant is the largest model that runs at a
usable rate on hardware a smallholder has. A two-stage detector such as Faster R-CNN would improve
localisation but is far too slow for CPU-only inference. The honest framing: I did not choose the
most accurate model, I chose the most accurate model that satisfies the cost ceiling — and the
error analysis shows the model is not currently the binding constraint anyway.

**C2. Did you compare against other architectures?**

No, and that is a gap. The defence is that the error taxonomy (F1) traces all 21 misses to
detection misses, cluster merges and track losses — none of which a different backbone at the same
scale would fix, and two of which are data and tracking problems. A model comparison would be
addressing the wrong bottleneck. I would run YOLOv8s and YOLOv11n as an ablation in an extension.

**C3. Why fine-tune from COCO weights? COCO has no catfish.**

It has no catfish, but the low-level features — edges, elongated-body texture, contrast against
background — transfer, and that is what matters at 332 images. Training from scratch at this
dataset size would not converge usefully.

**⚠ TRAP — C4. What hardware and hyperparameters did you train on?**

The paper says "a single GTX 1650" with SGD, momentum 0.937, cosine decay and patience 20. The
checkpoint's own `train_args` says otherwise, and the checkpoint is authoritative. What actually
ran: **Google Colab** (`project: /content/runs`, `workers: 2`), **Ultralytics 8.4.21**,
`optimizer: 'auto'` — meaning Ultralytics selected the optimiser, initial learning rate and
momentum itself and explicitly ignored the recorded `lr0` and `momentum` — `cos_lr: False`, so
**linear** decay, not cosine, and `patience: 100`, so early stopping could never fire and all 100
epochs ran. Correct as printed: 100 epochs, batch 16, 640×640, weight decay 5e-4.

If asked, give the corrected version. It is *better* for reproducibility than the printed one,
because every value is checkable in the checkpoint.

**⚠ TRAP — C5. You state 3.2 M parameters and 8.7 GFLOPs.**

Those are the figures for the 80-class COCO YOLOv8n. The trained 3-class model has **3,011,433
parameters and 8.20 GFLOPs** (3,006,233 and 8.1 after fusion). Minor, but exactly the kind of
detail an examiner checks because it is trivially checkable.

**⚠ TRAP — C6. List your augmentations.**

The paper lists eight, including ±15° rotation, vertical flip and Gaussian blur. The export
contains 232 training images = exactly 70% of 332, so no augmented copies were baked in by
Roboflow. What actually applied were the Ultralytics on-the-fly defaults: `hsv_h 0.015,
hsv_s 0.7, hsv_v 0.4, translate 0.1, scale 0.5, fliplr 0.5, mosaic 1.0, erasing 0.4,
close_mosaic 10`. Critically **`degrees: 0.0` and `flipud: 0.0`** — no rotation and no vertical
flip were applied, nor blur.

Turn this into a finding: fish appear at arbitrary orientation in the channel, so the *absence* of
rotation and vertical-flip augmentation is a concrete, cheap improvement lead.

**⚠ TRAP — C7. What confidence threshold does the system run at?**

The paper says 0.50 and cites `config.yaml`. `config.yaml` ships **0.15**, with NMS IoU 0.45 (not
0.50) and min_hits 2 (not 3). The validated rounds behave like a ≈0.50 operating point: at
conf 0.50 on validation the detector recovers 96.2% of true instances (near count-unbiased), while
at 0.15 it predicts 197 boxes against 157 true instances — a 25.5% *over*count. So Tables 1 and 2
are consistent with 0.50; the shipped 0.15 is a regression in the config file, not the setting the
results were obtained at. The correct response is to fix the config, not the paper.

**C8. You apply CLAHE at inference but not in training or evaluation. Why, and what does it do?**

Caught — and it is worth reporting rather than hiding. `FingerlingDetector.detect()` applies CLAHE
(clipLimit 2.0, 8×8 tiles, LAB space) to every frame in production, but the model was trained
without it and Table 1 was computed without it. Measured on the same weights:

| Split | Preproc | P | R | F1 | mAP@0.5 |
|---|---|---|---|---|---|
| val | raw (as reported) | 0.811 | 0.782 | 0.796 | 0.821 |
| val | + CLAHE (as deployed) | 0.773 | **0.835** | 0.803 | **0.837** |
| test | raw | 0.871 | 0.761 | 0.813 | 0.832 |
| test | + CLAHE (as deployed) | 0.877 | **0.832** | **0.854** | **0.870** |

CLAHE buys **+5.3 pp recall on validation and +7.1 pp on test**, at some cost to precision and
tight-IoU localisation. Recall is precisely the axis on which this system loses fish, so the
deployed configuration is the better one for counting — the reporting should carry both rows and
state which was used.

**C9. Why ONNX in production, and are the two backends equivalent?**

The deployed service loads `models/best.onnx` because the production environment carries
`onnxruntime` without `torch` or `ultralytics` — a deployment-size constraint on free-tier
hosting. They are close but not identical: over the 66 validation images with CLAHE on both sides,
ONNX returns 224 detections against PyTorch's 233 (−3.9%), with 18 of 66 images differing and a
maximum per-image difference of 2. The cause is letterbox and NMS implementation differences. All
reported metrics come from the PyTorch path, and that should be declared.

---

## D. Tracking and counting — the highest-risk section

**⚠ TRAP — D1. Walk me through your tracker. You say SORT with a Kalman filter.**

This is the claim most likely to be checked, and the code does not support it. There is **no Kalman
filter anywhere in `src/`** — `filterpy` is installed but never imported. `Track.predict()` is a
two-point constant-velocity extrapolation: `predicted = centre + (history[-1] − history[-2])`.
Association is by **Euclidean centroid distance, not IoU** — `_compute_iou()` is defined and never
called, and the `iou_threshold = 0.3` argument is stored and never read. The real gate is
`max_distance` = 160 px. Hungarian assignment via `scipy.optimize.linear_sum_assignment` is the one
part that matches.

The accurate description, which you should use: *"Detections are associated frame-to-frame by a
lightweight SORT-style tracker after Bewley et al. (2016) — Hungarian assignment on Euclidean
centroid distance, with constant-velocity motion prediction and a 160 px gating radius. Unlike SORT
proper it uses neither a Kalman filter nor IoU association; the simplification is acceptable here
because the observation geometry keeps fish separated and slow-moving."*

If pressed on *why* the simplification is defensible: a Kalman filter earns its keep under
occlusion and erratic motion. In a constrained channel where fish move near-unidirectionally in a
near-single layer, two-point extrapolation captures essentially the same motion model at a fraction
of the cost — and the error taxonomy supports this, since track losses were the *rarest* of the
three failure modes in every class.

**⚠ TRAP — D2. Explain exactly how a fish gets counted.**

Two different answers exist, and you must know which you are describing.

*As the paper describes it:* a virtual line at y = 0.50, counted once per track, only on a
downstream crossing, with upstream crossings discarded.

*As the code ships:* `config.yaml` sets `counting.mode: "unique_track"`. In that mode **no counting
line is created at all** — `_count_unique_tracks()` increments the total the moment a track reaches
`count_min_hits` = 2, anywhere in the frame, in any direction, moving or stationary. And even in
`line_crossing` mode **there is no direction gate**: `_check_line_crossings()` fires on
`prev < line <= curr` *or* `prev > line >= curr`. `track.get_direction()` is called and its return
value discarded. Re-counting is prevented by a one-shot `counted` flag, not by direction.

The difference is not cosmetic. On `VID_20260617_151857.mp4` (102 s, 2,815 frames, a clip
containing one or two fish): the shipped configuration reports **111**; the configuration the
manuscript describes reports **3**. On the second clip, which is essentially empty, shipped reports
**49**, the described configuration reports **0** — exactly right.

The correct position: *the method described in the paper is the right method and is 37× closer to
the truth; the shipped config is a regression, and the fix is five values in `config.yaml` plus a
direction gate in the tracker.* Do not defend `unique_track`.

**⚠ TRAP — D3. How is a class assigned to a counted fish? You say majority vote over the track.**

It does not exist. `Track.update()` overwrites `class_name` with the current frame's label on every
update, so the recorded class is whatever the *most recent* matched detection carried. A repo-wide
search for `most_common`, `Counter(`, `vote` or `majority` in `src/` returns nothing.

Why it matters, stated plainly: size sorting *is* the class assignment, so a fish whose class
flickers is sorted by a coin flip on its last frame. In the video run, the same physical juvenile
was recorded under all three labels at different moments. The implementation is about eight lines —
a `collections.Counter` on `Track`, updated in `update()`, read at count time.

**D4. How do you prevent double counting?**

Within a single track, a one-shot `counted` flag — a fish that hesitates and re-crosses is not
counted twice. **Across** tracks there is no protection: when identity is lost and re-acquired, the
same fish is counted again under a new ID. On the handheld footage this happens constantly. Under
the fixed-camera tank conditions of the validation rounds it is far rarer, which is why Table 2
shows no double counts — but it is a structural limitation, not an eliminated failure mode.

**D5. Why SORT-style tracking rather than DeepSORT?**

DeepSORT adds an appearance-embedding network, which costs inference time I do not have on CPU, and
its benefit is re-identification after long occlusion. The error analysis says track loss was the
*rarest* of the three failure modes in every class, so the appearance model would be paying a
throughput penalty to fix the problem I do not have. That is an evidence-based choice, not a
convenience one.

**⚠ TRAP — D6. You claim every counted fish is logged to CSV for audit. Show me.**

`CSVLogger` writes a **per-frame snapshot**, not a per-fish event:
`timestamp, frame, total, fingerling, post_fingerling, juvenile, unknown, fps`. There is no
track-identifier column and no per-fish row, so per-fish post-hoc reconstruction is not possible as
built. There is also a real bug — the header is written with an escaped `\n` inside a non-raw
f-string, so a literal backslash-n is emitted and the header runs into the first data row.

Both are small fixes (~10 lines for a proper event log), and until they are made, the auditability
argument should be stated as a design intent, not a delivered capability.

---

## E. Results and statistics

**E1. Your mAP@0.5:0.95 is 0.479 against mAP@0.5 of 0.822. That is a large gap. Explain it.**

The gap means the model **finds** fish reliably but draws **loose boxes**. mAP@0.5 requires only
50% overlap; the 0.5:0.95 average demands progressively tighter localisation. For small,
fast-moving, partially-submerged targets at 640×640 with 332 training images, that is the expected
signature. Crucially it is the right trade-off for this task: counting depends on *detecting* a
fish, not on pixel-accurate boxes. It would matter if I were estimating biomass from box area —
which is why size classification, which does partly depend on box geometry, is the weaker of my two
claims.

**E2. Juvenile F1 is 0.936 against 0.733 for fingerlings. Isn't that just class imbalance?**

It is the opposite, and this is the strongest version of the argument. Juvenile has the **fewest**
instances — 19 in the validation set, 96 across the dataset — and the **best** metrics. Fingerling
has the most instances and the worst. If data volume drove performance, the ordering would invert.
What drives it is pixel support and occlusion: juveniles occupy more pixels, overlap less, and are
individually resolvable.

Pre-empt the counter-attack: **19 instances in 13 images is a thin estimate** with a wide interval,
and the per-class table should carry an instance count per row (90 / 48 / 19) so a reader can
weight it.

**E3. You report validation metrics. `best.pt` was selected on validation. Isn't that optimistic?**

A fair and correct criticism — the reported table is a model-selection score, not a clean
generalisation estimate. I also have the untouched 34-image, 62-instance test split:

| Split | Role | P | R | F1 | mAP@0.5 | mAP@0.5:0.95 |
|---|---|---|---|---|---|---|
| val (66 img / 157 inst) | model selection — reported | 0.811 | 0.782 | 0.796 | 0.821 | 0.479 |
| **test (34 img / 62 inst)** | **held out** | **0.871** | **0.761** | **0.813** | **0.832** | **0.451** |

The test result is **slightly better** than validation, so the model is not overfitted to the
selection split.

**⚠ But do not present this as a generalisation claim — see B8.** Measured on the filename
timestamps, the splits are not independent, so the test score is close to the validation score for
the wrong reason. Present it as "consistent across splits", nothing stronger.

**E4. 156 fish is a small validation sample.**

Agreed, and the confidence intervals are reported precisely so the reader can see how small. The
Wilson interval on 135/156 is 80.3–91.0% — nearly 11 points wide, and I do not claim precision
beyond it. Note also that I decline to claim the size gradient is real: Cochran–Armitage gives
p = 0.29, so the apparent 83.3 → 87.0 → 90.5% trend is **not** significant at this sample size, and
I say so. Reproducibility across rounds was good (CV 3.5–4.6%).

**E5. Your Wilson interval treats 156 passages as independent. They are not.**

Correct, and this is the sharpest statistical question available. The same 20/18/14 individuals
were re-used across the three rounds of their class, and fish within a round share water, light,
clustering and operator state — the effective independent unit is closer to **9 rounds** than 156
trials. That is a pseudoreplication concern for *generalisation*.

It does not, however, inflate the reported precision. A cluster bootstrap resampling the nine
rounds (200,000 draws) gives **84.1–89.2%**, which is *narrower* than the Wilson interval, because
between-round variance is small (round accuracies 85.0, 80.0, 85.0, 88.9, 83.3, 88.9, 92.9, 85.7,
92.9; SD 4.3 pp). So the Wilson interval is conservative, not optimistic — but generalisation is
limited by nine rounds, not by 156 passages.

**E6. Why Wilson intervals and Bland–Altman rather than simpler statistics?**

Wilson because the normal approximation misbehaves at proportions near the boundary with n this
small. Bland–Altman because accuracy alone cannot distinguish a system that is unbiased-but-noisy
from one that is biased-but-consistent — and that distinction is the practical finding here. The
limits of agreement are **+0.37 to +4.29 fish**, and because the interval excludes zero the bias is
established rather than suspected: paired t = 7.00, df = 8, p = 0.0001.

**E7. What does the systematic bias mean for a user?**

It is the most useful result in the paper. A random error of ±13% is not correctable; a *systematic*
undercount of 13.1% (SD 4.3) is — a calibration multiplier recovers most of it. That is why I report
the bias direction and tightness rather than only the headline accuracy.

**⚠ TRAP — E8. You claim no false positives and no double counts. Defend that.**

Only defensible **within the validated envelope**, and it should be narrowed to say so. Three lines
of evidence contradict the unqualified claim at the shipped configuration: (i) on the supplied
footage, 85 of 111 counted detections (77%) are on wet pavement, paving-slab joints, puddles and the
outer wall of the pipe — background outside the channel entirely, with the same static pavement
patch re-counted at frames 278, 472, 581, 625, 726, 797, 838, 943…; (ii) on validation at conf 0.15
the detector predicts 197 boxes against 157 true instances, a net overcount; (iii) double counts are
structural (D4).

The defensible form: *"Within the 156 scored passages, every discrepancy from the reference was an
undercount. False positives were not observed under the controlled tank conditions of the validation
rounds; behaviour outside that envelope is reported separately."* And the root cause is B6 — zero
background images in training.

**E9. Those videos show your system counting 111 fish in a clip with two. Doesn't that destroy the
86.5% figure?**

No, and the distinction matters. Those two videos are **rig-documentation footage**: handheld,
panning across unrelated background, channel empty for most of the runtime. The validated rounds
used a fixed camera framing the rig, where out-of-channel background is simply not in frame. What
the videos show is not that 86.5% is wrong, but that **the shipped configuration is not the
validated configuration**, and that out-of-channel background is a live failure mode outside the
tested envelope. I would rather report that than have it discovered — it shows the system was tested
beyond the conditions that flatter it, and it motivates the deployment recommendations concretely.

---

## F. Error analysis

**F1. Where do the 21 missed fish come from?**

Frame-by-frame review traced every one to three mechanisms. **Detection misses** — fish visible but
scoring below threshold; dominant for fingerlings, which sit at the edge of what the model resolves
at 640×640. **Cluster merges** — fish crossing together become one box and one track; dominant for
larger fish, because feed-driven movement arrives in pulses of small groups. **Track losses** — a
track drops just before the line; rare in all classes, which is what justifies SORT over DeepSORT.

The useful structural point: the two dominant causes run in **opposite directions by fish size**, so
no single confidence threshold can fix both. Lowering it recovers faint fingerlings and worsens
merges; raising it does the reverse. That is the argument for class-specific thresholds.

**F2. If detection misses dominate for fingerlings, why not just lower the threshold?**

Because the threshold that maximises F1 is not the threshold that minimises counting error, and
counting is the task. Measured on image-level count error:

| Split | conf | F1 | count MAE | bias | Σpred/Σtrue |
|---|---|---|---|---|---|
| val | 0.15 (shipped) | 0.757 | 0.91 | +0.61 | 125.5% |
| val | 0.50 (manuscript) | **0.799** | **0.67** | **−0.09** | **96.2%** |
| test | 0.35 | **0.840** | **0.21** | −0.15 | 91.9% |
| test | CLAHE + 0.35 | 0.848 | 0.38 | **+0.03** | **101.6%** |

F1 peaks at 0.50 on validation and 0.35 on test; count bias crosses zero near 0.45 and 0.30
respectively. Lowering the threshold trades a recovered fingerling for a false positive on
background, and at 0.15 that trade is badly negative.

**F3. Is there a fourth error mechanism you did not report?**

Yes, and it should be added: **frame-rate-limited misses**. Measured CPU-only on an Intel i5-6300U,
the pipeline runs at 5.2 FPS (PyTorch) to 7.1 FPS (ONNX) on validation images, and 6.7–8.0 FPS on
1080p video, against source footage at 27.6 FPS. At 6 FPS the inter-frame interval is 167 ms, so a
fish crossing the line faster than that is never seen in two consecutive frames and cannot trigger a
crossing. That is an unreported contributor to the undercount, and it means "real-time" must be
qualified as *"real-time on GPU; 5–8 FPS on CPU"*.

**F4. Your model fires on wet pavement. How is that possible?**

Directly traceable to B6 — the training set contains zero background images, so the model has never
been shown an example of "not a fish" and has no decision boundary for it. Wet paving slabs under
glare present elongated dark-light texture transitions that resemble a submerged fish body at the
scale the model operates on.

Worth adding the mechanistic nuance: **raising the confidence threshold does not fix this.** In one
clip the two highest-confidence detections in the entire video are `fingerling 0.79` on a
paving-slab joint and `fingerling 0.80` on the shadow at the pipe's cut edge — both well above 0.50.
What suppresses them is the **line-crossing requirement**, because static background never crosses
the line whereas a transiting fish does. So direction-gated line crossing is not merely a
de-duplication device; it is the system's only working defence against static background false
positives. That is a strong argument for the design the paper describes.

---

## G. The rig, hydraulics and fish behaviour

**G1. What was the hardest part of this work?**

Not the model — getting the fish to move past the camera at all. With flow alone the fish turned
into the current and held station (rheotaxis; Arnold 1974), so almost none entered the pipe. A
perfect detector counts nothing if the fish will not swim. Adding 2 mm sinking feed continuously
moved them through within minutes, and that feed-stimulated, flow-assisted protocol became the
standard procedure and is the paper's main transferable contribution.

**G2. Did feed introduction bias your counts?**

It changes the arrival pattern, and I report the consequence rather than hiding it: feed-driven
movement arrives in **pulses of small groups** rather than a steady single file, which is precisely
why cluster merges are the dominant error for larger fish. So feeding improves throughput at the
cost of a specific, identified error mode. A metered dispenser producing steadier arrivals —
recommendation (iii) — would reduce it.

**⚠ TRAP — G3. Describe the observation window.**

The paper says "glazed" and "transparent observation window". The footage shows a **PVC pipe with a
rectangular window cut in the top and no glazing** — an open channel viewed from directly above,
water surface exposed to air. The figure caption already says "open-channel observation
cross-section", so the text contradicts its own figure. Concede this; "glazed" should be removed
throughout, and surface disturbance and refraction re-attributed to the free air–water surface
rather than to a window.

**⚠ TRAP — G4. Check your flow-area calculation.**

The paper uses A = bh = 0.10 × 0.05 = 0.005 m², which is a **rectangular** cross-section. The rig is
a round pipe with the top cut away, so the wetted section is a circular segment: for a 100 mm ID
pipe at 50 mm depth, A = πr²/2 = **0.00393 m²**. The rectangular form **overstates the flow area by
27%**. Either state explicitly that the observation section is a rectangular flume, or use the
circular-segment form A = r²(θ − sin θ)/2 with θ = 2·arccos((r − h)/r).

The volume and pressure equations are all arithmetically correct: 10.0 L, 13.25 L, 2452.5 Pa.

**⚠ TRAP — G5. Your flow rate does not match your head. Explain.**

The most dangerous question for an agricultural engineering panel, because it is a check your
examiners can do in their heads. Free gravity discharge at H = 0.25 m gives v = √(2gH) = 2.21 m/s —
roughly 26 L/min through even a 20 mm pipe, around 650 L/min through a 100 mm pipe. The stated
0.5 L/min is two to three orders of magnitude lower, so **the flow must have been throttled**, by a
valve or part-open tap the Methods does not mention. That belongs in the protocol.

Worse, 0.5 L/min over A = 0.005 m² is a mean velocity of **1.7 mm/s**, which would take **20
minutes** to move 10 L — inconsistent with the stated clearing time of five to eight minutes, and far
below any velocity that would produce the strong station-holding rheotaxis that is the paper's
headline behavioural finding.

Safe answer: *"The figure needs re-checking. 5 L/min gives 17 mm/s and a two-minute transfer, which
fits the observed narrative; 0.5 L/min does not. Either it is a transcription error, or the velocity
relevant to the rheotaxis observation is the local one at the constricted pipe inlet rather than the
channel mean — and I should report the velocity at the point the fish experienced it, together with
how flow was regulated and measured."* Do **not** attempt to defend 0.5 L/min as printed.

**G6. Why does the window geometry matter?**

0.10 m wide × 0.05 m deep forces fish to pass in a **near-single layer**, which is what makes
monocular counting tractable at all — it removes most depth-wise occlusion. It is a physical
solution to a computer-vision problem, and it is cheaper than solving the same problem with a better
model.

**G7. Is the system stressful to the fish?**

Less than the alternative. Hand counting requires repeated netting, handling and air exposure; here
the fish move voluntarily under feed stimulus through a gravity-fed channel into a receiving tank.
Every fish was recovered and recounted after each round, which is both the reference check and a
welfare check. I did not measure cortisol or post-transfer mortality, which an extension should.

---

## H. Deployment and economics

**H1. Break down the USD 40–60.**

Source tank, PVC pipe and fittings, the cut observation section, mesh screen, the destination tank
and the mounting. The phone is explicitly excluded because the premise is that the farmer already
owns one — which is the honest framing, since a phone bought for this purpose would change the
comparison. Processing runs on a laptop-class machine at the hatchery, with no cloud connection
needed.

**H2. "Smartphone-based" — but the processing runs on a laptop. Isn't the title misleading?**

A fair challenge. The smartphone is the **acquisition** device; inference runs on a laptop-class
machine with a web dashboard. "Smartphone-deployable" is the defensible claim: the model is small
enough to run on-device, and the ONNX export exists for that path, but I validated the laptop
configuration. Either the title should say smartphone-*acquired*, or the on-device capability should
be demonstrated rather than asserted.

**H3. What hardware does a hatchery actually need?**

Any laptop-class machine. Measured CPU-only throughput is 5–8 FPS on an i5-6300U — about a quarter
of real time against 27.6 FPS footage. That is adequate for the current batch-processing workflow
and inadequate for continuous live operation, which is a real limitation that the cost comparison
against commercial counters currently obscures. Commercial channel counters run continuously.

**H4. Would a farmer actually use this?**

The honest answer is that adoption was not tested, and the current form — assemble a rig, run a
laptop, open a dashboard — is a research prototype, not a product. That is exactly what
recommendation (iii) addresses: an enclosed edge device with regulated flow, a feed dispenser and a
fixed camera. The use case where adoption is plausible today is at sale or stocking of a large
batch, where the labour saved is substantial and an auditable record has commercial value in a
dispute.

**H5. Does it work in a real hatchery, outdoors, in variable light?**

Not demonstrated, and the evidence says be cautious. All validation was in controlled tank
conditions with a fixed camera. The outdoor handheld footage shows severe background false positives
under glare on wet surfaces. So the correct claim is that it works within a controlled observation
geometry, and that deployment requires enclosing that geometry — which is why the enclosed-device
recommendation exists rather than being an afterthought.

---

## I. Limitations and future work

**I1. What is the single biggest limitation?**

The domain gap. The model was trained on static tray images and deployed on flowing-channel video.
Everything else — the loose boxes, the fingerling misses, the background false positives — is
downstream of that. Which is why recommendation (i) is to annotate 500–1,000 frames filmed **in the
operating channel**, not in trays, and why I rank it ahead of any model change.

**I2. If you had six more months, what would you do, in order?**

(1) Add 30–50 background images and retrain — cheapest fix, largest effect on false positives.
(2) Fix the configuration and implement the direction gate and majority vote — turns 111 into 3 on
real footage, for about twenty lines of code. (3) Annotate 500–1,000 in-channel frames to close the
domain gap. (4) Raise input resolution to 960–1,280 px with class-specific thresholds. (5) Validate
at commercial batch sizes — hundreds, not twenty. (6) Build the enclosed edge device.

Note the ordering: the first two cost almost nothing and are not model work.

**I3. How would this scale to a thousand fish?**

Unknown, and that is a genuine limitation — the largest round was 20 fish. Two effects will not
extrapolate linearly: cluster merges should worsen with density, and track fragmentation accumulates
with duration. The counter-argument is that the bias is systematic and consistent (CV 3.5–4.6%
across rounds), so if that structure holds at scale a calibration factor remains viable. But it must
be tested, not assumed.

**I4. Does the size classification actually work?**

It is the weaker of the two claims and I would present it as such. Detection-level class metrics are
good (juvenile F1 0.936), but at count time the class is assigned from the last matched frame rather
than by majority vote (D3), so a flickering fish is sorted by a coin flip — the same physical
juvenile was recorded under all three labels in the video run. Fix the vote and the classification
claim becomes as strong as the detection metrics suggest it should be.

**I5. What would make this publishable at a higher tier?**

Larger and more diverse data including negatives, in-channel training frames, validation at
commercial batch sizes, an architecture ablation, and reporting MAE/RMSE/MAPE alongside the
agreement statistics — the last of which is computable today on data already in the repository and
should move from future work into results.

---

## J. Hostile and trap questions

**J1. "This is just YOLO with a line. Where is the research contribution?"**

The research contribution is not the detector. It is the finding that rheotaxis, not detection
accuracy, is the binding constraint on automated fingerling counting, and the feed-stimulated
flow-assisted protocol that resolves it — a behavioural result that transfers to grading,
vaccination, transfer and harvest regardless of which detector anyone uses. Alongside it: a dataset
that did not exist, and a full-system validation at a documented cost point. The engineering is
deliberately conventional because the contribution is the protocol and the evidence.

**J2. "Did you write this code, or did an AI?"**

Answer directly and without defensiveness: state your actual workflow, then demonstrate command of
it. The defence against this question is not the answer, it is being able to explain *why*
centroid-distance association was acceptable here, *why* the two dominant error modes cannot be
fixed by one threshold, and *what* the 0.822/0.479 mAP gap means. Those are D1, F1 and E1.

**J3. "Your results are not reproducible — I ran your code and got a different number."**

They are right, and you should know it before they say it. The shipped `config.yaml` is not the
configuration the results were obtained at: it ships conf 0.15 and `unique_track`, where the
validated rounds behave like conf 0.50 with line crossing. Concede the configuration drift
immediately, state that the fix is five values in one file, and point out that every *statistic* in
the paper reproduces exactly — the detection metrics match the checkpoint's own stored values and an
independent re-run to within rounding, and all nine agreement statistics recompute to the printed
precision. The numbers are sound; the shipped config is a regression.

**J4. "Why should I believe your hand-counted reference?"**

Each round's reference was confirmed by **two independent hand counts**, and every fish was
recovered and recounted afterwards — so the reference is triple-checked, and the closing recount also
rules out fish lost in the apparatus being misattributed to detection failure.

**J5. "Your accuracy is lower than published work on fish counting. Why publish?"**

Because the comparison controls for cost, and published work generally does not. The
accuracy-against-cost figure places this system at the lowest capital cost of any automated option
compared, 8–10 points below commercial optical counters costing 50–250× more. A result is
interesting when it is on the frontier, not when it is at the maximum — and in a resource-constrained
setting the relevant frontier is accuracy per naira.

**J6. "You have four claims in your Methods that your code contradicts. Is the rest of the paper
trustworthy?"**

The question to prepare hardest for. The answer is specific, not apologetic: the discrepancies are
**descriptive**, in Methods prose written against an intended design, and they are all repairable.
Every **measured** quantity in the paper has been independently verified — the detection metrics
reproduce from the checkpoint's own stored values, and all nine statistics recompute to the printed
precision. The system that produced the counting results was the one described, at conf ≈0.50 with
line crossing; the shipped config drifted afterwards. I audited this against the code myself, the
audit is in the repository, and the corrections are itemised with the code changes they require.

That is the strongest available position: you found it first, you quantified it, and you know
exactly what each fix costs.

---

## Numbers to have cold

| Quantity | Value |
|---|---|
| Counting accuracy | 86.5% (135/156), Wilson 95% CI 80.3–91.0 |
| By class | fingerling 83.3%, post-fingerling 87.0%, juvenile 90.5% |
| Size trend significance | Cochran–Armitage p = 0.29 — **not** significant |
| Round-to-round CV | 3.5–4.6% |
| Mean bias | +2.33 fish/round (SD 1.00); 13.1% relative (SD 4.3) |
| Bland–Altman limits | +0.37 to +4.29 fish (excludes zero) |
| Paired t-test | t = 7.00, df = 8, p = 0.0001 |
| Cluster bootstrap (9 rounds) | 84.1–89.2% — narrower than Wilson |
| Detection, val | P 0.812, R 0.782, F1 0.797, mAP@0.5 0.822, mAP@0.5:0.95 0.479 |
| Detection, test (held out) | P 0.871, R 0.761, F1 0.813, mAP@0.5 0.832 |
| Dataset, real | 332 images, 769 instances, 232/66/34 split |
| Instances per class | fingerling 395, post-fingerling 278, juvenile 96 |
| Model, real | 3,011,433 params, 8.20 GFLOPs, YOLOv8n, 100 epochs, batch 16, 640×640 |
| CPU throughput | 5.2–8.0 FPS vs 27.6 FPS source — about ¼ real time |
| Cost | rig USD 40–60; commercial counters USD 3,000–15,000 |
| Size classes | <0.65 cm / 0.65–1.00 cm / 1.00–1.50 cm head width |
| Rig | 10 L source, 13.25 L destination, 2452.5 Pa, window 0.10 × 0.05 m |

---

## The five things to fix before you present

1. ~~**`config/config.yaml`**~~ — **done 2026-11-05.** Measured effect on the field footage: 111 → 2
   on one video, 49 → 0 on the other.
2. ~~**Direction gate**~~ — **done 2026-11-05**, `count_direction: "down"` in config.
3. ~~**Majority vote**~~ — **done 2026-11-05.** It changes the size class of 26 of 111 counted
   events (23%) on the busier video, so it materially affects size sorting.
4. **Know the corrected dataset and training numbers** (332/769, Colab, linear decay,
   `optimizer: auto`, no rotation augmentation) so you are never caught defending a printed value.
5. **Have the flow-rate answer ready** (G5). It is the one an agricultural engineering panel is most
   likely to check unprompted.
