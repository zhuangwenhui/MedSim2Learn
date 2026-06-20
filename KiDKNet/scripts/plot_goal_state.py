#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""North-star project-state figure (PPTX-ready) for RESEARCH_GOAL.md.

Three-panel diagnosis read FIRST-HAND from the CV cross_fold_summary.json files
and the domain-gap metrics:
  A) 8-condition CV magnitude MAE (real-comparable) -> the synth->real cliff is the
     only signal outside the fold noise;
  B) transfer-recipe race (c4 variants vs c1 scratch) -> all recipes statistically tied;
  C) synt<->real appearance domain gap (feature diversity + linear-probe separability).

Read-only inputs; writes one PNG. CPU; only needs matplotlib + numpy.
"""
import json
import os
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else \
    "/workspace/project/MedSim2Learn/DataFlow"
CV = os.path.join(ROOT, "KiDKNet/outputs/cv5")
GAP = os.path.join(ROOT, "Deform_post/feature_cache/domain_gap_points.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(CV, "report/goal_state_diagnosis.png")

REAL_ONLY = {"c3", "c7"}            # mixed conditions -> use real_only_slice
BLUE, RED, GREY, GREEN = "#378ADD", "#C44E52", "#8C8C8C", "#55A868"


def load(cond):
    p = os.path.join(CV, cond, "cross_fold_summary.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def metric(summ, key):
    """Real-comparable (mean, std): real_only_slice if populated else pooled."""
    ro = summ.get("real_only_slice") or {}
    src = ro if (ro and key in ro) else summ["pooled"]
    m = src[key]
    return m["mean"], m["std"]


def mag(cond):
    s = load(cond)
    if s is None:
        return None, None
    return metric(s, "magnitude_mean_absolute_error")


fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))

# ---- Panel A: 8-condition CV ----
condsA = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]
labA = ["c1\nreal\nscratch", "c2\nsynt->real\n0-shot", "c3\nmixed", "c4\ntransfer",
        "c5\nreal\nseq", "c6\nsynt->real\nseq 0-shot", "c7\nmixed\nseq", "c8\ntransfer\nseq"]
colA = [GREY, RED, BLUE, GREEN, GREY, RED, BLUE, GREEN]
mA = [mag(c) for c in condsA]
yA = [v[0] for v in mA]
eA = [v[1] for v in mA]
xa = np.arange(len(condsA))
ax[0].bar(xa, yA, yerr=eA, color=colA, edgecolor="black", linewidth=0.5, capsize=4)
for i, (y, e) in enumerate(zip(yA, eA)):
    ax[0].text(i, y + e + 0.03, "%.2f" % y, ha="center", va="bottom", fontsize=8)
ax[0].set_xticks(xa)
ax[0].set_xticklabels(labA, fontsize=7.5)
ax[0].set_ylabel("magnitude MAE (real test, raw units)  -  lower better")
ax[0].set_title("A. 8-condition CV: the synth->real cliff is\nthe only signal outside fold noise", fontsize=10)
ax[0].set_ylim(0, max(yA) * 1.25)
ax[0].annotate("~6x sim2real cliff\n(zero-shot synth)", xy=(1, yA[1]), xytext=(2.4, yA[1] * 0.92),
               fontsize=8, color=RED,
               arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
ax[0].grid(axis="y", alpha=0.25)

# ---- Panel B: transfer-recipe race (zoomed) ----
condsB = ["c1", "c4", "c4ft", "c4dl", "c4sg", "c4fz"]
labB = ["c1\nscratch", "c4\nLP-FT", "c4ft\nfull-FT", "c4dl\ndisc-LR", "c4sg\nsurgical", "c4fz\nfrozen"]
colB = [GREY, GREEN, GREEN, GREEN, GREEN, GREEN]
mB = [mag(c) for c in condsB]
yB = [v[0] for v in mB]
eB = [v[1] for v in mB]
xb = np.arange(len(condsB))
ax[1].bar(xb, yB, yerr=eB, color=colB, edgecolor="black", linewidth=0.5, capsize=4)
for i, (y, e) in enumerate(zip(yB, eB)):
    ax[1].text(i, y + e + 0.004, "%.3f" % y, ha="center", va="bottom", fontsize=8)
c1mean = yB[0]
ax[1].axhline(c1mean, ls="--", color=GREY, lw=1.2)
ax[1].text(len(condsB) - 0.5, c1mean + 0.002, "c1 scratch baseline", ha="right", va="bottom",
           fontsize=8, color=GREY)
ax[1].set_xticks(xb)
ax[1].set_xticklabels(labB, fontsize=8)
ax[1].set_ylabel("magnitude MAE (real test)  -  lower better")
ax[1].set_title("B. Transfer-recipe race: 5 recipes all\nstatistically tied (spread << fold std)", fontsize=10)
ax[1].set_ylim(0, max([y + e for y, e in zip(yB, eB)]) * 1.18)
ax[1].grid(axis="y", alpha=0.25)

# ---- Panel C: appearance domain gap ----
gm = {}
if os.path.exists(GAP):
    gm = json.load(open(GAP)).get("metrics", {})
rms_r = gm.get("rms_real", 7.64)
rms_s = gm.get("rms_synth", 1.25)
sep_acc = gm.get("sep_acc", 1.0)
sep_ratio = gm.get("sep_ratio", 3.7)
ax[2].bar(["real", "synth"], [rms_r, rms_s], color=[BLUE, RED], edgecolor="black", linewidth=0.5)
for i, v in enumerate([rms_r, rms_s]):
    ax[2].text(i, v + max(rms_r, rms_s) * 0.02, "%.2f" % v, ha="center", va="bottom", fontsize=9)
ax[2].set_ylabel("within-domain feature spread (RMS)  -  diversity")
ax[2].set_title("C. Appearance domain gap:\nsynth ~%.1fx less diverse than real" % (rms_r / rms_s), fontsize=10)
ax[2].set_ylim(0, rms_r * 1.25)
ax[2].text(0.5, rms_r * 1.12,
           "linear-probe real-vs-synth separability %.0f%% (chance 50%%)\nseparation ratio %.1f"
           % (sep_acc * 100, sep_ratio),
           ha="center", va="top", fontsize=8.5,
           bbox=dict(boxstyle="round,pad=0.4", fc="#FFF3CD", ec="#E0C97F"))
ax[2].grid(axis="y", alpha=0.25)

fig.suptitle("MedSim2Learn project state (2026-06-21): an APPEARANCE domain-coverage problem, "
             "not architecture  -  fix measurement -> close appearance gap -> architecture last",
             fontsize=12, y=1.02)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches="tight")
print("[fig] wrote %s" % OUT)
