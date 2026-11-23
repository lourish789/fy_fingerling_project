# AquaCount in a working hatchery: Version 1

This guide covers setting up AquaCount as a **channel counter** at a hatchery. Fish
swim single-file down a channel under a fixed camera and are counted as they cross
a line. It runs on a laptop at the hatchery, offline.

**What V1 is:** the configuration that was validated (86.5% of fish counted over 9
hand-counted rounds, fixed camera, single-file channel), plus an audit trail and a
calibration procedure so the hatchery knows how far to trust each count.

**What V1 is not:** a way to count a crowd of fish from one photo of a basin. The model
was trained on images with at most 14 fish each. In a stress test, whole-image counts
fell to 41% of the true number at about 30 fish and to 0% at a few hundred. Counting
crowds needs a different setup and new training data (Version 2).

---

## 1. Hardware

| Item | Minimum | Notes |
|---|---|---|
| Computer | Windows laptop, 4-core CPU, 8 GB RAM | No GPU needed. Measured 2.7–7 frames/s on laptop CPUs. |
| Camera | USB webcam (1080p), or a phone running an IP-camera app | Must be **fixed**. Handheld footage over-counts badly. |
| Mount | Rigid arm or frame directly above the channel | Mark the height so it can be restored exactly. |
| Shade / light | Cover over the channel, steady LED light | Direct sun and glare on water cause false detections. |
| Channel | Fish pass one at a time, in one direction | Flow should run **top to bottom in the camera image**. |

### How fast can fish pass?

Each fish must be seen in several frames to be tracked and counted. With

* **F** = frames processed per second (shown on the dashboard, typically 3–7),
* **L** = length of channel visible in the image, in cm,
* **v** = fish speed, in cm/s,

each fish is seen about **F × L / v** times. Keep this at **6 or more**:

> v ≤ F × L / 6. Example: F = 3, L = 40 cm, so fish should move no faster than 20 cm/s.

Fish also need gaps between them. Two fish passing side by side, or nose to tail, can
be merged or swapped by the tracker. At 3 fish per second, 10,000 fish take about
55 minutes.

---

## 2. Install and start

**First run** (needs internet once, to install Python packages):

1. Install Python 3.10 or 3.11 from python.org (tick "Add Python to PATH").
2. Copy the whole `fingerling_counting_model` folder to the laptop. It must contain
   `models/best.onnx`.
3. Double-click **`run_hatchery.bat`**. The first run creates `.venv` and installs
   `requirements-prod.txt`. That takes a few minutes.

**Every day:** double-click `run_hatchery.bat`. The dashboard opens at
`http://localhost:5000`. The console window also prints an address such as
`http://192.168.1.23:5000` for phones and tablets on the same Wi-Fi. If Windows asks
whether to allow Python on private networks, allow it.

Manual equivalent:

```
.venv\Scripts\python.exe main.py --web-server --no-display --weights models\best.onnx --port 5000
```

---

## 3. Physical setup checklist

Do this once at installation, and again whenever anything moves.

- [ ] Camera directly above the channel at the **marked height**. Size grading
      (fingerling / post-fingerling / juvenile) uses how big a fish *looks*, so it is only
      valid at the camera height used when the training images were taken.
- [ ] Only the channel is in frame: no pavement, puddles, pipe exterior or people.
- [ ] Water flows from the **top of the image to the bottom**. If it has to run left to
      right, set `counting_line_orientation: "vertical"` and `count_direction: "right"` in
      `config/config.yaml`.
- [ ] The counting line (drawn on the video) sits across the middle of the visible channel.
- [ ] Run 2–3 minutes of **empty** channel with water flowing. The count must stay at 0.
      If it doesn't, look at the crops in that run's `crops/` folder to see what is being
      counted, then fix the framing or lighting (see section 7).
- [ ] Pass 20–30 fish you have counted by hand, and compare.
- [ ] Then do the full calibration (section 5).

---

## 4. Daily operation

1. **Start a count**
   * Live camera: *Camera* tab, choose index `0` (built-in) or `1` (USB camera), then *Start*.
   * Recorded video: *Upload* tab, choose the file, then *Upload & Process*.
   * Phone as a camera: run an IP-camera app on the phone and paste its `rtsp://` or
     `http://` stream address into the *URL* tab.
2. **Watch the overlay.** Each counted fish crosses the line downwards. Boxes on things
   that are not fish are a warning sign. Note them, and check the crops afterwards.
3. **Stop** when the batch has passed. The *Last saved count* panel then shows the total
   and links to the **Report** (printable), the **Fish log (CSV)** and the **Summary**.
4. Only one count runs at a time. Starting another while one is running is refused, so a
   count in progress can't be lost. **Reset** during a count closes the current record
   and starts a new one.

### Where the records are

Every count is saved in `output\runs\<date_time_source>\`:

| File | Contents |
|---|---|
| `report.html` | One-page summary for the batch: totals by class, calibrated estimate, settings |
| `events.csv` | One row per counted fish: time, frame, track, class, votes, confidence, box |
| `crops/` | A small picture of every counted fish, for spot checks and disputes |
| `summary.json` | Everything above in machine-readable form, including the model fingerprint |

`events.csv` is written as fish are counted, so a power cut keeps everything counted up
to that moment. **Back up `output\runs` weekly** (USB stick or cloud drive).

---

## 5. Calibration

A machine count is an estimate. Calibration measures how far off it is **in your
setup**, and the reports then show both the raw count and a calibrated estimate.

**When:** at installation, and again after any change of camera position, lighting,
flow rate, fish size class, or model file. Spot-check monthly.

**Procedure**

1. Prepare **at least 5 batches** of 150–300 fish of the size class you will be counting.
2. Hand-count each batch carefully. Count twice, or use two people, and resolve any
   disagreement.
3. Pass each batch through the channel with AquaCount running. Note each batch's
   `run_id` (the folder name in `output\runs`, also shown on the dashboard).
4. Write `calibration.csv`:
   ```
   batch,hand_count,run_id
   B1,212,20261120_091500_batch1
   B2,198,20261120_094210_batch2
   ...
   ```
5. Run:
   ```
   .venv\Scripts\python.exe scripts\calibrate.py calibration.csv
   ```
   It prints each batch's error, the correction factor with a 95% interval, and the
   **expected error after calibration**. That last figure is estimated leave-one-out,
   so it is honest. It also warns you if the batches used different settings, or if the
   error is too inconsistent for a single factor to fix.
6. Paste the two lines it prints (`count_correction_factor`, `count_correction_note`)
   into `config/config.yaml` under `counting:` and restart.

If the batches disagree strongly (the script warns when this happens), **don't** paste
the factor. Find the cause first, using the crops: fish clumping, flow too fast, glare,
or a camera that moved.

---

## 6. Retraining with background images

The current model has two known training-data problems:

1. **No background images.** All 332 training images contain fish, so the model has
   never learned "not a fish". It detects empty turbulent water as a juvenile with up to
   0.78 confidence.
2. **Stretched images.** The Roboflow export used *Resize to 512×512 (Stretch)*, so fish
   were squashed during training. At counting time, frames keep their true proportions,
   so the fish look different from what the model was trained on. This hurts detection
   and size grading.

**Steps**

1. In Roboflow, generate a new dataset version from the same images and labels with
   **Resize: "Fit (black edges)"** (or no resize) instead of *Stretch*. Export in
   YOLOv8 format.
2. Record 2–5 minutes of the **real installed setup with no fish**: water flowing,
   different times of day. Extract candidate frames:
   ```
   .venv\Scripts\python.exe scripts\extract_background_frames.py --video empty_channel.mp4
   .venv\Scripts\python.exe scripts\extract_background_frames.py --video empty_channel.mp4 --hard-only --every 3
   ```
   The second command keeps only frames where the current model wrongly detects
   something. These are the most valuable ones.
3. **Look at every image** in `data/background_candidates/...`. Delete any image that
   shows a fish, even part of one, together with its `.txt` file.
4. Aim for **30–50 background images** (about 10% of the dataset). Put about 80% in
   `train` and 20% in `val`, so the validation score measures false positives too.
5. Also add footage of **fish passing close together** (annotated in Roboflow). This is
   where the tracker and detector make most of their mistakes.
6. Train with `notebooks/colab_fingerling_training_testing.ipynb` (Colab GPU), using the
   same settings as before. Compare the new model against the old one on the same
   validation set at confidence 0.50.
7. Export the model and keep the old one:
   ```
   copy models\best.onnx models\best_v1.onnx
   python scripts\convert_to_onnx.py --weights path\to\new\best.pt --output models\best.onnx
   ```
8. Run the tests (`python -m unittest discover -s tests`), repeat the empty-channel
   check in section 3, and **recalibrate** (section 5). A factor belongs to one model.

---

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Count goes up with no fish | Glare, ripples or objects in frame. Check `crops/` to see what is counted, then reframe, shade or retrain (section 6). |
| Count stays at 0 while fish pass | Flow direction does not match `count_direction`, or fish appear already below the line (move the line up). |
| Count much lower than the hand count | Fish too fast for the frame rate (section 1), clumping, or poor contrast. |
| Camera will not start | Try index 1 or 2. Close other apps using the camera (Teams, Zoom, Camera). |
| Phone can't open the dashboard | Same Wi-Fi network? Allow Python through Windows Firewall (private networks). |
| "A count is already running" | Press **Stop** first. Only one count runs at a time. |
| Slow (frames/s below 3) | Close other programs, keep the laptop plugged in, or set `video.frame_width: 1280` and `frame_height: 720` in `config/config.yaml`. |

---

## 8. Hosted (Render) deployment

The Render backend serves the dashboard at its own URL as well as through Vercel. The
free Render plan (0.1 CPU) is far too slow for real batch videos and goes to sleep when
idle (the first request after that took 51 s). Its disk is also wiped on every restart,
so run records don't survive there. Use it for demos only. For hosted use, choose a paid
instance with at least 2 dedicated CPUs and attach a persistent disk for `output/runs`.

## 9. Known limits of V1

* Validated only for the single-file channel, with about 17 fish per round.
* Fish that first appear already past the counting line are not counted.
* Size grading is only meaningful at the training camera height, and is weakened by
  the stretched training export until the model is retrained.
* False positives on turbulent water remain until the model is retrained with
  background images.
