#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""k-shot real-finetune learning curve: the ACTUAL test of the research hypothesis.

The c1-c8 grid trains on ALL real data; it never tests the data-SCARCITY regime
the goal is about ("synthetic as a prior for SCARCE real"). This script does:
for k in K_LIST real training sequences (x REPS random draws), finetune on a FIXED
real test set (cv5 fold0 test) from two starts:
  - arm 'synt'     : synt-pretrained c2/fold0 best_model (LP-FT, base config c4)
  - arm 'imagenet' : ImageNet-only, no transfer (base config c1)
and report real-test magMAE vs k for both arms. If 'synt' beats 'imagenet' at small
k (and the gap shrinks as k grows), synthetic IS a useful scarce-real prior; if not,
synth pretraining carries little transferable signal.

Reuses the proven split helpers (author_paired_splits) and the unchanged main.py
train/evaluate entry (like run_cv). NEEDS GPU for a real run; --dry-run authors the
splits + builds the configs + prints the plan with NO training (validatable now).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from author_paired_splits import _idx, _payload, _ranges  # noqa: E402

KIDKNET = HERE.parent
ROOT = KIDKNET.parent
DF = ROOT / "DataFlow"
K_LIST = [1, 2, 4, 8, 16]
REPS = 3
VAL = 2


def _find_best(cv_out_cond_fold: Path):
    cands = [d for d in cv_out_cond_fold.iterdir()
             if d.is_dir() and (d / "checkpoints" / "best_model.pth").exists()] \
        if cv_out_cond_fold.exists() else []
    if not cands:
        return None
    return max(cands, key=lambda d: d.stat().st_mtime) / "checkpoints" / "best_model.pth"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--real-merged", default=str(DF / "Deform_post/preprocessed/datasets/real"))
    ap.add_argument("--splits-dir", default=str(DF / "KiDKNet/splits/cv5"))
    ap.add_argument("--cv-out", default=str(DF / "KiDKNet/outputs/cv5"))
    ap.add_argument("--out-dir", default=str(DF / "KiDKNet/outputs/kshot"))
    ap.add_argument("--config-dir", default=str(KIDKNET / "configs"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args(argv)

    real_ranges, real_total = _ranges(a.real_merged)
    real_dir = str(Path(a.real_merged).resolve())
    manifest = json.loads((Path(a.splits_dir) / "cv_manifest.json").read_text())
    f0 = manifest["per_fold"][0]
    test_ids = f0["test_ids"]
    pool = f0["train_ids"] + f0["val_ids"]          # everything not in fold0 test
    split_root = Path(a.out_dir) / "splits"
    split_root.mkdir(parents=True, exist_ok=True)

    c2_ckpt = _find_best(Path(a.cv_out) / "c2" / "fold0")
    if c2_ckpt is None and not a.dry_run:
        print("[error] c2/fold0 best_model.pth not found -- run the main sweep first")
        return 2

    arms = {
        "imagenet": {"config": "c1_real_single_convnextL.yaml", "init": None},
        "synt": {"config": "c4_transfer_single_convnextL.yaml", "init": str(c2_ckpt)},
    }
    results = []
    for k in K_LIST:
        if k >= len(pool):
            print("[skip] k=%d >= pool=%d" % (k, len(pool)))
            continue
        for rep in range(REPS):
            rng = random.Random(1000 * k + rep)
            tr = sorted(rng.sample(pool, k))
            rest = [i for i in pool if i not in tr]
            va = sorted(rng.sample(rest, min(VAL, len(rest))))
            payload = _payload(
                _idx(real_ranges, tr), _idx(real_ranges, va), _idx(real_ranges, test_ids),
                tr, va, test_ids, real_total, real_dir,
                "kshot_k%d_r%d" % (k, rep), require_full_coverage=False)
            payload["split_by"] = "sequence"
            sp = split_root / ("k%d_r%d.json" % (k, rep))
            sp.write_text(json.dumps(payload, indent=2))

            for arm, spec in arms.items():
                base = yaml.safe_load((Path(a.config_dir) / spec["config"]).read_text())
                fold_out = Path(a.out_dir) / ("k%d_r%d_%s" % (k, rep, arm))
                cfg = copy.deepcopy(base)
                cfg.setdefault("general", {})["output_dir"] = str(fold_out)
                cfg["general"]["result_dir"] = str(fold_out / "evaluation")
                cfg.setdefault("data", {})["split_file"] = str(sp)
                if spec["init"]:
                    cfg.setdefault("training", {}).setdefault("transfer", {})["enabled"] = True
                    cfg["training"]["transfer"]["init_from_checkpoint"] = spec["init"]
                print("[plan] k=%d rep=%d arm=%s | train=%d ids | init=%s | out=%s"
                      % (k, rep, arm, k, "c2" if spec["init"] else "imagenet", fold_out))
                if a.dry_run:
                    continue
                fold_out.mkdir(parents=True, exist_ok=True)
                cfg_path = fold_out / "_run_config.yaml"
                cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
                rc = subprocess.run([a.python, "main.py", "--mode", "train", "--config", str(cfg_path)],
                                    cwd=str(KIDKNET)).returncode
                if rc != 0:
                    print("[fail] train k%d r%d %s rc=%d" % (k, rep, arm, rc)); continue
                exp = _find_best(fold_out)
                if exp:
                    subprocess.run([a.python, "main.py", "--mode", "evaluate", "--config",
                                    str(cfg_path), "--model", exp.parent.parent.name], cwd=str(KIDKNET))
                reps = sorted(fold_out.glob("evaluation/*/reports/evaluation_report.json"))
                if reps:
                    rep_j = json.loads(reps[-1].read_text())
                    mae = rep_j.get("magnitude_mean_absolute_error")
                    results.append({"k": k, "rep": rep, "arm": arm, "magMAE": mae})
                    print("[done] k=%d rep=%d arm=%s magMAE=%.4f" % (k, rep, arm, mae or -1))

    if not a.dry_run and results:
        out = Path(a.out_dir) / "kshot_results.json"
        out.write_text(json.dumps(results, indent=2))
        print("[kshot] wrote %s (%d runs)" % (out, len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
