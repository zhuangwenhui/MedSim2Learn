# Evaluation entry is centralized via KiDKNet/main.py;
# avoid running this module directly.
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import torch
import yaml
from typing import Any
from torch.utils.data import DataLoader
from tqdm import tqdm

from dknet.data import get_dataloaders
from dknet.models import build_model
from dknet.utils import (
    compute_all_metrics,
    ForceLoss,
    plot_force_distance_histogram,
    EvaluateVisualizer,
    integrate_gradcam_to_evaluation,
    export_gradcam_basic_metrics_csv_for_loader,
)

_IMAGENET_MEAN: list[float] = [0.485, 0.456, 0.406]
_IMAGENET_STD: list[float] = [0.229, 0.224, 0.225]


def _setup_logging(log_file: str) -> None:
    """Attach evaluation log file handler without overriding global logging config."""
    root_logger: logging.Logger = logging.getLogger()
    abs_log_file = os.path.abspath(log_file)

    # Reuse an existing handler when evaluate() is called multiple times
    # in a long-running process to avoid duplicated log lines.
    for handler in root_logger.handlers:
        if not isinstance(handler, logging.FileHandler):
            continue
        base_filename = getattr(handler, "baseFilename", None)
        if isinstance(base_filename, str) and os.path.abspath(base_filename) == abs_log_file:
            return

    file_handler = logging.FileHandler(abs_log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)

def _resolve_image_stats_for_visualization(
    test_loader: DataLoader,
    logger: logging.Logger,
) -> tuple[list[float], list[float]]:
    """Resolve image denormalization parameters from dataset metadata.

    The evaluation pipeline prefers metadata.yaml as the single source of truth
    for data-level preprocessing settings. ImageNet parameters are used only as
    a last-resort fallback when metadata is missing or incomplete.
    """
    dataset = getattr(test_loader, "dataset", None)
    base_dataset = getattr(dataset, "dataset", dataset)
    metadata = getattr(base_dataset, "metadata", None)
    if not isinstance(metadata, dict) or not metadata:
        logger.warning(
            "Dataset metadata is unavailable; falling back to ImageNet stats for visualization."
        )
        return _IMAGENET_MEAN, _IMAGENET_STD

    if not metadata.get("normalize_images", False):
        return [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]

    mean = metadata.get("image_mean")
    std = metadata.get("image_std")
    if (
        not isinstance(mean, (list, tuple))
        or not isinstance(std, (list, tuple))
        or len(mean) != 3
        or len(std) != 3
    ):
        logger.warning(
            "metadata.yaml indicates normalized images but is missing image_mean/image_std; "
            "falling back to ImageNet stats for visualization."
        )
        return _IMAGENET_MEAN, _IMAGENET_STD

    return [float(v) for v in mean], [float(v) for v in std]

def _build_loss_analysis_context(
    args: argparse.Namespace,
    config: dict[str, Any],
    logger: logging.Logger,
) -> tuple[torch.nn.Module | None, bool]:
    """Build loss objects needed for evaluation analysis."""
    if not args.enable_loss_analysis:
        return None, False

    loss_config: dict[str, Any] = config["training"]["loss"]
    loss_type = str(loss_config["type"]).upper()

    # MSE does not support component-wise loss monitoring/analysis.
    if loss_type == "MSE":
        logger.info("Loss analysis is disabled for MSE loss.")
        return None, False

    loss_kwargs: dict[str, Any] = {
        k: v for k, v in loss_config.items() if k != "type"
    }
    loss_fn = ForceLoss.get_loss(loss_type, **loss_kwargs)
    supports_component_monitoring = hasattr(loss_fn, "get_component_losses")
    if not supports_component_monitoring:
        raise ValueError(
            f"Loss type '{loss_type}' does not support component monitoring."
        )

    logger.info(
        "Loaded loss function for analysis, supports component monitoring: %s",
        supports_component_monitoring,
    )

    return loss_fn, supports_component_monitoring

def _prepare_test_loader(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> tuple[DataLoader, dict[str, Any]]:
    """Build the test data loader using a copy of the experiment config."""
    # Deep-copy the config to avoid mutating the original dict passed from
    # KiDKNet/main.py. get_dataloaders() may sync normalization settings from
    # dataset metadata into config["data"], so we keep those changes local.
    eval_config: dict[str, Any] = copy.deepcopy(config)
    _, _, test_loader = get_dataloaders(eval_config, split_file=args.split_file)

    return test_loader, eval_config

def _get_cuda_device() -> torch.device:
    """Return the CUDA device or raise when unavailable."""
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA device is required for evaluation; no GPU is available."
        )
    return torch.device("cuda")

def _load_model_from_checkpoint(
    args: argparse.Namespace,
    config: dict[str, Any],
    device: torch.device,
    logger: logging.Logger,
) -> tuple[torch.nn.Module, bool, dict[str, float] | None]:
    """Load model weights and return model and normalization settings."""
    force_norm_keys = ("x_scale", "y_scale", "z_scale")
    force_norm_eps = 1e-9

    def _normalize_force_norm(value: object) -> dict[str, float] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError(
                f"force_normalization must be a dict, got {type(value)}"
            )
        normalized: dict[str, float] = {}
        for key in force_norm_keys:
            if key not in value:
                raise KeyError(
                    f"force_normalization is missing required key '{key}'"
                )
            normalized[key] = float(value[key])
        return normalized

    def _force_norm_equal(
        a: dict[str, float] | None,
        b: dict[str, float] | None,
    ) -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return all(
            abs(a[key] - b[key]) <= force_norm_eps for key in force_norm_keys
        )

    config_data: dict[str, Any] = config["data"]
    config_normalize_forces = bool(
        config_data.get("normalize_forces", False)
    )
    config_force_normalization = _normalize_force_norm(
        config_data.get("force_normalization")
    )

    logger.info("Building model...")
    # Load checkpoints on CPU to avoid moving optimizer/history tensors to GPU.
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=False)

    if "normalize_forces" not in checkpoint:
        raise KeyError("Checkpoint is missing required key 'normalize_forces'")
    if "force_normalization" not in checkpoint:
        raise KeyError("Checkpoint is missing required key 'force_normalization'")

    checkpoint_normalize_forces = bool(checkpoint["normalize_forces"])
    checkpoint_force_normalization = _normalize_force_norm(
        checkpoint["force_normalization"]
    )

    if checkpoint_normalize_forces != config_normalize_forces:
        raise ValueError(
            "normalize_forces mismatch between experiment config and checkpoint: "
            f"config={config_normalize_forces}, "
            f"checkpoint={checkpoint_normalize_forces}"
        )
    if config_normalize_forces and not _force_norm_equal(
        checkpoint_force_normalization, config_force_normalization
    ):
        raise ValueError(
            "force_normalization mismatch between experiment config and checkpoint: "
            f"config={config_force_normalization}, "
            f"checkpoint={checkpoint_force_normalization}"
        )

    model = build_model(config["model"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

    logger.info("Model: %s", getattr(model, "name", type(model).__name__))
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Total parameters: %s", f"{total_params:,}")
    logger.info("Trainable parameters: %s", f"{trainable_params:,}")

    return model, config_normalize_forces, config_force_normalization

def _run_inference(
    model: torch.nn.Module,
    test_loader: DataLoader,
    device: torch.device,
    vis_samples: int,
    collect_sample_ids: bool,
) -> tuple[
    torch.Tensor,
    torch.Tensor,
    torch.Tensor,
    list[Any],
]:
    """Run inference and collect predictions/targets plus visualization samples.

    Args:
        model: Model in eval mode.
        test_loader: Test DataLoader.
        device: CUDA device.
        vis_samples: Number of samples to keep for visualization.
        collect_sample_ids: Whether to collect sample IDs for downstream usage.

    Returns:
        Tuple of:
            all_predictions,
            all_targets,
            vis_images,
            vis_ids,
    """
    prediction_chunks: list[torch.Tensor] = []
    target_chunks: list[torch.Tensor] = []
    vis_images: list[torch.Tensor] = []
    vis_ids: list[Any] = []

    if vis_samples < 0:
        raise ValueError(f"vis_samples must be >= 0, got {vis_samples}")

    collect_images = vis_samples > 0
    collected_vis_count = 0
    with torch.inference_mode():
        for batch in tqdm(test_loader, desc="Evaluation progress"):
            images = batch["image"].to(device, non_blocking=True).float()
            targets = batch["force"]
            ids = batch["id"] if collect_sample_ids else None

            outputs = model(images)

            prediction_chunks.append(outputs.cpu())
            target_chunks.append(targets.cpu())

            # Collect visualization samples up to vis_samples
            if collect_images and collected_vis_count < vis_samples:
                num_to_keep = min(vis_samples - collected_vis_count, len(images))
                vis_images.append(images[:num_to_keep].cpu())
                collected_vis_count += num_to_keep
                if ids is not None:
                    vis_ids.extend(ids[:num_to_keep])

    if not prediction_chunks:
        raise RuntimeError(
            "No batches were processed during evaluation; test_loader may be empty."
        )

    all_predictions = torch.cat(prediction_chunks, dim=0)
    all_targets = torch.cat(target_chunks, dim=0)
    if vis_images:
        all_vis_images = torch.cat(vis_images, dim=0)
    else:
        all_vis_images = torch.empty(0)

    return (
        all_predictions,
        all_targets,
        all_vis_images,
        vis_ids,
    )

def _save_evaluation_report(
    metrics: dict[str, Any],
    output_dir: str,
    num_samples: int,
    force_normalization: dict[str, float] | None,
) -> None:
    """Save a single JSON report combining flat metrics and structured summaries."""
    report: dict[str, Any] = dict(metrics)
    normalize_forces = force_normalization is not None

    report["evaluation_summary"] = {
        "total_samples": int(num_samples),
        "model_performance": {
            "overall_magnitude_accuracy_10pct": report.get(
                "magnitude_accuracy_10pct"
            ),
            "overall_magnitude_accuracy_5pct": report.get(
                "magnitude_accuracy_5pct"
            ),
            "magnitude_mean_relative_error": report.get(
                "magnitude_mean_relative_error"
            ),
            "vector_mean_relative_error": report.get(
                "vector_mean_relative_error"
            ),
            "magnitude_mean_absolute_error": report.get(
                "magnitude_mean_absolute_error"
            ),
            "mean_angle_error_degrees": report.get("mean_angle_error"),
            "angle_accuracy_5deg": report.get("angle_accuracy_5deg"),
            "axis_mae": {
                "x_mae": report.get("x_mae"),
                "y_mae": report.get("y_mae"),
                "z_mae": report.get("z_mae"),
            },
        },
    }

    report["normalization_info"] = {
        "forces_normalized": bool(normalize_forces),
        "normalization_params": force_normalization if normalize_forces else None,
    }

    has_denormalized = any(key.startswith("denorm_") for key in report)
    if normalize_forces and has_denormalized:
        report["denormalized_performance"] = {
            "magnitude_accuracy_10pct": report.get(
                "denorm_magnitude_accuracy_10pct"
            ),
            "magnitude_accuracy_5pct": report.get(
                "denorm_magnitude_accuracy_5pct"
            ),
            "magnitude_mean_relative_error": report.get(
                "denorm_magnitude_mean_relative_error"
            ),
            "vector_mean_relative_error": report.get(
                "denorm_vector_mean_relative_error"
            ),
            "magnitude_mean_absolute_error": report.get(
                "denorm_magnitude_mean_absolute_error"
            ),
            "axis_mae": {
                "x_mae": report.get("denorm_x_mae"),
                "y_mae": report.get("denorm_y_mae"),
                "z_mae": report.get("denorm_z_mae"),
            },
            "mean_angle_error_degrees": report.get("denorm_mean_angle_error"),
            "angle_accuracy_5deg": report.get("denorm_angle_accuracy_5deg"),
        }

    has_component_analysis = any(
        key in report
        for key in ("loss_magnitude_component", "loss_angle_component")
    )
    if has_component_analysis:
        loss_settings = {
            key: report.get(key)
            for key in (
                "loss_normalize_losses",
                "loss_lambda_magnitude",
                "loss_lambda_angle",
            )
            if key in report
        }
        report["component_analysis"] = {
            "magnitude_analysis": {
                "magnitude_mean_relative_error": report.get(
                    "magnitude_mean_relative_error"
                ),
                "magnitude_mean_absolute_error": report.get(
                    "magnitude_mean_absolute_error"
                ),
                "magnitude_accuracy_10pct": report.get("magnitude_accuracy_10pct"),
                "magnitude_accuracy_5pct": report.get("magnitude_accuracy_5pct"),
            },
            "vector_analysis": {
                "vector_mean_relative_error": report.get(
                    "vector_mean_relative_error"
                ),
            },
            "angle_analysis": {
                "mean_angle_error_degrees": report.get("mean_angle_error"),
                "angle_accuracy_5deg": report.get("angle_accuracy_5deg"),
            },
            "loss_components": {
                "magnitude_loss": report.get("loss_magnitude_component"),
                "angle_loss": report.get("loss_angle_component"),
            },
            "loss_settings": loss_settings or None,
        }

    report_file = os.path.join(output_dir, "evaluation_report.json")
    with open(report_file, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

def _fmt(value: Any, width: int, precision: int) -> str:
    if value is None:
        return "N/A".rjust(width)
    try:
        return f"{float(value):{width}.{precision}f}"
    except (TypeError, ValueError):
        return "N/A".rjust(width)


def _render_table(rows: list[list[str]]) -> str:
    max_cols = max((len(row) for row in rows), default=0)
    normalized_rows = [row + [""] * (max_cols - len(row)) for row in rows]
    col_widths = [0] * max_cols
    for row in normalized_rows:
        for col_idx, cell in enumerate(row):
            col_widths[col_idx] = max(col_widths[col_idx], len(cell))
    lines: list[str] = []
    for row in normalized_rows:
        rendered_cells = [
            f"{cell:<{col_widths[col_idx]}}"
            for col_idx, cell in enumerate(row)
        ]
        lines.append("| " + " | ".join(rendered_cells) + " |")
    return "\n".join(lines)


def _format_evaluation_summary(metrics: dict[str, Any], num_samples: int) -> str:
    """Return a formatted evaluation summary table aligned with training logs."""
    mag_loss = metrics.get("loss_magnitude_component")
    ang_loss = metrics.get("loss_angle_component")

    mag_acc10 = metrics.get("magnitude_accuracy_10pct")
    mag_acc5 = metrics.get("magnitude_accuracy_5pct")
    ang_acc5 = metrics.get("angle_accuracy_5deg")

    mag_mre = metrics.get("magnitude_mean_relative_error")
    vec_mre = metrics.get("vector_mean_relative_error")
    mag_mae = metrics.get("magnitude_mean_absolute_error")
    ang_mean_err = metrics.get("mean_angle_error")

    x_mae = metrics.get("x_mae")
    y_mae = metrics.get("y_mae")
    z_mae = metrics.get("z_mae")

    has_denorm = any(key.startswith("denorm_") for key in metrics)
    denorm_mag_acc10 = metrics.get("denorm_magnitude_accuracy_10pct")
    denorm_mag_acc5 = metrics.get("denorm_magnitude_accuracy_5pct")
    denorm_mag_mre = metrics.get("denorm_magnitude_mean_relative_error")
    denorm_mag_mae = metrics.get("denorm_magnitude_mean_absolute_error")

    header = f"Evaluation Summary | Samples: {num_samples}"
    rows: list[list[str]] = [
        [
            f"Mag MRE: {_fmt(mag_mre, 8, 4)}",
            f"Vec MRE: {_fmt(vec_mre, 8, 4)}",
            f"Mag MAE: {_fmt(mag_mae, 8, 4)}",
            f"Ang Mean Err(°): {_fmt(ang_mean_err, 9, 4)}",
        ],
        [
            f"Mag ACC@10%: {_fmt(mag_acc10, 7, 4)}",
            f"Mag ACC@5%: {_fmt(mag_acc5, 7, 4)}",
            f"Ang ACC@5°: {_fmt(ang_acc5, 7, 4)}",
            "",
        ],
        [
            f"X MAE: {_fmt(x_mae, 8, 4)}",
            f"Y MAE: {_fmt(y_mae, 8, 4)}",
            f"Z MAE: {_fmt(z_mae, 8, 4)}",
            "",
        ],
    ]

    if mag_loss is not None or ang_loss is not None:
        rows.insert(
            0,
            [
                f"Mag Loss: {_fmt(mag_loss, 8, 4)}",
                f"Ang Loss: {_fmt(ang_loss, 8, 4)}",
                "",
                "",
            ],
        )

    if has_denorm:
        denorm_vec_mre = metrics.get("denorm_vector_mean_relative_error")
        rows.append(
            [
                f"Denorm Mag ACC@10%: {_fmt(denorm_mag_acc10, 7, 4)}",
                f"Denorm Mag ACC@5%: {_fmt(denorm_mag_acc5, 7, 4)}",
                f"Denorm Vec MRE: {_fmt(denorm_vec_mre, 8, 4)}",
                f"Denorm Mag MRE: {_fmt(denorm_mag_mre, 8, 4)}",
            ]
        )
        rows.append(
            [
                f"Denorm Mag MAE: {_fmt(denorm_mag_mae, 8, 4)}",
                "",
                "",
                "",
            ]
        )

    return "\n".join([header, _render_table(rows)])

def _run_visualizations(
    args: argparse.Namespace,
    output_dir: str,
    vis_images: torch.Tensor,
    all_targets: torch.Tensor,
    all_predictions: torch.Tensor,
    image_mean: list[float],
    image_std: list[float],
    logger: logging.Logger,
) -> None:
    """Generate evaluation visualizations."""
    logger.info("Generating comprehensive visualization results...")
    visualizer = EvaluateVisualizer(
        output_dir=output_dir,
        image_mean=image_mean,
        image_std=image_std,
    )

    if len(vis_images) > 0:
        visualizer.visualize_predictions(
            vis_images,
            all_targets[: len(vis_images)],
            all_predictions[: len(vis_images)],
            filename="sample_predictions.png",
            max_samples=args.vis_samples,
        )

    try:
        visualizer.plot_force_residual_scatter(
            all_targets,
            all_predictions,
            filename="error_analysis.png",
            title="Evaluation - Residual Analysis (Pred - True)",
        )
        logger.info("Generated residual scatter analysis")
    except Exception as e:
        logger.warning("Failed to generate residual scatter analysis: %s", e)

    if args.generate_3d_vis:
        try:
            vis_3d_path = os.path.join(output_dir, "force_distance_histogram.png")
            plot_force_distance_histogram(
                all_targets,
                all_predictions,
                vis_3d_path,
                title="Evaluation - Force Distance Distribution",
            )
            logger.info("Generated force distance histogram")
        except Exception as e:
            logger.warning("Failed to generate distance histogram: %s", e)

    logger.info("Comprehensive visualization results saved to: %s", output_dir)

def _run_gradcam(
    args: argparse.Namespace,
    model: torch.nn.Module,
    config: dict[str, Any],
    output_dir: str,
    device: torch.device,
    vis_images: torch.Tensor,
    all_targets: torch.Tensor,
    all_predictions: torch.Tensor,
    sample_errors: torch.Tensor | None,
    sample_rel_errors: torch.Tensor | None,
    sample_ids: list[Any],
    image_mean: list[float],
    image_std: list[float],
    test_loader: DataLoader,
    logger: logging.Logger,
) -> None:
    """Run Grad-CAM analysis and save visualizations to disk."""
    logger.info("Generating Grad-CAM visualizations for model interpretability...")
    if len(vis_images) == 0:
        raise RuntimeError(
            "Grad-CAM is enabled but no visualization samples were collected. "
            "Set --vis_samples to a positive value."
        )

    max_vis_samples = min(
        int(args.gradcam_samples),
        int(args.vis_samples),
        len(vis_images),
    )
    if max_vis_samples <= 0:
        raise ValueError(
            "Grad-CAM requires positive gradcam_samples and vis_samples. "
            f"Received gradcam_samples={args.gradcam_samples}, vis_samples={args.vis_samples}."
        )
    integrate_gradcam_to_evaluation(
        model=model,
        config=config,
        output_dir=output_dir,
        device=device,
        vis_images=vis_images,
        vis_targets=all_targets[: len(vis_images)],
        vis_predictions=all_predictions[: len(vis_images)],
        vis_errors=sample_errors[: len(vis_images)] if sample_errors is not None else None,
        vis_relative_errors=sample_rel_errors[: len(vis_images)] if sample_rel_errors is not None else None,
        vis_ids=sample_ids,
        image_mean=image_mean,
        image_std=image_std,
        max_vis_samples=max_vis_samples,
    )

    export_sample_maps = bool(getattr(args, "export_gradcam_sample_maps", False))
    if getattr(args, "gradcam_export_csv", True) or export_sample_maps:
        csv_samples = int(getattr(args, "gradcam_csv_samples", 0))
        csv_cam_batch_size = int(
            getattr(
                args,
                "gradcam_csv_cam_batch_size",
                config.get("general", {}).get("gradcam_csv_cam_batch_size", 16),
            )
        )
        csv_path = export_gradcam_basic_metrics_csv_for_loader(
            model=model,
            config=config,
            test_loader=test_loader,
            output_dir=output_dir,
            device=device,
            max_samples=csv_samples,
            cam_method=getattr(args, "gradcam_method", "gradcam"),
            cam_batch_size=csv_cam_batch_size,
            export_sample_visualizations=export_sample_maps,
            image_mean=image_mean,
            image_std=image_std,
        )
        logger.info("Grad-CAM full-set CSV saved to: %s", csv_path)

    logger.info("Grad-CAM analysis completed successfully")
    logger.info(
        "Grad-CAM results saved to: %s",
        os.path.join(output_dir, "gradcam_analysis"),
    )


def evaluate(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Evaluate a trained model checkpoint using the provided experiment config."""
    if args is None or config is None:
        raise ValueError(
            "Evaluation args and config must be provided by KiDKNet/main.py; "
            "please use the main entrypoint."
        )

    output_dir = args.result_dir
    log_dir = os.path.join(output_dir, "logs")
    report_dir = os.path.join(output_dir, "reports")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "evaluation.log")
    _setup_logging(log_file)

    logger = logging.getLogger("evaluation")
    logger.info("Model checkpoint: %s", args.model)
    logger.info("Experiment config: %s", args.config_path)

    loss_fn, supports_component_monitoring = _build_loss_analysis_context(
        args, config, logger
    )

    if args.enable_gradcam and int(args.vis_samples) <= 0:
        raise ValueError(
            "Grad-CAM is enabled but vis_samples is not positive. "
            "Please set --vis_samples to a positive value."
        )
    if args.enable_gradcam and int(getattr(args, "gradcam_samples", 10)) <= 0:
        raise ValueError("gradcam_samples must be > 0 when Grad-CAM is enabled")
    if args.enable_gradcam and int(getattr(args, "gradcam_csv_samples", 0)) < 0:
        raise ValueError("gradcam_csv_samples must be >= 0")
    if (
        args.enable_gradcam
        and bool(getattr(args, "gradcam_export_csv", True))
        and int(
            getattr(
                args,
                "gradcam_csv_cam_batch_size",
                config.get("general", {}).get("gradcam_csv_cam_batch_size", 16),
            )
        )
        <= 0
    ):
        raise ValueError("gradcam_csv_cam_batch_size must be > 0")
    try:
        test_loader, eval_config = _prepare_test_loader(args, config)
    except Exception as e:
        logger.error("Failed to prepare test data: %s", e)
        raise RuntimeError(
            "Failed to build test DataLoader. Please verify the dataset directory "
            "structure, metadata.yaml, batch .pt files, and that split_file matches "
            "the selected dataset."
        ) from e

    # Use the config instance that may have been updated by get_dataloaders()
    # (e.g., normalization settings synced from dataset metadata).
    config = eval_config
    device = _get_cuda_device()
    image_mean, image_std = _resolve_image_stats_for_visualization(
        test_loader, logger
    )
    logger.info(
        "Creating test data loader with %s batches, batch size %s",
        len(test_loader),
        config["training"]["batch_size"],
    )

    try:
        model, normalize_forces, force_normalization = _load_model_from_checkpoint(
            args, config, device, logger
        )
    except Exception as e:
        logger.error("Model loading failed: %s", e)
        raise RuntimeError(
            "Failed to load model checkpoint. Please verify that best_model.pth "
            "matches experimentConfig.yaml and that the checkpoint is not corrupted."
        ) from e

    (
        all_predictions,
        all_targets,
        all_images,
        sample_ids,
    ) = _run_inference(
        model,
        test_loader,
        device,
        args.vis_samples,
        collect_sample_ids=bool(args.enable_gradcam),
    )

    logger.info("Calculating comprehensive evaluation metrics...")
    metrics = compute_all_metrics(
        all_predictions,
        all_targets,
        force_normalization=force_normalization if normalize_forces else None,
        include_denormalized=normalize_forces,
        loss_fn=loss_fn if supports_component_monitoring else None,
    )

    _save_evaluation_report(
        metrics,
        report_dir,
        num_samples=len(all_targets),
        force_normalization=force_normalization if normalize_forces else None,
    )
    evaluation_config_path = os.path.join(report_dir, "evaluation_config.yaml")
    with open(evaluation_config_path, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, sort_keys=False)
    logger.info("\n%s", _format_evaluation_summary(metrics, len(all_targets)))

    _run_visualizations(
        args,
        output_dir,
        all_images,
        all_targets,
        all_predictions,
        image_mean,
        image_std,
        logger,
    )

    if args.enable_gradcam:
        errors = torch.norm(all_predictions - all_targets, dim=1)
        denom = torch.norm(all_targets, dim=1).clamp_min(1e-8)
        rel_errors = errors / denom
        _run_gradcam(
            args,
            model,
            config,
            output_dir,
            device,
            all_images,
            all_targets,
            all_predictions,
            errors,
            rel_errors,
            sample_ids,
            image_mean,
            image_std,
            test_loader,
            logger,
        )

    logger.info("Evaluation completed")
