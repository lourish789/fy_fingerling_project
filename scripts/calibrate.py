#!/usr/bin/env python
"""
Field calibration: compare machine counts with hand counts and derive a
correction factor for config/config.yaml.

Prepare a CSV with one row per calibration batch:

    batch,hand_count,run_id
    B1,212,20261120_091500_batch1
    B2,198,20261120_094210_batch2
    B3,205,20261120_101030_batch3

`run_id` is the folder name under output/runs/ (the machine count is read from
its summary.json). Instead of `run_id` you can give a `machine_count` column.

    python scripts/calibrate.py calibration.csv

Method
  * factor = sum(hand) / sum(machine)  (ratio estimator; weights big batches more)
  * 95% interval for the factor by bootstrap over batches
  * Expected error after calibration estimated by leave-one-out: each batch is
    corrected with a factor computed from the *other* batches only, so the
    estimate is not flattered by fitting the batch it is tested on.

A factor is only valid for the setup it was measured on: same model file,
thresholds, camera position, lighting, flow rate and fish size class.
Recalibrate when any of those change.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_rows(path: Path, runs_dir: Path):
    rows, settings_seen = [], {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            name = (r.get("batch") or f"row{i}").strip()
            try:
                hand = int(float(r["hand_count"]))
            except (KeyError, ValueError):
                sys.exit(f"{path}:{i}: hand_count missing or not a number")
            machine = None
            run_id = (r.get("run_id") or "").strip()
            if run_id:
                summary_path = runs_dir / run_id / "summary.json"
                if not summary_path.exists():
                    sys.exit(f"{path}:{i}: no summary at {summary_path}")
                s = json.loads(summary_path.read_text(encoding="utf-8"))
                if s.get("status") != "completed":
                    print(f"  ! {name}: run status is '{s.get('status')}' - the count may be partial")
                machine = int(s["counts"]["total"])
                st = s.get("settings", {})
                key = (st.get("model_sha256_12"), st.get("confidence_threshold"),
                       st.get("counting_mode"), st.get("count_direction"),
                       st.get("counting_line_position"))
                settings_seen.setdefault(key, []).append(name)
            elif (r.get("machine_count") or "").strip():
                machine = int(float(r["machine_count"]))
            else:
                sys.exit(f"{path}:{i}: give either run_id or machine_count")
            if hand <= 0:
                sys.exit(f"{path}:{i}: hand_count must be positive")
            rows.append((name, hand, machine))
    return rows, settings_seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "output" / "runs")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows, settings_seen = load_rows(args.csv, args.runs_dir)
    if not rows:
        sys.exit("No rows found.")

    names = [r[0] for r in rows]
    hand = np.array([r[1] for r in rows], dtype=float)
    machine = np.array([r[2] for r in rows], dtype=float)
    n = len(rows)

    print(f"\nCalibration batches: {n}   fish hand-counted: {int(hand.sum())}\n")
    print(f"{'batch':<12}{'hand':>7}{'machine':>9}{'error':>9}")
    for nm, h, m in zip(names, hand, machine):
        print(f"{nm:<12}{int(h):>7}{int(m):>9}{100 * (m - h) / h:>8.1f}%")

    raw_err = 100 * (machine - hand) / hand
    print(f"\nRaw machine count: mean error {raw_err.mean():+.1f}%  "
          f"(mean absolute {np.abs(raw_err).mean():.1f}%, worst {raw_err[np.argmax(np.abs(raw_err))]:+.1f}%)")

    if machine.sum() == 0:
        sys.exit("Machine counted zero fish in every batch - check the setup before calibrating.")

    factor = hand.sum() / machine.sum()
    print(f"\nCorrection factor (sum hand / sum machine): {factor:.4f}")

    if len(settings_seen) > 1:
        print("\n  ! WARNING: these runs used different models or settings:")
        for key, batches in settings_seen.items():
            print(f"      model {key[0]}, conf {key[1]}, mode {key[2]}/{key[3]}, line {key[4]}: {', '.join(batches)}")
        print("    A single factor is not valid across different setups. Calibrate each setup separately.")

    if n < 3:
        print("\n  ! Only", n, "batch(es). Use at least 3, ideally 5, before trusting a factor.")
        return

    rng = np.random.default_rng(args.seed)
    idx = rng.integers(0, n, size=(10000, n))
    boot = hand[idx].sum(1) / np.maximum(machine[idx].sum(1), 1e-9)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    print(f"95% interval for the factor (bootstrap over batches): {lo:.4f} - {hi:.4f}")

    loo_err = []
    for i in range(n):
        keep = np.arange(n) != i
        if machine[keep].sum() == 0:
            continue
        f_i = hand[keep].sum() / machine[keep].sum()
        loo_err.append(100 * (machine[i] * f_i - hand[i]) / hand[i])
    loo_err = np.array(loo_err)
    print(f"Expected error after calibration (leave-one-out): mean {loo_err.mean():+.1f}%, "
          f"mean absolute {np.abs(loo_err).mean():.1f}%, worst {loo_err[np.argmax(np.abs(loo_err))]:+.1f}%")

    ratios = hand / np.maximum(machine, 1e-9)
    cv = ratios.std(ddof=1) / ratios.mean() * 100
    if cv > 10:
        print(f"\n  ! The hand/machine ratio varies a lot between batches (CV {cv:.0f}%).")
        print("    A single factor will not fix that. Look for the cause first (lighting, flow")
        print("    rate, fish clumping, camera moved) using the crops in each run's crops/ folder.")

    print("\nPaste into config/config.yaml under `counting:`\n")
    print(f"  count_correction_factor: {factor:.4f}")
    print(f'  count_correction_note: "Calibrated on {n} batches ({int(hand.sum())} fish), '
          f'factor 95% CI {lo:.3f}-{hi:.3f}, LOO mean abs error {np.abs(loo_err).mean():.1f}%"')
    print()


if __name__ == "__main__":
    main()
