#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-condition / cross-fold report for the 8-condition KiDKNet CV.

Read-only consumer of ``<cv-out>/<cond>/cross_fold_summary.json`` (written by
run_cv.py aggregate_condition). Emits, under ``<cv-out>/report``:
  - report_cv_table.csv / report_cv_table.md : one row per condition, mean+-std
    over folds for the headline metrics, using the REAL-COMPARABLE block --
    the real_only slice for the mixed-test conditions (c3/c7), pooled (which is
    already real-only) for the single-domain conditions.
  - report_cv_<metric>.png : grouped bar charts with cross-fold error bars,
    bars coloured by data regime (real / synt->real / mixed / transfer).

Does NOT touch training/eval; purely turns the aggregated JSON into a table and
figures of record for the paper.
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# condition -> (data regime, model mode)
CONDS = [
    ("c1", "real", "single"),
    ("c2", "synt->real", "single"),
    ("c3", "mixed", "single"),
    ("c4", "transfer", "single"),
    ("c5", "real", "sequence"),
    ("c6", "synt->real", "sequence"),
    ("c7", "mixed", "sequence"),
    ("c8", "transfer", "sequence"),
]
# mixed-test conditions: the real-comparable numbers live in the real_only slice
REAL_ONLY = {"c3", "c7"}

# (key, human label, lower_is_better) -- table carries all; charts use CHART_KEYS
METRICS = [
    ("magnitude_mean_absolute_error", "Magnitude MAE (raw units)", True),
    ("magnitude_mean_relative_error", "Magnitude MRE", True),
    ("magnitude_accuracy_10pct", "Magnitude Acc@10%", False),
    ("mean_angle_error", "Mean angle error (deg)", True),
    ("angle_accuracy_5deg", "Angle Acc@5deg", False),
    ("vector_mean_relative_error", "Vector MRE", True),
    ("x_mae", "X MAE", True),
    ("y_mae", "Y MAE", True),
    ("z_mae", "Z MAE", True),
]
CHART_KEYS = {"magnitude_mean_absolute_error", "mean_angle_error", "magnitude_accuracy_10pct"}
REGIME_COLOR = {"real": "#4C72B0", "synt->real": "#C44E52", "mixed": "#55A868", "transfer": "#8172B3"}


def _load(cv_out, cond):
    p = os.path.join(cv_out, cond, "cross_fold_summary.json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _comparable(summary, cond):
    """Return (block, slice_name): real_only slice for mixed conds, else pooled."""
    if cond in REAL_ONLY and summary.get("real_only_slice"):
        return summary["real_only_slice"], "real_only"
    return summary.get("pooled", {}), "pooled"


def _cell(block, key):
    st = block.get(key) if block else None
    return "%.4f+-%.4f" % (st["mean"], st["std"]) if st else "-"


def build_rows(cv_out):
    rows = []
    for cond, regime, mode in CONDS:
        s = _load(cv_out, cond)
        if not s:
            rows.append(dict(cond=cond, regime=regime, mode=mode, block=None, slice="-", folds=0))
            continue
        block, slc = _comparable(s, cond)
        nf = len([k for k, v in s.get("per_fold", {}).items() if v])
        rows.append(dict(cond=cond, regime=regime, mode=mode, block=block, slice=slc, folds=nf))
    return rows


def write_table(rows, out_dir):
    headers = ["cond", "regime", "mode", "folds", "slice"] + [k for k, _, _ in METRICS]
    csv = [",".join(headers)]
    md = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        cells = [r["cond"], r["regime"], r["mode"], str(r["folds"]), r["slice"]]
        cells += [_cell(r["block"], k) for k, _, _ in METRICS]
        csv.append(",".join(cells))
        md.append("| " + " | ".join(cells) + " |")
    with open(os.path.join(out_dir, "report_cv_table.csv"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(csv) + "\n")
    with open(os.path.join(out_dir, "report_cv_table.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")


def write_charts(rows, out_dir):
    n = 0
    for key, label, lower_better in METRICS:
        if key not in CHART_KEYS:
            continue
        labels, means, stds, colors = [], [], [], []
        for r in rows:
            st = r["block"].get(key) if r["block"] else None
            if not st:
                continue
            labels.append("%s\n%s/%s" % (r["cond"], r["regime"], r["mode"][:3]))
            means.append(st["mean"])
            stds.append(st["std"])
            colors.append(REGIME_COLOR.get(r["regime"], "#999999"))
        if not means:
            continue
        plt.figure(figsize=(10, 5))
        x = list(range(len(means)))
        plt.bar(x, means, yerr=stds, capsize=4, color=colors, edgecolor="black", linewidth=0.5)
        plt.xticks(x, labels, fontsize=8)
        plt.ylabel(label)
        arrow = "lower=better" if lower_better else "higher=better"
        plt.title("%s by condition  (real-comparable, mean +/- std over folds; %s)" % (label, arrow))
        handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in REGIME_COLOR.values()]
        plt.legend(handles, list(REGIME_COLOR.keys()), title="data regime", fontsize=8)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "report_cv_%s.png" % key), dpi=130)
        plt.close()
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cross-condition CV report (table + bar charts).")
    ap.add_argument("--cv-out", required=True, help="dir with <cond>/cross_fold_summary.json")
    ap.add_argument("--out-dir", default=None, help="output dir (default: <cv-out>/report)")
    a = ap.parse_args(argv)
    out_dir = a.out_dir or os.path.join(a.cv_out, "report")
    os.makedirs(out_dir, exist_ok=True)

    rows = build_rows(a.cv_out)
    write_table(rows, out_dir)
    n = write_charts(rows, out_dir)
    print("[report_cv] wrote report_cv_table.{csv,md} + %d bar chart(s) to %s" % (n, out_dir))
    # echo the markdown table to stdout for convenience
    with open(os.path.join(out_dir, "report_cv_table.md"), "r", encoding="utf-8") as fh:
        print(fh.read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
