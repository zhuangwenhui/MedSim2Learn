#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-condition / cross-fold report for the KiDKNet CV (+ transfer race).

Read-only consumer of ``<cv-out>/<cond>/cross_fold_summary.json`` (written by
run_cv.py aggregate_condition). DISCOVERS whichever conditions are present, so
it picks up the c4 transfer-race variants (c4ft/c4dl/c4sg/c4fz) automatically
once they finish. Emits, under ``<cv-out>/report``:
  - report_cv_table.csv / .md : one row per condition, mean+-std over folds for
    the headline metrics, REAL-COMPARABLE (real_only slice for the mixed-test
    conditions c3/c7, pooled -- already real-only -- for the rest).
  - report_cv_<metric>.png : bar charts over all conditions, error bars.
  - report_race_table.md + report_race_<metric>.png : focused transfer-strategy
    comparison (scratch c1, synt-source c2, LP-FT c4, and the 4 race variants),
    with the scratch baseline drawn as a reference line.

Does NOT touch training/eval; purely turns aggregated JSON into figures of record.
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# cond -> (data regime, model mode, transfer strategy)
DESCRIPTORS = {
    "c1": ("real", "single", "scratch"),
    "c2": ("synt->real", "single", "-"),
    "c3": ("mixed", "single", "-"),
    "c4": ("transfer", "single", "LP-FT"),
    "c5": ("real", "sequence", "scratch"),
    "c6": ("synt->real", "sequence", "-"),
    "c7": ("mixed", "sequence", "-"),
    "c8": ("transfer", "sequence", "init+FT"),
    "c4ft": ("transfer", "single", "full-FT"),
    "c4dl": ("transfer", "single", "disc-LR"),
    "c4sg": ("transfer", "single", "surgical"),
    "c4fz": ("transfer", "single", "frozen-head"),
}
ORDER = ["c1", "c2", "c3", "c4", "c4ft", "c4dl", "c4sg", "c4fz", "c5", "c6", "c7", "c8"]
REAL_ONLY = {"c3", "c7"}                       # mixed test -> use real_only slice
RACE_ORDER = ["c1", "c2", "c4", "c4ft", "c4dl", "c4sg", "c4fz"]  # transfer-strategy race
REGIME_COLOR = {"real": "#4C72B0", "synt->real": "#C44E52", "mixed": "#55A868", "transfer": "#8172B3"}

METRICS = [
    ("magnitude_mean_absolute_error", "Magnitude MAE (raw units)", True),
    ("magnitude_mean_relative_error", "Magnitude MRE", True),
    ("magnitude_accuracy_10pct", "Magnitude Acc@10%", False),
    ("mean_angle_error", "Mean angle error (deg)", True),
    ("angle_accuracy_5deg", "Angle Acc@5deg", False),
    ("vector_mean_relative_error", "Vector MRE", True),
    ("x_mae", "X MAE", True), ("y_mae", "Y MAE", True), ("z_mae", "Z MAE", True),
]
CHART_KEYS = {"magnitude_mean_absolute_error", "mean_angle_error", "magnitude_accuracy_10pct"}


def _load(cv_out, cond):
    p = os.path.join(cv_out, cond, "cross_fold_summary.json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _comparable(summary, cond):
    if cond in REAL_ONLY and summary.get("real_only_slice"):
        return summary["real_only_slice"], "real_only"
    return summary.get("pooled", {}), "pooled"


def _cell(block, key):
    st = block.get(key) if block else None
    return "%.4f+-%.4f" % (st["mean"], st["std"]) if st else "-"


def _discover(cv_out):
    """All conds with a summary on disk, in ORDER (unknowns appended)."""
    present = [c for c in os.listdir(cv_out)
               if os.path.exists(os.path.join(cv_out, c, "cross_fold_summary.json"))]
    ordered = [c for c in ORDER if c in present] + sorted(c for c in present if c not in ORDER)
    return ordered


def _rows(cv_out, conds):
    rows = []
    for cond in conds:
        regime, mode, strat = DESCRIPTORS.get(cond, ("?", "?", "?"))
        s = _load(cv_out, cond)
        if not s:
            rows.append(dict(cond=cond, regime=regime, mode=mode, strat=strat,
                             block=None, slice="-", folds=0))
            continue
        block, slc = _comparable(s, cond)
        nf = len([k for k, v in s.get("per_fold", {}).items() if v])
        rows.append(dict(cond=cond, regime=regime, mode=mode, strat=strat,
                         block=block, slice=slc, folds=nf))
    return rows


def _write_table(rows, out_dir, base, extra_col=None):
    hdr = ["cond", "regime", "mode"] + ([extra_col] if extra_col else []) + \
          ["folds", "slice"] + [k for k, _, _ in METRICS]
    csv = [",".join(hdr)]
    md = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for r in rows:
        cells = [r["cond"], r["regime"], r["mode"]]
        if extra_col:
            cells.append(r["strat"])
        cells += [str(r["folds"]), r["slice"]] + [_cell(r["block"], k) for k, _, _ in METRICS]
        csv.append(",".join(cells))
        md.append("| " + " | ".join(cells) + " |")
    with open(os.path.join(out_dir, base + ".csv"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(csv) + "\n")
    with open(os.path.join(out_dir, base + ".md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")


def _bar(rows, out_dir, prefix, label_fn, color_fn, baseline=None, title_suffix=""):
    n = 0
    for key, label, lower in METRICS:
        if key not in CHART_KEYS:
            continue
        labels, means, stds, colors = [], [], [], []
        for r in rows:
            st = r["block"].get(key) if r["block"] else None
            if not st:
                continue
            labels.append(label_fn(r))
            means.append(st["mean"]); stds.append(st["std"]); colors.append(color_fn(r))
        if not means:
            continue
        plt.figure(figsize=(10, 5))
        x = list(range(len(means)))
        plt.bar(x, means, yerr=stds, capsize=4, color=colors, edgecolor="black", linewidth=0.5)
        if baseline is not None:
            bl = next((r["block"].get(key) for r in rows
                       if r["cond"] == baseline and r["block"] and r["block"].get(key)), None)
            if bl:
                plt.axhline(bl["mean"], ls="--", color="#888888", lw=1)
                plt.text(len(means) - 0.5, bl["mean"], " %s baseline" % baseline,
                         va="bottom", ha="right", fontsize=8, color="#666666")
        plt.xticks(x, labels, fontsize=8)
        plt.ylabel(label)
        plt.title("%s%s  (real-comparable, mean +/- std; %s)"
                  % (label, title_suffix, "lower=better" if lower else "higher=better"))
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "%s_%s.png" % (prefix, key)), dpi=130)
        plt.close()
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cross-condition CV report + transfer race.")
    ap.add_argument("--cv-out", required=True)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    out_dir = a.out_dir or os.path.join(a.cv_out, "report")
    os.makedirs(out_dir, exist_ok=True)

    present = _discover(a.cv_out)

    # --- main report over all present conditions ---
    main_rows = _rows(a.cv_out, present)
    _write_table(main_rows, out_dir, "report_cv_table")
    n_main = _bar(main_rows, out_dir, "report_cv",
                  label_fn=lambda r: "%s\n%s/%s" % (r["cond"], r["regime"], r["mode"][:3]),
                  color_fn=lambda r: REGIME_COLOR.get(r["regime"], "#999999"))

    # --- focused transfer-strategy race (only conds present) ---
    race_conds = [c for c in RACE_ORDER if c in present]
    n_race = 0
    if any(c in race_conds for c in ("c4ft", "c4dl", "c4sg", "c4fz")):
        race_rows = _rows(a.cv_out, race_conds)
        _write_table(race_rows, out_dir, "report_race_table", extra_col="strategy")
        n_race = _bar(race_rows, out_dir, "report_race",
                      label_fn=lambda r: "%s\n%s" % (r["cond"], r["strat"]),
                      color_fn=lambda r: REGIME_COLOR.get(r["regime"], "#999999"),
                      baseline="c1", title_suffix=" -- transfer race")

    print("[report_cv] %d conditions present: %s" % (len(present), " ".join(present)))
    print("[report_cv] main: report_cv_table.{csv,md} + %d charts" % n_main)
    if n_race:
        print("[report_cv] race: report_race_table.{csv,md} + %d charts" % n_race)
    else:
        print("[report_cv] race: variants not finished yet -- skipped race section")
    with open(os.path.join(out_dir, "report_cv_table.md"), "r", encoding="utf-8") as fh:
        print(fh.read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
