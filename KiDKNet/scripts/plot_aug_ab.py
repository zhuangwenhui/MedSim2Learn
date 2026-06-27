#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase-0 augmentation A/B: no-aug (cv5) vs photometric-aug (cv5_aug), per condition.

Grouped bars (magMAE + mean angle error) with fold-std error bars. PPTX-style.
Real-comparable metric: real_only_slice for mixed conds (c3,c7) else pooled.
"""
import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DF = sys.argv[1] if len(sys.argv) > 1 else "/workspace/project/MedSim2Learn/DataFlow/KiDKNet"
CONDS = (sys.argv[2].split(",") if len(sys.argv) > 2 else ["c1", "c3"])
NOAUG, AUG = os.path.join(DF, "outputs/cv5"), os.path.join(DF, "outputs/cv5_aug")
OUT = os.path.join(AUG, "report/aug_ab.png")
REAL_ONLY = {"c3", "c7"}
GREY, GREEN = "#8C8C8C", "#55A868"


def metric(path, cond, key):
    if not os.path.exists(path):
        return None
    s = json.load(open(path))
    ro = s.get("real_only_slice") or {}
    src = ro if (cond in REAL_ONLY and ro and key in ro) else s["pooled"]
    m = src[key]
    return m["mean"], m["std"], m["n"]


rows = []
for c in CONDS:
    na = metric(os.path.join(NOAUG, c, "cross_fold_summary.json"), c, "magnitude_mean_absolute_error")
    au = metric(os.path.join(AUG, c, "cross_fold_summary.json"), c, "magnitude_mean_absolute_error")
    na_a = metric(os.path.join(NOAUG, c, "cross_fold_summary.json"), c, "mean_angle_error")
    au_a = metric(os.path.join(AUG, c, "cross_fold_summary.json"), c, "mean_angle_error")
    if na and au:
        rows.append((c, na, au, na_a, au_a))

if not rows:
    print("[aug_ab] no condition has BOTH cv5 and cv5_aug summaries yet"); sys.exit(0)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig, ax = plt.subplots(1, 2, figsize=(5 + 2.2 * len(rows), 5))
x = np.arange(len(rows)); w = 0.36
for j, (key_idx, ylab, title) in enumerate([(0, "magnitude MAE (lower better)", "A. magMAE: no-aug vs photometric-aug"),
                                            (1, "mean angle error deg (lower better)", "B. angle error: no-aug vs aug")]):
    na_m = [r[1 if j == 0 else 3][0] for r in rows]; na_s = [r[1 if j == 0 else 3][1] for r in rows]
    au_m = [r[2 if j == 0 else 4][0] for r in rows]; au_s = [r[2 if j == 0 else 4][1] for r in rows]
    ax[j].bar(x - w/2, na_m, w, yerr=na_s, capsize=4, color=GREY, edgecolor="black", linewidth=0.5, label="no-aug")
    ax[j].bar(x + w/2, au_m, w, yerr=au_s, capsize=4, color=GREEN, edgecolor="black", linewidth=0.5, label="photometric-aug")
    for i in range(len(rows)):
        ax[j].text(x[i]-w/2, na_m[i]+na_s[i], "%.3f" % na_m[i], ha="center", va="bottom", fontsize=8)
        ax[j].text(x[i]+w/2, au_m[i]+au_s[i], "%.3f" % au_m[i], ha="center", va="bottom", fontsize=8)
    ax[j].set_xticks(x); ax[j].set_xticklabels([r[0] for r in rows])
    ax[j].set_ylabel(ylab); ax[j].set_title(title, fontsize=10); ax[j].legend(fontsize=9); ax[j].grid(axis="y", alpha=0.25)
fig.suptitle("Phase-0 photometric augmentation A/B (real-comparable, 5-fold CV, error bars = fold std)", fontsize=12, y=1.02)
fig.savefig(OUT, dpi=140, bbox_inches="tight")
print("[fig] wrote %s" % OUT)
for c, na, au, na_a, au_a in rows:
    print("  %-3s magMAE: no-aug %.4f+/-%.4f  aug %.4f+/-%.4f  (dMean %+.4f, dStd %+.4f) | angle %.1f->%.1f"
          % (c, na[0], na[1], au[0], au[1], au[0]-na[0], au[1]-na[1], na_a[0], au_a[0]))
