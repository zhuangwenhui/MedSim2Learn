#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""k-shot learning curve: synthetic-prior vs ImageNet, real-test magMAE/angle vs k.

Robust + partial-data tolerant: aggregates each completed kshot run's evaluation
report directly (does not wait for the final kshot_results.json), so it can be run
mid-sweep to show progress. PPTX-style matplotlib figure + JSON summary.

Run: python plot_kshot.py [kshot_dir]
"""
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

KDIR = sys.argv[1] if len(sys.argv) > 1 else \
    "/workspace/project/MedSim2Learn/DataFlow/KiDKNet/outputs/kshot"
OUTDIR = os.path.join(KDIR, "report")
SYNT, IMAGENET, GREY = "#C44E52", "#378ADD", "#8C8C8C"
RUN_RE = re.compile(r"^k(\d+)_r(\d+)_(synt|imagenet)$")
METRICS = ("magnitude_mean_absolute_error", "mean_angle_error")


def latest_report(run_dir):
    import glob
    cands = sorted(glob.glob(os.path.join(run_dir, "evaluation", "*", "reports", "evaluation_report.json")))
    if not cands:
        return None
    try:
        return json.load(open(cands[-1]))
    except Exception:
        return None


# collect: data[arm][metric][k] -> list over reps
data = {a: {m: defaultdict(list) for m in METRICS} for a in ("synt", "imagenet")}
n_runs = 0
for name in sorted(os.listdir(KDIR)):
    mobj = RUN_RE.match(name)
    if not mobj:
        continue
    k, _rep, arm = int(mobj.group(1)), int(mobj.group(2)), mobj.group(3)
    rpt = latest_report(os.path.join(KDIR, name))
    if rpt is None:
        continue
    n_runs += 1
    for m in METRICS:
        if rpt.get(m) is not None:
            data[arm][m][k].append(float(rpt[m]))

if n_runs == 0:
    print("[kshot] no completed runs yet; nothing to plot")
    sys.exit(0)

os.makedirs(OUTDIR, exist_ok=True)


def series(arm, metric):
    ks = sorted(data[arm][metric].keys())
    mean = [float(np.mean(data[arm][metric][k])) for k in ks]
    std = [float(np.std(data[arm][metric][k])) for k in ks]
    nrep = [len(data[arm][metric][k]) for k in ks]
    return ks, mean, std, nrep


fig, ax = plt.subplots(1, 2, figsize=(13, 5))
panels = [("magnitude_mean_absolute_error", "real-test magnitude MAE  (lower better)",
           "A. k-shot: synthetic prior vs ImageNet (magMAE)"),
          ("mean_angle_error", "mean angle error (deg)  (lower better)",
           "B. k-shot: direction error vs k")]
for j, (metric, ylab, title) in enumerate(panels):
    for arm, color, lab in (("synt", SYNT, "synth-pretrain (c2 init)"),
                            ("imagenet", GREY, "ImageNet (no transfer)")):
        ks, mean, std, _ = series(arm, metric)
        if not ks:
            continue
        ax[j].errorbar(ks, mean, yerr=std, marker="o", ms=6, lw=1.8, capsize=4,
                       color=color, label=lab)
    ax[j].set_xscale("log", base=2)
    ax[j].set_xticks([1, 2, 4, 8, 16])
    ax[j].get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax[j].set_xlabel("# real training sequences (k)")
    ax[j].set_ylabel(ylab)
    ax[j].set_title(title, fontsize=10)
    ax[j].grid(alpha=0.25)
    ax[j].legend(fontsize=9)
if "magnitude_mean_absolute_error" == panels[0][0]:
    ax[0].axhline(0.232, ls="--", color=GREY, lw=1.0, alpha=0.7)
    ax[0].text(ax[0].get_xlim()[1], 0.232, " c1 full-real scratch 0.232", ha="right",
               va="bottom", fontsize=7.5, color=GREY)
fig.suptitle("k-shot scarce-real curve (partial; %d runs done) | synth prior wins where red < blue"
             % n_runs, fontsize=12, y=1.02)
figpath = os.path.join(OUTDIR, "kshot_curve.png")
fig.savefig(figpath, dpi=140, bbox_inches="tight")
print("[fig] wrote %s" % figpath)

summary = {arm: {m: {str(k): {"mean": float(np.mean(v)), "std": float(np.std(v)), "n": len(v)}
                     for k, v in data[arm][m].items()} for m in METRICS}
           for arm in ("synt", "imagenet")}
summary["_runs_done"] = n_runs
json.dump(summary, open(os.path.join(OUTDIR, "kshot_summary.json"), "w"), indent=2)
print("[kshot] %d runs aggregated -> %s/kshot_summary.json" % (n_runs, OUTDIR))
for k in sorted(set(list(data["synt"]["magnitude_mean_absolute_error"]) +
                    list(data["imagenet"]["magnitude_mean_absolute_error"]))):
    sv = data["synt"]["magnitude_mean_absolute_error"].get(k, [])
    iv = data["imagenet"]["magnitude_mean_absolute_error"].get(k, [])
    print("  k=%-2d magMAE: synt=%s imagenet=%s"
          % (k, "%.3f" % np.mean(sv) if sv else "-", "%.3f" % np.mean(iv) if iv else "-"))
