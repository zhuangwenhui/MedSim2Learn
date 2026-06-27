#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Two architecture schematics (code-accurate), two-column (full-page-width) size.
Box widths are MEASURED from the rendered text -> text never overflows; few, short
boxes per row -> readable at column width; no line crosses any text; dashed callout
auto-sized to its content. Colour language borrowed from Figure_2_wf.pdf.

  arch_single.png/.pdf     per-frame model (c1-c4)
  arch_sequence.png/.pdf    video-sequence MS-TCN model (c5-c8)
Run:  python arch_figures.py [OUT_DIR]
"""
from __future__ import annotations
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else \
    "/workspace/project/MedSim2Learn/DataFlow/KiDKNet/outputs/paper_figures"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.12,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})
CONV, ACT, GREEN, DROP = "#A9C6E6", "#F2C089", "#B6D2A1", "#DBDBDB"
LIGHT, P_ENC, P_HEAD = "#EFF2F6", "#DCE7F3", "#F6E7D2"
EC = "#2f2f2f"
PADX = 1.9


def measure_w(ax, fig, text, fs, bold):
    t = ax.text(0, 0, text, fontsize=fs, fontweight="bold" if bold else "normal", clip_on=False)
    fig.canvas.draw()
    bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    w = abs(inv.transform((bb.x1, 0))[0] - inv.transform((bb.x0, 0))[0])
    t.remove()
    return w


def wrap_to_width(ax, fig, text, max_w, fs, bold=False):
    """Greedily wrap `text` so every line fits in max_w (data units). Returns (str, n_lines)."""
    words = [w for w in text.split(" ") if w]
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if not cur or measure_w(ax, fig, trial, fs, bold) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return "\n".join(lines), len(lines)


def rbox(ax, cx, cy, w, h, text, fc, fs, bold=False):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                 boxstyle="round,pad=0.02,rounding_size=1.4", fc=fc, ec=EC, lw=1.1, clip_on=False))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", linespacing=1.3, clip_on=False)


def harrow(ax, x1, x2, cy, lw=1.5):
    ax.add_patch(FancyArrowPatch((x1, cy), (x2, cy), arrowstyle="-|>",
                 mutation_scale=12, lw=lw, color="#333", shrinkA=0, shrinkB=0, clip_on=False))


def panel(ax, x0, x1, y0, y1, fc, title, tfs):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                 boxstyle="round,pad=0.02,rounding_size=2", fc=fc, ec="#9aa6b4", lw=1.1,
                 zorder=0, clip_on=False))
    ax.text((x0 + x1) / 2, y1 + 1.3, title, ha="center", va="bottom", fontsize=tfs,
            fontweight="bold", color="#33445a", clip_on=False)


def flow(ax, fig, boxes, x0, cy, h, gap, fs, sh_fs, sh_dy):
    pos, x = [], x0
    for i, b in enumerate(boxes):
        w = measure_w(ax, fig, b["t"], b.get("fs", fs), b.get("bold", False)) + 2 * PADX
        cx = x + w / 2
        rbox(ax, cx, cy, w, h, b["t"], b["fc"], b.get("fs", fs), b.get("bold", False))
        pos.append((cx, x, x + w))
        if i < len(boxes) - 1:
            harrow(ax, x + w, x + w + gap, cy)
            if b.get("shape"):
                ax.text(x + w + gap / 2, cy - h / 2 - sh_dy, b["shape"], ha="center", va="top",
                        fontsize=sh_fs, color="#555", style="italic")
        x += w + gap
    return pos


# ===================================================== FIG A : single-frame
def fig_single():
    fig, ax = plt.subplots(figsize=(9.4, 3.35))
    ax.set_xlim(0, 100); ax.set_ylim(0, 35.6); ax.axis("off")
    cy, h = 21, 11
    boxes = [
        dict(t="Endoscopic\nframe", fc=LIGHT, shape="3 x 256 x 256"),
        dict(t="ConvNeXt-Large\nfine-tuned", fc=CONV, bold=True, shape="1536 x 8 x 8"),
        dict(t="Global\navg-pool", fc=LIGHT, shape="1536"),
        dict(t="MLP head\n4 FC layers", fc=ACT, bold=True, shape="3"),
        dict(t="Force\n(Fx, Fy, Fz)", fc=LIGHT, bold=True),
    ]
    pos = flow(ax, fig, boxes, x0=3, cy=cy, h=h, gap=3.2, fs=10, sh_fs=8.4, sh_dy=1.9)
    py0, py1 = cy - h / 2 - 4.4, cy + h / 2 + 1.4
    panel(ax, pos[0][1] - 1.5, pos[2][2] + 1.5, py0, py1, P_ENC, "Feature extractor", 10.5)
    panel(ax, pos[3][1] - 1.5, pos[4][2] + 1.5, py0, py1, P_HEAD, "Regression head", 10.5)
    note, _ = wrap_to_width(ax, fig,
        "ConvNeXt-Large is ImageNet-pretrained. MLP head = 4 fully-connected layers "
        "(1536 → 1024 → 512 → 256 → 3); each hidden FC = Linear + BatchNorm + ReLU + Dropout(0.1).",
        pos[4][2] - pos[0][1], 8.2, bold=False)
    ax.text(pos[0][1] - 1.5, py0 - 2.0, note, ha="left", va="top",
            fontsize=8.2, color="#555", style="italic", linespacing=1.45)
    ax.text(3, 34.0, "Per-frame force model   (conditions c1-c4)", ha="left", va="center",
            fontsize=12, fontweight="bold", color="#222")
    fig.savefig(os.path.join(OUT, "arch_single.png")); fig.savefig(os.path.join(OUT, "arch_single.pdf"))
    plt.close(fig); print("[arch_single] right=%.1f" % pos[-1][2])


# ===================================================== FIG B : sequence
def fig_sequence():
    fig, ax = plt.subplots(figsize=(9.4, 4.95))
    ax.set_xlim(0, 100); ax.set_ylim(0, 52.7); ax.axis("off")
    cy, h = 39, 11
    boxes = [
        dict(t="Video clip\nT frames", fc=LIGHT, shape="T x 3 x 256 x 256"),
        dict(t="ConvNeXt-Large\nfrozen", fc=CONV, bold=True, shape="T x 1536"),
        dict(t="TCN\nStage 1", fc=ACT, bold=True, shape="T x 3"),
        dict(t="TCN\nStage 2", fc=ACT, bold=True, shape="T x 3"),
        dict(t="TCN\nStage 3", fc=ACT, bold=True, shape="T x 3"),
        dict(t="Per-frame\nforce", fc=LIGHT, bold=True),
    ]
    pos = flow(ax, fig, boxes, x0=3, cy=cy, h=h, gap=3.2, fs=10, sh_fs=8.4, sh_dy=1.9)
    py0, py1 = cy - h / 2 - 1.4, cy + h / 2 + 1.4
    panel(ax, pos[0][1] - 1.5, pos[1][2] + 1.5, py0, py1, P_ENC, "Frame encoder (frozen)", 10.5)
    panel(ax, pos[2][1] - 1.5, pos[5][2] + 1.5, py0, py1, P_HEAD, "Temporal head (MS-TCN)", 10.5)
    ax.text((pos[2][0] + pos[4][0]) / 2, cy - h / 2 - 5.4,
            "deep supervision:  every stage output (T x 3) is supervised",
            ha="center", va="center", fontsize=8.4, color="#7a5a2a", style="italic")

    # ---- detail callout (own row): dilated residual layer
    dboxes = [
        dict(t="in\nT x 64", fc=LIGHT),
        dict(t="Dilated\nConv 1D", fc=CONV),
        dict(t="ReLU", fc=ACT),
        dict(t="1x1\nConv", fc=GREEN),
        dict(t="Dropout", fc=DROP),
    ]
    dcy, dh, dfs = 7.5, 8.5, 9.0
    dp = flow(ax, fig, dboxes, x0=12, cy=dcy, h=dh, gap=2.8, fs=dfs, sh_fs=8, sh_dy=0)
    addx = dp[-1][2] + 4.4
    ax.add_patch(Circle((addx, dcy), 1.8, fc="white", ec=EC, lw=1.1, clip_on=False))
    ax.text(addx, dcy, "+", ha="center", va="center", fontsize=12, fontweight="bold", clip_on=False)
    harrow(ax, dp[-1][2], addx - 1.8, dcy)
    y_skip = dcy + dh / 2 + 2.3
    in_x = dp[0][0]
    ax.plot([in_x, in_x], [dcy + dh / 2, y_skip], color="#666", lw=1.1, clip_on=False)
    ax.plot([in_x, addx], [y_skip, y_skip], color="#666", lw=1.1, clip_on=False)
    ax.add_patch(FancyArrowPatch((addx, y_skip), (addx, dcy + 1.8), arrowstyle="-|>",
                 mutation_scale=11, lw=1.1, color="#666", clip_on=False))
    ax.text((in_x + addx) / 2, y_skip + 0.8, "residual connection", ha="center", va="bottom",
            fontsize=7.8, color="#666", style="italic", clip_on=False)
    bx0, bx1 = dp[0][1] - 4.0, addx + 4.0
    dtitle, nlines = wrap_to_width(ax, fig,
        "Repeating unit inside each TCN stage  —  dilated residual layer "
        "(x10 per stage, k=3 causal, dilation d = 1, 2, 4, ..., 512)",
        (bx1 - bx0) - 7.0, 8.6, bold=True)
    lh = 2.5
    title_cy = y_skip + 2.6 + (nlines * lh) / 2          # title block sits above the residual elbow
    by0, by1 = dcy - dh / 2 - 2.4, title_cy + (nlines * lh) / 2 + 1.7
    ax.add_patch(FancyBboxPatch((bx0, by0), bx1 - bx0, by1 - by0,
                 boxstyle="round,pad=0.02,rounding_size=2", fc="#F7F8FA", ec="#8a93a0",
                 lw=1.1, ls=(0, (5, 3)), zorder=0, clip_on=False))
    ax.text((bx0 + bx1) / 2, title_cy, dtitle, ha="center", va="center",
            fontsize=8.6, fontweight="bold", color="#33445a", linespacing=1.35, clip_on=False)

    ax.text(3, 50.5, "Video-sequence force model   (conditions c5-c8)", ha="left", va="center",
            fontsize=12, fontweight="bold", color="#222")
    fig.savefig(os.path.join(OUT, "arch_sequence.png")); fig.savefig(os.path.join(OUT, "arch_sequence.pdf"))
    plt.close(fig); print("[arch_sequence] right=%.1f" % pos[-1][2])


fig_single()
fig_sequence()
print("[done] ->", OUT)
