#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main script for the KiDKNet framework.
This script provides a command-line interface for training,
evaluating models and splitting datasets.
"""
from __future__ import annotations

import os
import sys
import argparse
import yaml
import logging
import time
import traceback
from pathlib import Path

# Ensure dknet package is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


DEFAULT_CUDA_ALLOC_CONF = (
    "max_split_size_mb:128,"
    "garbage_collection_threshold:0.8,"
    "expandable_segments:True"
)

#=========================================================#
#             Common helpers for all modes.               #
#=========================================================#
def set_timezone(tz_name: str = "JST-9") -> None:
    """Set process timezone so log timestamps follow JST (UTC+9)."""
    os.environ["TZ"] = tz_name
    if hasattr(time, "tzset"):
        time.tzset()

def setup_logging() -> None:
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def _load_config(config_path: str, logger: logging.Logger) -> dict:
    """Load config or raise a clear error when it fails."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded: {config_path}")
        print()
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration '{config_path}': {e}")
        raise FileNotFoundError(
            f"Configuration load failed, please check config path: {config_path}"
        ) from e

#=========================================================#
#                 Evaluation-mode helpers.                #
#=========================================================#
def _resolve_evaluation_context(model_arg: str) -> tuple[Path, Path, Path]:
    """Resolve evaluation artifacts from experiment name."""
    if not model_arg:
        # if model_arg is None or empty
        raise ValueError("Evaluation mode requires --model (experiment name).")
    if os.sep in model_arg or (os.altsep and os.altsep in model_arg):
        # if model_arg is a path
        raise ValueError(
            f"Please pass an experiment name, not a path: {model_arg}"
        )

    project_root = Path(__file__).resolve().parent  # KiDKNet/

    experiment_dir = project_root / "outputs" / "experiments" / model_arg
    if not experiment_dir.exists():
        raise FileNotFoundError(
            f"Experiment directory not found: {experiment_dir}"
        )

    config_path = experiment_dir / "experimentConfig.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing experimentConfig.yaml: {config_path}"
        )

    model_path = experiment_dir / "checkpoints" / "best_model.pth"
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model checkpoint not found: {model_path}"
        )

    return experiment_dir, model_path, config_path

#=========================================================#
#                     CLI helpers.                        #
#=========================================================#
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="KiDKNet - ConvNeXt force prediction framework"
    )

    parser.add_argument(
        "--mode",
        type=str,
        default="train",
        choices=["train", "evaluate", "split"],
        help="Run mode: train, evaluate, split"
    )

    # Train & Split configuration file path
    parser.add_argument(
        "--config", type=str, default="configs/convnext_tiny_config.yaml",
        help="Configuration file path for training and splitting"
    )

    parser.add_argument(
        "--lambda_magnitude",
        type=float,
        default=None,
        help=(
            "Override training.loss.lambda_magnitude in the loaded config "
            "(COMBINED loss only)."
        ),
    )

    # Evaluate model: pass experiment name (directory under outputs/experiments)
    parser.add_argument(
        "--model", type=str, default=None,
        help="Experiment name under outputs/experiments"
    )
    parser.add_argument(
        "--vis_samples", type=int, default=10,
        help="Number of samples to visualize (default: 10)"
    )

    # Grad-CAM arguments for evaluation mode
    parser.add_argument(
        "--enable_gradcam", action="store_true",
        help="Enable Grad-CAM visualization in evaluation mode"
    )
    parser.add_argument(
        "--gradcam_method", type=str, default="gradcam",
        choices=["gradcam", "gradcam++", "layercam", "eigencam", "eigengradcam"],
        help="Grad-CAM method to use (default: gradcam)"
    )
    parser.add_argument(
        "--gradcam_samples", type=int, default=10,
        help="Number of samples for Grad-CAM visualization (default: 10)"
    )
    parser.add_argument(
        "--gradcam_csv_samples", type=int, default=0,
        help="Number of samples for Grad-CAM CSV export (0 means full test set)"
    )
    parser.add_argument(
        "--gradcam_csv_cam_batch_size",
        type=int,
        default=16,
        help="CAM sub-batch size for Grad-CAM CSV export",
    )
    parser.add_argument(
        "--disable_gradcam_csv", action="store_true",
        help="Disable full-test Grad-CAM CSV export in evaluation mode"
    )
    parser.add_argument(
        "--export_gradcam_sample_maps",
        action="store_true",
        help=(
            "Export per-sample Grad-CAM overlays for vecfusion_abs and "
            "vecproj_gt variants, plus Top-K error CSVs"
        ),
    )
    return parser.parse_args()


# Main entrypoint.
def main():
    set_timezone()
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = DEFAULT_CUDA_ALLOC_CONF

    setup_logging()
    logger = logging.getLogger("main")
    print()
    logger.info("PYTORCH_CUDA_ALLOC_CONF set to: %s", DEFAULT_CUDA_ALLOC_CONF)
    print()

    args = parse_args()

    try:
        if args.mode == "train":
            config = _load_config(args.config, logger)
            if args.lambda_magnitude is not None:
                loss_cfg = config.get("training", {}).get("loss", {})
                loss_type = str(loss_cfg.get("type", "MSE")).upper()
                if loss_type != "COMBINED":
                    raise ValueError(
                        "--lambda_magnitude is only supported for COMBINED loss, "
                        f"got loss type: {loss_type}"
                    )
                if not (0.0 <= float(args.lambda_magnitude) <= 1.0):
                    raise ValueError(
                        "--lambda_magnitude must be within [0, 1], "
                        f"got: {args.lambda_magnitude}"
                    )
                config["training"]["loss"]["lambda_magnitude"] = float(
                    args.lambda_magnitude
                )
                logger.info(
                    "Override training.loss.lambda_magnitude to: %s",
                    config["training"]["loss"]["lambda_magnitude"],
                )
            args.split_file = config["data"]["split_file"]

            logger.info("Starting training...")
            print()
            from scripts.train import main as train_main
            train_main(args, config)
        elif args.mode == "evaluate":
            experiment_dir, model_path, config_path = _resolve_evaluation_context(args.model)

            config = _load_config(str(config_path), logger)
            if "data" not in config or "split_file" not in config["data"]:
                raise KeyError("Missing required config key: data.split_file")
            if "general" not in config or "result_dir" not in config["general"]:
                raise KeyError("Missing required config key: general.result_dir")

            split_file = config["data"]["split_file"]
            base_result_dir = Path(config["general"]["result_dir"])
            result_dir = str(base_result_dir / args.model)

            logger.info("Starting model evaluation: %s", model_path)
            from scripts.evaluate import evaluate

            os.makedirs(result_dir, exist_ok=True)
            logger.info("Evaluation results will be saved to: %s", result_dir)

            eval_args = argparse.Namespace(
                experiment=args.model,
                experiment_dir=str(experiment_dir),
                model=str(model_path),
                config_path=str(config_path),
                result_dir=result_dir,
                split_file=split_file,
                vis_samples=args.vis_samples,
                enable_loss_analysis=True,
                generate_3d_vis=True,
                enable_gradcam=getattr(args, "enable_gradcam", False),
                gradcam_method=getattr(args, "gradcam_method", "gradcam"),
                gradcam_samples=getattr(args, "gradcam_samples", 10),
                gradcam_csv_samples=getattr(args, "gradcam_csv_samples", 0),
                gradcam_csv_cam_batch_size=getattr(
                    args, "gradcam_csv_cam_batch_size", 16
                ),
                gradcam_export_csv=not getattr(args, "disable_gradcam_csv", False),
                export_gradcam_sample_maps=getattr(
                    args, "export_gradcam_sample_maps", False
                ),
            )
            evaluate(eval_args, config)
        elif args.mode == "split":
            config = _load_config(args.config, logger)
            logger.info("Starting dataset split...")
            from scripts.split_dataset import split_dataset_main
            split_dataset_main(config)
        else:
            logger.error(f"Unknown mode: {args.mode}")
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
