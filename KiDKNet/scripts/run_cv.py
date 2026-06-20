#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-validation orchestration driver for the 8-condition KiDKNet matrix.

Realizes decisions #3/#4/#5 on top of the per-fold splits authored by
``author_cv_splits.py`` (``splits/cv5/fold{f}/{real,c2_synt2real,c3_mixed}_split.json``):

- #3 (shared K-fold): runs every requested condition over the SAME fold
  partition. Per (condition, fold) it deep-copies the condition's base config and
  overrides only ``data.split_file`` -> the fold split, ``general.output_dir`` /
  ``general.result_dir`` -> a fold-scoped directory, then invokes the unchanged
  ``main.py`` entry as an isolated subprocess (crash isolation + resumability for
  a multi-day GPU sweep).
- #5 (init pinning): C4/C8 are transfer conditions; their
  ``training.transfer.init_from_checkpoint`` is auto-pinned to the SAME fold's
  C2/C6 ``checkpoints/best_model.pth`` (never a cross-fold checkpoint).
- #4 (domain slices): handled inside ``evaluate.py``; this driver aggregates the
  real-only slice alongside the pooled metric when building cross-fold summaries.

Condition -> (base config, fold split kind, transfer init source):
    c1 real single        real   -            c5 real sequence       real   -
    c2 synt->real single  c2     -            c6 synt->real sequence c2     -
    c3 mixed single       c3     -            c7 mixed sequence      c3     -
    c4 transfer single    real   <- c2        c8 transfer sequence   real   <- c6

The run order keeps each transfer condition AFTER its init source within a fold.
Training requires CUDA, so a full run happens on the server; ``--dry-run`` builds
and validates the entire plan locally (split files exist, configs well-formed,
init dependencies resolvable) without launching anything.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import subprocess
import sys
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("run_cv")

# condition -> base config filename, fold split kind, transfer init source
CONDITIONS: Dict[str, Dict[str, Optional[str]]] = {
    "c1": {"config": "c1_real_single_convnextL.yaml", "split": "real", "init": None},
    "c2": {"config": "c2_synt2real_single_convnextL.yaml", "split": "c2", "init": None},
    "c3": {"config": "c3_mixed_single_convnextL.yaml", "split": "c3", "init": None},
    "c4": {"config": "c4_transfer_single_convnextL.yaml", "split": "real", "init": "c2"},
    "c5": {"config": "c5_real_sequence_tcn_convnextL.yaml", "split": "real", "init": None},
    "c6": {"config": "c6_synt2real_sequence_tcn_convnextL.yaml", "split": "c2", "init": None},
    "c7": {"config": "c7_mixed_sequence_tcn_convnextL.yaml", "split": "c3", "init": None},
    "c8": {"config": "c8_transfer_sequence_tcn_convnextL.yaml", "split": "real", "init": "c6"},
}

# fold split kind -> the per-fold split filename authored by author_cv_splits.py
SPLIT_FILES = {
    "real": "real_split.json",
    "c2": "c2_synt2real_split.json",
    "c3": "c3_mixed_split.json",
}

# run order: each transfer condition follows its init source within a fold
DEFAULT_ORDER = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]

KIDKNET_ROOT = Path(__file__).resolve().parent.parent
# DataFlow sits beside the KiDKNet checkout (workspace/DataFlow). Deriving the
# local defaults from the repo root keeps them portable (no hardcoded drive);
# the server operator overrides --splits-dir / --cv-out with remote paths.
_DATAFLOW = KIDKNET_ROOT.parent / "DataFlow"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _dump_yaml(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(obj, handle, sort_keys=False)


def _find_experiment(fold_out: Path) -> Optional[Path]:
    """Newest completed experiment dir under *fold_out* (has best_model.pth)."""
    if not fold_out.exists():
        return None
    candidates = [
        d for d in fold_out.iterdir()
        if d.is_dir()
        and (d / "checkpoints" / "best_model.pth").exists()
        and (d / "experimentConfig.yaml").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def _best_model(exp_dir: Path) -> Path:
    return exp_dir / "checkpoints" / "best_model.pth"


def build_run_config(
    cond: str, base_cfg: dict, fold: int, splits_dir: Path, cv_out: Path,
    init_ckpt: Optional[str], augment: bool = False,
) -> Tuple[dict, Path, Path]:
    """Return (overridden config, fold output dir, fold split path) for one run."""
    spec = CONDITIONS[cond]
    split_path = splits_dir / f"fold{fold}" / SPLIT_FILES[str(spec["split"])]
    fold_out = cv_out / cond / f"fold{fold}"

    cfg = copy.deepcopy(base_cfg)
    cfg.setdefault("general", {})
    cfg.setdefault("data", {})
    cfg["data"]["split_file"] = str(split_path)
    cfg["general"]["output_dir"] = str(fold_out)
    cfg["general"]["result_dir"] = str(fold_out / "evaluation")

    if spec["init"] is not None:
        transfer = cfg.setdefault("training", {}).setdefault("transfer", {})
        if not transfer.get("enabled"):
            raise ValueError(
                f"{cond} has an init source {spec['init']} but its config "
                "training.transfer.enabled is not true"
            )
        # init_ckpt may be a real path or a PENDING marker (dry-run); store as-is.
        transfer["init_from_checkpoint"] = init_ckpt

    if augment:
        # Phase-0: train-only LABEL-SAFE photometric augmentation (applied by
        # dknet.data.transforms.get_transforms(train=True)). Use a separate
        # --cv-out so the no-aug baselines are preserved for the A/B comparison.
        aug = cfg.setdefault("data", {}).setdefault("augmentation", {})
        aug["photometric"] = {
            "enabled": True, "p": 0.8,
            "brightness": 0.3, "contrast": 0.3, "saturation": 0.3, "hue": 0.05,
            "blur_p": 0.2, "blur_sigma": [0.1, 1.5],
            "gamma": [0.8, 1.2], "noise_std": 0.02,
        }
    return cfg, fold_out, split_path


def _resolve_init_ckpt(
    cond: str, fold: int, cv_out: Path, planned: set, dry_run: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a transfer condition's init checkpoint for this fold.

    Returns (init_ckpt_or_marker, problem). ``problem`` is None when resolvable.
    """
    src = CONDITIONS[cond]["init"]
    if src is None:
        return None, None
    dep_fold_out = cv_out / str(src) / f"fold{fold}"
    dep_exp = _find_experiment(dep_fold_out)
    if dep_exp is not None:
        return str(_best_model(dep_exp)), None
    # dependency not trained yet
    if (src, fold) in planned:
        marker = f"<PENDING {src}/fold{fold} best_model.pth (runs earlier in this plan)>"
        return marker, None
    problem = (
        f"init source {src}/fold{fold} has no trained best_model.pth and is not "
        f"in this run's plan; train {src} first or include it in --conditions"
    )
    if dry_run:
        return f"<MISSING {src}/fold{fold}>", problem
    return None, problem


def _run_subprocess(python: str, mode: str, cfg_path: Path, model: Optional[str]) -> int:
    cmd = [python, "main.py", "--mode", mode, "--config", str(cfg_path)]
    if model is not None:
        cmd += ["--model", model]
    logger.info("RUN: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(KIDKNET_ROOT)).returncode


def _numeric_metrics(report: dict) -> Dict[str, float]:
    """Top-level numeric metrics from an evaluation_report.json."""
    out: Dict[str, float] = {}
    for key, value in report.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def _find_eval_report(fold_out: Path) -> Optional[dict]:
    eval_root = fold_out / "evaluation"
    if not eval_root.exists():
        return None
    reports = sorted(eval_root.glob("*/reports/evaluation_report.json"),
                     key=lambda p: p.stat().st_mtime)
    if not reports:
        return None
    with open(reports[-1], "r", encoding="utf-8") as handle:
        return json.load(handle)


def aggregate_condition(cond: str, folds: List[int], cv_out: Path) -> Optional[dict]:
    """Collect per-fold test metrics -> mean/std; write cross_fold_summary.json."""
    pooled: Dict[str, List[float]] = {}
    real_only: Dict[str, List[float]] = {}
    per_fold: Dict[str, Any] = {}
    for fold in folds:
        report = _find_eval_report(cv_out / cond / f"fold{fold}")
        if report is None:
            per_fold[f"fold{fold}"] = None
            continue
        flat = _numeric_metrics(report)
        per_fold[f"fold{fold}"] = flat
        for key, value in flat.items():
            pooled.setdefault(key, []).append(value)
        slice_block = report.get("test_domain_slices", {})
        real_metrics = slice_block.get("real_only", {}).get("metrics", {})
        for key, value in real_metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                real_only.setdefault(key, []).append(float(value))

    if not pooled:
        logger.warning("[%s] no fold reports found; skipping summary", cond)
        return None

    def _stats(values: List[float]) -> Dict[str, float]:
        return {"mean": mean(values), "std": pstdev(values), "n": len(values)}

    summary = {
        "condition": cond,
        "folds": folds,
        "pooled": {k: _stats(v) for k, v in sorted(pooled.items())},
        "real_only_slice": {k: _stats(v) for k, v in sorted(real_only.items())},
        "per_fold": per_fold,
    }
    out_path = cv_out / cond / "cross_fold_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    logger.info("[%s] wrote %s", cond, out_path)
    return summary


def run(args: argparse.Namespace) -> int:
    splits_dir = Path(args.splits_dir)
    cv_out = Path(args.cv_out)
    config_dir = Path(args.config_dir)
    python = args.python or sys.executable

    manifest_path = splits_dir / "cv_manifest.json"
    if not manifest_path.exists():
        logger.error("cv_manifest.json not found in %s (run author_cv_splits.py)", splits_dir)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    n_folds = int(manifest["folds"])
    folds = args.folds if args.folds else list(range(n_folds))
    conditions = [c for c in DEFAULT_ORDER if c in (args.conditions or DEFAULT_ORDER)]
    planned = {(c, f) for c in conditions for f in folds}

    logger.info("CV plan: conditions=%s folds=%s (manifest folds=%d)", conditions, folds, n_folds)
    problems: List[str] = []
    failures: List[str] = []

    for fold in folds:
        for cond in conditions:
            spec = CONDITIONS[cond]
            base_path = config_dir / str(spec["config"])
            if not base_path.exists():
                problems.append(f"{cond}/fold{fold}: base config missing: {base_path}")
                continue
            base_cfg = _load_yaml(base_path)
            init_ckpt, problem = _resolve_init_ckpt(cond, fold, cv_out, planned, args.dry_run)
            if problem:
                problems.append(f"{cond}/fold{fold}: {problem}")
                if not args.dry_run:
                    continue
            cfg, fold_out, split_path = build_run_config(
                cond, base_cfg, fold, splits_dir, cv_out, init_ckpt,
                augment=args.augment,
            )
            if args.wandb:
                cfg["wandb"] = {
                    "enabled": True,
                    "project": args.wandb_project,
                    "entity": args.wandb_entity,
                    "group": cond,
                    "name": f"{cond}_fold{fold}",
                    "mode": args.wandb_mode,
                }
            split_ok = split_path.exists()
            if not split_ok:
                problems.append(f"{cond}/fold{fold}: split file missing: {split_path}")

            if args.dry_run:
                logger.info(
                    "PLAN %s fold%d | split=%s(%s) | out=%s | init=%s",
                    cond, fold, SPLIT_FILES[str(spec["split"])],
                    "ok" if split_ok else "MISSING", fold_out, init_ckpt,
                )
                continue

            if not split_ok:
                continue
            if args.skip_existing and _find_experiment(fold_out) is not None \
                    and _find_eval_report(fold_out) is not None:
                logger.info("SKIP %s fold%d (already complete)", cond, fold)
                continue

            cfg_path = fold_out / "_run_config.yaml"
            _dump_yaml(cfg, cfg_path)
            rc = _run_subprocess(python, "train", cfg_path, None)
            if rc != 0:
                failures.append(f"{cond}/fold{fold}: train rc={rc}")
                continue
            exp = _find_experiment(fold_out)
            if exp is None:
                failures.append(f"{cond}/fold{fold}: no experiment produced")
                continue
            rc_eval = _run_subprocess(python, "evaluate", cfg_path, exp.name)
            if rc_eval != 0:
                failures.append(f"{cond}/fold{fold}: evaluate rc={rc_eval}")

    if not args.dry_run:
        for cond in conditions:
            aggregate_condition(cond, folds, cv_out)

    if problems:
        logger.warning("PLAN PROBLEMS (%d):", len(problems))
        for p in problems:
            logger.warning("  - %s", p)
    if failures:
        logger.error("RUN FAILURES (%d):", len(failures))
        for f in failures:
            logger.error("  - %s", f)

    if args.dry_run:
        logger.info("Dry-run complete: %d planned runs, %d problem(s).",
                    len(planned), len(problems))
    return 1 if (problems or failures) else 0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KiDKNet 8-condition CV orchestration driver.")
    p.add_argument("--splits-dir", default=str(_DATAFLOW / "KiDKNet" / "splits" / "cv5"),
                   help="dir with cv_manifest.json + fold{f}/ splits")
    p.add_argument("--cv-out", default=str(_DATAFLOW / "KiDKNet" / "outputs" / "cv5"),
                   help="root for fold-scoped training/eval outputs + summaries")
    p.add_argument("--config-dir", default=str(KIDKNET_ROOT / "configs"),
                   help="dir holding the c1..c8 base configs")
    p.add_argument("--conditions", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                   default=None, help="comma list subset of c1..c8 (default all)")
    p.add_argument("--folds", type=lambda s: [int(x) for x in s.split(",") if x.strip() != ""],
                   default=None, help="comma list of fold indices (default all)")
    p.add_argument("--python", default=None, help="python interpreter for subprocess (default sys.executable)")
    p.add_argument("--skip-existing", action="store_true",
                   help="skip a (cond,fold) that already has a completed experiment + eval report")
    p.add_argument("--augment", action="store_true",
                   help="enable train-only LABEL-SAFE photometric augmentation (Phase-0)")
    p.add_argument("--dry-run", action="store_true",
                   help="build + validate the full plan without training/evaluating")
    p.add_argument("--wandb", action="store_true",
                   help="enable Weights & Biases tracking for every (cond,fold) run")
    p.add_argument("--wandb-project", default="kidknet-cv5", help="W&B project name")
    p.add_argument("--wandb-entity", default=None, help="W&B entity (team or user)")
    p.add_argument("--wandb-mode", default="online",
                   choices=["online", "offline", "disabled"], help="W&B mode")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
