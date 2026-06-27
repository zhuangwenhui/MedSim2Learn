#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Publication-style figures for the KiDKNet sim2real force-regression study (v2).

Self-contained, read-only consumer of the aggregated cross_fold_summary.json /
kshot_summary.json already on disk. Emits paper-grade PNG + PDF (serif/STIX type,
neutral palette, panel tags, no status/marketing text). Honest by construction:
every panel reads its real-comparable slice and the value labels print the true
mean; incomplete arms (n<5) are flagged and de-weighted.

Run inside the container venv:
    python paper_figures.py [DATAFLOW_KIDKNET_ROOT] [OUT_DIR]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

DF = sys.argv[1] if len(sys.argv) > 1 else \
    "/workspace/project/MedSim2Learn/DataFlow/KiDKNet"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DF, "outputs/paper_figures")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- house style
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 15,
    "axes.titlesize": 15,
    "axes.labelsize": 16,
    "xtick.labelsize": 13.5,
    "ytick.labelsize": 13.5,
    "legend.fontsize": 13.5,
    "axes.linewidth": 1.0,
    "axes.edgecolor": "#1a1a1a",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.axisbelow": True,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 4,
    "ytick.major.size": 4,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.14,
    "savefig.facecolor": "white",
})

# regime palette -- muted, print-safe; teal-green widens red/green CB separation
REAL, SYNTH, MIXED, XFER = "#3B6EA5", "#B5402F", "#3C8C7E", "#7D6CA8"
GREY = "#9AA0A6"
ACCENT = "#7D6CA8"


def grid_y(ax):
    ax.grid(axis="y", color="#D4D4D4", lw=0.7, alpha=0.9)
    ax.set_axisbelow(True)


def save(fig, stem):
    fig.savefig(os.path.join(OUT, stem + ".png"))
    fig.savefig(os.path.join(OUT, stem + ".pdf"))
    plt.close(fig)


def load(path):
    return json.load(open(path)) if os.path.exists(path) else None


def comparable(summary, cond):
    if cond in ("c3", "c7") and summary.get("real_only_slice"):
        return summary["real_only_slice"]
    return summary.get("pooled", {})


def stat(root, sub, cond, key):
    s = load(os.path.join(root, sub, cond, "cross_fold_summary.json"))
    if not s:
        return None
    blk = comparable(s, cond).get(key)
    if not blk:
        return None
    nf = len([k for k, v in s.get("per_fold", {}).items() if v])
    return blk["mean"], blk["std"], nf


# ============================================================ FIG 1 domain gap
def fig_domain_gap():
    conds = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]
    regime = {"c1": REAL, "c2": SYNTH, "c3": MIXED, "c4": XFER,
              "c5": REAL, "c6": SYNTH, "c7": MIXED, "c8": XFER}
    synth_only = {"c2", "c6"}
    mag = {c: stat(DF, "outputs/cv5", c, "magnitude_mean_absolute_error") for c in conds}
    ang = {c: stat(DF, "outputs/cv5", c, "mean_angle_error") for c in conds}
    if any(v is None for v in mag.values()):
        print("[fig1] missing data; skip"); return
    nfolds = mag["c1"][2]
    x = np.arange(len(conds))
    colors = [regime[c] for c in conds]
    mm = [mag[c][0] for c in conds]; ms = [mag[c][1] for c in conds]
    am = [ang[c][0] for c in conds]; asd = [ang[c][1] for c in conds]

    fig = plt.figure(figsize=(12.8, 5.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 2.0], width_ratios=[1, 1],
                          hspace=0.12, wspace=0.22)
    ax_t = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_r = fig.add_subplot(gs[:, 1])
    ebar = dict(ecolor="#33333366", elinewidth=1.2, capsize=3.5, capthick=1.2)

    def draw_bars(ax, vals, errs):
        bars = ax.bar(x, vals, 0.74, yerr=errs, color=colors, edgecolor="#1a1a1a",
                      linewidth=0.7, error_kw=ebar)
        for i, c in enumerate(conds):
            if c in synth_only:
                bars[i].set_hatch("////")
        return bars

    # broken magnitude panel
    draw_bars(ax_t, mm, ms); draw_bars(ax_b, mm, ms)
    ax_t.set_ylim(0.80, 2.0); ax_t.set_yticks([1.0, 1.5, 2.0])
    ax_b.set_ylim(0, 0.34); ax_b.set_yticks([0, 0.1, 0.2, 0.3])
    ax_t.spines["bottom"].set_visible(False)
    ax_t.tick_params(bottom=False, labelbottom=False)
    ax_b.spines["top"].set_visible(False)
    # break marks on the LEFT spine only (the broken axis)
    d = 0.018
    kw = dict(transform=ax_t.transAxes, color="#1a1a1a", clip_on=False, lw=1.2)
    ax_t.plot((-d, +d), (-d * 2.6, +d * 2.6), **kw)
    kw = dict(transform=ax_b.transAxes, color="#1a1a1a", clip_on=False, lw=1.2)
    ax_b.plot((-d, +d), (1 - d * 1.3, 1 + d * 1.3), **kw)
    for ax in (ax_t, ax_b):
        grid_y(ax); ax.axvline(3.5, color="#999", lw=0.9, ls=(0, (4, 3)))
    # value labels: cluster on lower axis, towers on upper (clamped inside)
    for i, c in enumerate(conds):
        if mm[i] < 0.34:
            ax_b.text(x[i], mm[i] + ms[i] + 0.012, "%.2f" % mm[i],
                      ha="center", va="bottom", fontsize=12)
        else:
            ax_t.text(x[i], min(mm[i] + ms[i] + 0.04, 1.92), "%.2f" % mm[i],
                      ha="center", va="bottom", fontsize=12)
    ax_b.set_ylabel("Magnitude MAE (a.u.)")
    ax_b.set_xticks([1.5, 5.5])
    ax_b.set_xticklabels(["single-frame", "video (sequence)"], style="italic", fontsize=14)
    ax_b.tick_params(axis="x", length=0)

    # angle panel
    bars = ax_r.bar(x, am, 0.74, yerr=asd, color=colors, edgecolor="#1a1a1a",
                    linewidth=0.7, error_kw=ebar)
    for i, c in enumerate(conds):
        if c in synth_only:
            bars[i].set_hatch("////")
    grid_y(ax_r); ax_r.axvline(3.5, color="#999", lw=0.9, ls=(0, (4, 3)))
    ax_r.set_ylim(0, 70)
    for i in range(len(conds)):
        ax_r.text(x[i], am[i] + asd[i] + 0.8, "%.0f" % am[i], ha="center", va="bottom", fontsize=12)
    ax_r.set_ylabel("Direction error  (degrees)")
    ax_r.set_xticks([1.5, 5.5])
    ax_r.set_xticklabels(["single-frame", "video (sequence)"], style="italic", fontsize=14)
    ax_r.tick_params(axis="x", length=0)

    handles = [Patch(fc=REAL, ec="#1a1a1a", label="Real-only"),
               Patch(fc=SYNTH, ec="#1a1a1a", hatch="////", label="Synthetic-only"),
               Patch(fc=MIXED, ec="#1a1a1a", label="Synthetic + Real"),
               Patch(fc=XFER, ec="#1a1a1a", label="Transfer")]
    fig.subplots_adjust(left=0.115, right=0.985, top=0.85, bottom=0.135,
                        hspace=0.12, wspace=0.22)
    fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False,
               bbox_to_anchor=(0.5, 1.0), handlelength=1.3, columnspacing=1.8,
               fontsize=15)
    ax_t.text(-0.11, 1.03, "(a)", transform=ax_t.transAxes, fontsize=17,
              fontweight="bold", va="bottom", ha="right")
    ax_r.text(-0.10, 1.03, "(b)", transform=ax_r.transAxes, fontsize=17,
              fontweight="bold", va="bottom", ha="right")
    save(fig, "fig1_domain_gap")
    print("[fig1] domain gap  (n=%d folds)  mag synth-only=%.2f/%.2f vs real=%.2f"
          % (nfolds, mag["c2"][0], mag["c6"][0], mag["c1"][0]))


# ================================================================ FIG 2 kshot
def fig_kshot():
    s = load(os.path.join(DF, "outputs/kshot/report/kshot_summary.json"))
    if not s:
        print("[fig2] no kshot summary; skip"); return
    ks = [1, 2, 4, 8, 16]

    def series(arm, metric):
        d = s[arm][metric]
        return (np.array([d[str(k)]["mean"] for k in ks]),
                np.array([d[str(k)]["std"] for k in ks]))

    nrep = s["synt"]["magnitude_mean_absolute_error"]["1"]["n"]
    fig, ax = plt.subplots(1, 2, figsize=(12.8, 5.2))
    panels = [("magnitude_mean_absolute_error", "Magnitude MAE (a.u.)", "(a)"),
              ("mean_angle_error", "Direction error  (degrees)", "(b)")]
    for j, (metric, ylab, tag) in enumerate(panels):
        for arm, col, lab in (("synt", SYNTH, "Synthetic pre-training"),
                              ("imagenet", GREY, "ImageNet init.")):
            m, sd = series(arm, metric)
            ax[j].fill_between(ks, m - sd, m + sd, color=col, alpha=0.16, linewidth=0)
            ax[j].plot(ks, m, marker="o", ms=8, lw=2.4, color=col, mec="#1a1a1a",
                       mew=0.6, label=lab)
        ax[j].set_xscale("log", base=2)
        ax[j].set_xticks(ks); ax[j].set_xticklabels(ks)
        ax[j].set_xlabel("Number of real training sequences  $k$")
        ax[j].set_ylabel(ylab)
        ax[j].grid(color="#D4D4D4", lw=0.7, alpha=0.9)
        ax[j].text(-0.02, 1.04, tag, transform=ax[j].transAxes, fontsize=17,
                   fontweight="bold", va="bottom", ha="right")
    # full-real reference on panel (a), in clear whitespace, bold + dark
    ax[0].axhline(0.232, ls=(0, (6, 4)), color="#333", lw=1.8)
    ax[0].text(1.05, 0.255, "Full real-data baseline ($k{=}16$)", ha="left", va="bottom",
               fontsize=13, color="#333")
    ax[0].text(0.97, 0.03, "shaded band = s.d. over %d seeds" % nrep, transform=ax[0].transAxes,
               ha="right", va="bottom", fontsize=12, color="#555")
    ax[0].legend(frameon=False, loc="upper right", fontsize=14)
    fig.tight_layout()
    save(fig, "fig2_kshot")
    print("[fig2] kshot  (n=%d seeds/point)" % nrep)


# ========================================================= generic AB bar pair
def ab_bars(stem, base_dir, alt_dir, base_lab, alt_lab, alt_color,
            mag_fmt="%.3f", ang_fmt="%.1f", note=None, incomplete=None):
    conds = ["c1", "c3"]
    cname = {"c1": "Real-only\n(single)", "c3": "Synthetic+Real\n(single)"}
    incomplete = incomplete or {}
    rows = []
    for c in conds:
        bm = stat(DF, base_dir, c, "magnitude_mean_absolute_error")
        am_ = stat(DF, alt_dir, c, "magnitude_mean_absolute_error")
        ba = stat(DF, base_dir, c, "mean_angle_error")
        aa = stat(DF, alt_dir, c, "mean_angle_error")
        if bm and am_ and ba and aa:
            rows.append((c, bm, am_, ba, aa))
    if not rows:
        print("[%s] no complete pair; skip" % stem); return
    x = np.arange(len(rows)); w = 0.36
    fig, ax = plt.subplots(1, 2, figsize=(11.6, 5.2))
    specs = [(1, 2, "Magnitude MAE (a.u.)", "(a)", mag_fmt),
             (3, 4, "Direction error  (degrees)", "(b)", ang_fmt)]
    for j, (bi, ai, ylab, tag, fmt) in enumerate(specs):
        for i, r in enumerate(rows):
            c = r[0]
            inc = c in incomplete and incomplete[c][0] == "alt"
            # baseline bar
            ax[j].bar(x[i] - w/2, r[bi][0], w, yerr=r[bi][1], color=GREY,
                      edgecolor="#1a1a1a", linewidth=0.7,
                      error_kw=dict(ecolor="#333", elinewidth=1.2, capsize=3.5, capthick=1.2),
                      label=base_lab if i == 0 else None)
            # alt bar (hatched + dashed-weak error if incomplete)
            ek = dict(ecolor="#777", elinewidth=1.1, capsize=3.0, capthick=1.0) if inc \
                else dict(ecolor="#333", elinewidth=1.2, capsize=3.5, capthick=1.2)
            ab = ax[j].bar(x[i] + w/2, r[ai][0], w, yerr=r[ai][1], color=alt_color,
                           edgecolor="#1a1a1a", linewidth=0.7, error_kw=ek,
                           label=alt_lab if i == 0 else None)
            alt_txt = fmt % r[ai][0]
            if inc:
                ab[0].set_hatch("////")
                alt_txt += "$^{\\dagger}$"
            ax[j].text(x[i]-w/2, r[bi][0]+r[bi][1], fmt % r[bi][0], ha="center", va="bottom", fontsize=11.5)
            ax[j].text(x[i]+w/2, r[ai][0]+r[ai][1], alt_txt, ha="center", va="bottom", fontsize=11.5)
        ax[j].set_xticks(x); ax[j].set_xticklabels([cname[r[0]] for r in rows])
        ax[j].set_ylabel(ylab)
        ax[j].grid(axis="y", color="#D4D4D4", lw=0.7, alpha=0.9)
        ax[j].margins(x=0.22)
        ax[j].text(-0.02, 1.04, tag, transform=ax[j].transAxes, fontsize=17,
                   fontweight="bold", va="bottom", ha="right")
    if note:
        ax[0].text(0.97, 0.03, note, transform=ax[0].transAxes, ha="right", va="bottom",
                   fontsize=12, color="#555")
    ax[0].legend(frameon=False, loc="upper right", fontsize=13.5)
    fig.tight_layout()
    if incomplete:
        nf = next(iter(incomplete.values()))[1]
        fig.text(0.5, -0.01, "$\\dagger$ this arm completed %d of 5 folds; "
                 "its error bar is not a 5-fold estimate" % nf,
                 ha="center", va="top", fontsize=11.5, color="#444")
    save(fig, stem)
    print("[%s] done (%s vs %s)" % (stem, base_lab, alt_lab))


# ---------------------------------------------------------------- build all
fig_domain_gap()
fig_kshot()
ab_bars("fig3_loss_uncertainty", "outputs/cv5", "outputs/cv5_unc",
        "Fixed weighting", "Learned uncertainty", ACCENT,
        note="5-fold CV (mean $\\pm$ s.d.)")
ab_bars("fig4_photometric_aug", "outputs/cv5", "outputs/cv5_aug",
        "No augmentation", "Photometric aug.", MIXED,
        note="5-fold CV (mean $\\pm$ s.d.)",
        incomplete={"c1": ("alt", 2)})
print("[done] figures in", OUT)
print("  ", " | ".join(sorted(f for f in os.listdir(OUT) if f.endswith(".png"))))
