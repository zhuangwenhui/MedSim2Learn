"""
Grad-CAM helpers for force regression models.

Generates CAM overlays for predicted force vectors and saves evaluation
visualizations to disk.
"""
from __future__ import annotations

import csv
import logging
import os
import re
from collections.abc import Callable, Sequence
from typing import Any, cast

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn

# Import pytorch-grad-cam
from pytorch_grad_cam import (
    EigenCAM,
    EigenGradCAM,
    GradCAM,
    GradCAMPlusPlus,
    LayerCAM,
)
from pytorch_grad_cam.utils.image import show_cam_on_image

logger = logging.getLogger(__name__)

_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD  = [0.229, 0.224, 0.225]


def _make_denormalize_fn(
    image_mean: list[float] | None,
    image_std: list[float] | None,
) -> Callable[[torch.Tensor], torch.Tensor]:
    """Return a closure that undoes image normalization for visualization.

    Falls back to ImageNet statistics when *image_mean*/*image_std* are not
    provided.  The returned function moves tensors to CPU, converts to
    float32, applies ``tensor * std + mean``, and clamps to ``[0, 1]``.
    """
    mean_vals = image_mean if image_mean is not None else _IMAGENET_MEAN
    std_vals  = image_std  if image_std  is not None else _IMAGENET_STD
    mean = torch.tensor([float(v) for v in mean_vals], dtype=torch.float32).view(1, 3, 1, 1)
    std  = torch.tensor([float(v) for v in std_vals],  dtype=torch.float32).view(1, 3, 1, 1)

    def _fn(tensor: torch.Tensor) -> torch.Tensor:
        # Convert to a [0, 1] RGB tensor on CPU for visualization overlays.
        return torch.clamp(tensor.detach().cpu().float() * std + mean, 0, 1)

    return _fn


def _sanitize_sample_id(sample_id: Any) -> str:
    """Return a safe filename derived from a sample ID without truncation."""
    sid_raw = str(sample_id)
    sid_clean = re.sub(r"[^A-Za-z0-9_-]+", "_", sid_raw).strip("_")
    if not sid_clean:
        sid_clean = "sample"
    return sid_clean


def _fmt(v: float, width: int, prec: int) -> str:
    return f"{v:{width}.{prec}f}"


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _row(cells: list[str]) -> str:
        return "| " + " | ".join(
            f"{cells[i]:<{widths[i]}}" for i in range(len(cells))
        ) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    lines = [sep, _row(headers), sep]
    lines.extend(_row(r) for r in rows)
    lines.append(sep)
    return "\n".join(lines)


def _write_cam_error_topk_csvs(
    records: list[dict[str, Any]],
    cam_key: str,
    output_dir: str,
    top_k: int = 20,
) -> None:
    """Write low/high error Top-K CSVs for samples with non-zero CAM value."""
    valid = [r for r in records if float(r.get(cam_key, 0.0)) > 0.0]
    sorted_valid = sorted(valid, key=lambda r: float(r["relative_error_pct"]))
    low = sorted_valid[:top_k]
    high = sorted_valid[-top_k:][::-1]

    columns = [
        "idx",
        "sample_id",
        "image_file",
        "mae",
        "l2",
        "relative_error_pct",
        "target_norm",
        "pred_norm",
        "pred_x",
        "pred_y",
        "pred_z",
        "true_x",
        "true_y",
        "true_z",
        cam_key,
    ]

    def _write(path: str, rows: list[dict[str, Any]]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k) for k in columns})

    _write(
        os.path.join(output_dir, f"cam_nonzero_low_error_top{top_k}.csv"),
        low,
    )
    _write(
        os.path.join(output_dir, f"cam_nonzero_high_error_top{top_k}.csv"),
        high,
    )


class ForceRegressionTarget(nn.Module):
    """
    Grad-CAM target for force regression outputs.

    Computes gradients for a selected force component or magnitude.
    """

    def __init__(self, target_component: str = 'magnitude') -> None:
        """
        Configure which output component drives Grad-CAM.

        Args:
            target_component: 'magnitude', 'x', 'y', 'z', or 'weighted'
                (abs-weighted sum).
        """
        super().__init__()
        self.target_component = target_component

    def forward(self, model_output: torch.Tensor) -> torch.Tensor:
        """
        Return the scalar target for Grad-CAM.

        Args:
            model_output: [3] for a single sample or [batch_size, 3].

        Returns:
            Scalar target value.
        """
        if model_output.dim() == 1:
            # Single sample case
            if self.target_component == 'magnitude':
                # Force norm
                return torch.norm(model_output)
            elif self.target_component == 'x':
                return model_output[0]
            elif self.target_component == 'y':
                return model_output[1]
            elif self.target_component == 'z':
                return model_output[2]
            elif self.target_component == 'weighted':
                weights = torch.abs(model_output) / (
                    torch.sum(torch.abs(model_output)) + 1e-8
                )
                return torch.sum(model_output * weights)
            else:
                raise ValueError(
                    f"Unknown target component: {self.target_component}"
                )
        elif model_output.dim() == 2:
            # Batch case
            if self.target_component == 'magnitude':
                return torch.norm(model_output, dim=1)
            elif self.target_component == 'x':
                return model_output[:, 0]
            elif self.target_component == 'y':
                return model_output[:, 1]
            elif self.target_component == 'z':
                return model_output[:, 2]
            elif self.target_component == 'weighted':
                weights = torch.abs(model_output)
                weights = weights / (weights.sum(dim=1, keepdim=True) + 1e-8)
                return torch.sum(model_output * weights, dim=1)
            else:
                raise ValueError(
                    f"Unknown target component: {self.target_component}"
                )
        else:
            raise ValueError(
                f"Unsupported model output shape {model_output.shape} "
                "for Grad-CAM target computation"
            )


class ForceVectorProjectionTarget(nn.Module):
    """
    Grad-CAM target based on vector projection onto a fixed direction.

    For each sample, this target computes dot(pred, direction_unit), where
    direction_unit is typically derived from the ground-truth force vector.
    """

    def __init__(self, direction: torch.Tensor, eps: float = 1e-8) -> None:
        super().__init__()
        if direction.numel() != 3:
            raise ValueError(
                "ForceVectorProjectionTarget expects a 3D direction vector."
            )
        direction = direction.detach().float().view(3)
        norm = float(torch.norm(direction).item())
        if norm <= eps:
            # Fallback to x-axis when direction norm is too small.
            direction_unit = torch.tensor([1.0, 0.0, 0.0], dtype=torch.float32)
        else:
            direction_unit = direction / norm
        self.register_buffer("direction_unit", direction_unit)

    def forward(self, model_output: torch.Tensor) -> torch.Tensor:
        direction_buffer = cast(torch.Tensor, self.get_buffer("direction_unit"))
        direction = direction_buffer.to(
            device=model_output.device, dtype=model_output.dtype
        )
        if model_output.dim() == 1:
            return torch.dot(model_output, direction)
        if model_output.dim() == 2:
            return torch.sum(model_output * direction.view(1, 3), dim=1)
        raise ValueError(
            f"Unsupported model output shape {model_output.shape} "
            "for vector projection target"
        )


class GradCAMVisualizer:
    """
    Grad-CAM visualizer for force prediction models.

    Supports ConvNeXt backbones and multiple CAM methods.
    """

    def __init__(
        self,
        model: nn.Module,
        backbone_type: str = 'convnext',
        cam_method: str = 'gradcam',
        target_component: str = 'magnitude',
    ) -> None:
        """
        Initialize the Grad-CAM visualizer.

        Args:
            model: Force prediction model.
            backbone_type: Must be 'convnext'.
            cam_method: 'gradcam', 'gradcam++', 'layercam', 'eigencam', or
                'eigengradcam'.
            target_component: Force component to visualize.
        """
        self.model = model
        self.backbone_type = backbone_type.lower()
        self.cam_method = cam_method.lower()
        self.target_component = target_component
        if not torch.cuda.is_available():
            raise RuntimeError(
                "Grad-CAM requires CUDA, but no CUDA device is available."
            )
        self.device = torch.device("cuda")

        # Move model to device
        self.model = self.model.to(self.device)
        self.model.eval()

        # Get target layers based on backbone type
        self.target_layers = self._get_target_layers()
        # Initialize CAM. Fail-fast: when Grad-CAM is enabled, do not
        # silently fall back to a placeholder mask.
        self.cam = self._initialize_cam()
        logger.info(
            "Initialized GradCAM visualizer for %s backbone using %s",
            backbone_type,
            cam_method,
        )

    def _get_target_layers(self) -> list[nn.Module]:
        """
        Resolve target layers based on the backbone type.

        Returns:
            Target layers for CAM computation (last conv).
        """
        backbone = getattr(self.model, "backbone", None)
        if not isinstance(backbone, nn.Module):
            raise RuntimeError(
                "Grad-CAM expected model.backbone to be an nn.Module, got: "
                f"{type(backbone)}"
            )

        def _last_conv2d(module: nn.Module, context: str) -> nn.Conv2d:
            last_conv: nn.Conv2d | None = None
            for submodule in module.modules():
                if isinstance(submodule, nn.Conv2d):
                    last_conv = submodule
            if last_conv is None:
                raise RuntimeError(
                    "Failed to locate nn.Conv2d layer for Grad-CAM "
                    f"({context})."
                )
            return last_conv

        if self.backbone_type == "convnext":
            backbone_model = getattr(backbone, "model", None)
            if not isinstance(backbone_model, nn.Module):
                raise RuntimeError(
                    "ConvNeXt backbone must expose backbone.model as "
                    f"nn.Module, got: {type(backbone_model)}"
                )
            features = getattr(backbone_model, "features", None)
            if not isinstance(features, nn.Sequential):
                raise RuntimeError(
                    "ConvNeXt backbone must expose backbone.model.features as "
                    f"nn.Sequential, got: {type(features)}"
                )
            return [_last_conv2d(features, context="convnext")]

        raise ValueError(
            "KiDKNet Grad-CAM supports only the ConvNeXt backbone, got: "
            f"{self.backbone_type}"
        )

    def _initialize_cam(self):
        """
        Initialize the configured CAM backend.

        Returns:
            Initialized CAM object.
        """
        cam_methods = {
            'gradcam': GradCAM,
            'gradcam++': GradCAMPlusPlus,
            'layercam': LayerCAM,
            'eigencam': EigenCAM,
            'eigengradcam': EigenGradCAM
        }

        if self.cam_method not in cam_methods:
            logger.warning(
                "Unknown CAM method %s, falling back to GradCAM",
                self.cam_method,
            )
            cam_class = GradCAM
        else:
            cam_class = cam_methods[self.cam_method]

        # Note: In newer versions of pytorch-grad-cam, use_cuda is deprecated
        # The library automatically detects if CUDA is available
        return cam_class(
            model=self.model,
            target_layers=self.target_layers
        )

    def _build_default_targets(self, batch_size: int) -> list[nn.Module]:
        """Build default targets from `self.target_component`."""
        return [
            ForceRegressionTarget(self.target_component)
            for _ in range(batch_size)
        ]

    def _prepare_images_for_overlay(
        self,
        input_tensor: torch.Tensor,
        denormalize_fn: Callable[[torch.Tensor], torch.Tensor] | None = None,
    ) -> np.ndarray:
        """Convert normalized tensors to [B, H, W, C] RGB arrays in [0, 1]."""
        images_cpu = input_tensor.detach().cpu()
        if denormalize_fn is not None:
            images_cpu = denormalize_fn(images_cpu)
        else:
            logger.warning(
                "denormalize_fn is not provided; "
                "falling back to ImageNet stats for visualization."
            )
            mean = torch.tensor(
                [0.485, 0.456, 0.406], dtype=images_cpu.dtype
            ).view(1, 3, 1, 1)
            std = torch.tensor(
                [0.229, 0.224, 0.225], dtype=images_cpu.dtype
            ).view(1, 3, 1, 1)
            images_cpu = images_cpu * std + mean
        images_cpu = torch.clamp(images_cpu, 0, 1)
        return images_cpu.numpy().transpose(0, 2, 3, 1)

    def generate_cam_maps(
        self,
        input_tensor: torch.Tensor,
        targets: Sequence[nn.Module] | None = None,
    ) -> np.ndarray:
        """
        Generate grayscale CAM maps [B, H, W] for the provided targets.
        """
        input_tensor = input_tensor.to(self.device)
        if self.cam is None:
            raise RuntimeError("Grad-CAM is not initialized.")

        if targets is None:
            targets_seq: Sequence[nn.Module] = self._build_default_targets(
                input_tensor.size(0)
            )
        else:
            targets_seq = targets
        if len(targets_seq) != input_tensor.size(0):
            raise ValueError(
                "Grad-CAM targets length mismatch: "
                f"len(targets)={len(targets_seq)}, batch_size={input_tensor.size(0)}"
            )

        try:
            targets_list = list(targets_seq)
            return self.cam(input_tensor=input_tensor, targets=targets_list)
        except Exception as e:
            raise RuntimeError(f"Grad-CAM execution failed: {e}") from e

    @staticmethod
    def overlay_cam_maps(cam_maps: np.ndarray, images_np: np.ndarray) -> np.ndarray:
        """Overlay grayscale CAM maps on RGB images."""
        if len(cam_maps) != len(images_np):
            raise ValueError(
                "cam_maps and images_np must have the same first dimension."
            )
        cam_images = []
        for i in range(len(cam_maps)):
            rgb_img = np.clip(images_np[i], 0, 1).astype(np.float32)
            cam_images.append(
                show_cam_on_image(rgb_img, cam_maps[i], use_rgb=True)
            )
        return np.array(cam_images)

    def generate_cam(
        self,
        input_tensor: torch.Tensor,
        denormalize_fn: Callable[[torch.Tensor], torch.Tensor] | None = None,
        targets: Sequence[nn.Module] | None = None,
    ) -> np.ndarray:
        """
        Generate CAM overlays for input images.

        Args:
            input_tensor: Input images [batch_size, 3, H, W].
            denormalize_fn: Optional image denormalizer for visualization.
            targets: Optional per-sample target objects for Grad-CAM.

        Returns:
            CAM overlays [batch_size, H, W, 3].
        """
        cam_maps = self.generate_cam_maps(input_tensor=input_tensor, targets=targets)
        images_np = self._prepare_images_for_overlay(
            input_tensor=input_tensor,
            denormalize_fn=denormalize_fn,
        )
        return self.overlay_cam_maps(cam_maps, images_np)

    def visualize_batch(
        self,
        images: torch.Tensor,
        true_forces: torch.Tensor,
        pred_forces: torch.Tensor,
        *,
        denormalize_fn: Callable[[torch.Tensor], torch.Tensor] | None = None,
        save_dir: str | None = None,
        sample_ids: list[Any] | None = None,
        error_values: torch.Tensor | np.ndarray | None = None,
        relative_errors: torch.Tensor | np.ndarray | None = None,
        max_samples: int = 16,
        filename: str = "gradcam_visualization.png",
        cam_images_override: np.ndarray | None = None,
    ) -> None:
        """
        Save a Grad-CAM grid for a batch of samples.

        Args:
            images: Input images [batch_size, 3, H, W].
            true_forces: Ground truth force vectors [batch_size, 3].
            pred_forces: Predicted force vectors aligned with `images`.
            denormalize_fn: Optional image denormalizer.
            save_dir: Output directory for saved figures.
            sample_ids: Sample IDs for labels.
            error_values: Precomputed error values.
            relative_errors: Precomputed relative errors from evaluation
                pipeline.
            max_samples: Maximum number of samples to visualize.
            filename: Output file name when save_dir is provided.
            cam_images_override: Optional precomputed CAM overlays [B, H, W, 3].
        """
        batch_size = min(len(images), max_samples)
        images = images[:batch_size]
        true_forces = true_forces[:batch_size]
        pred_forces = pred_forces[:batch_size]

        if cam_images_override is not None:
            cam_images = np.asarray(cam_images_override)[:batch_size]
        else:
            # Generate CAM overlays. Note: Grad-CAM itself requires an internal
            # forward/backward pass; we avoid a separate "prediction-only" forward.
            cam_images = self.generate_cam(images, denormalize_fn=denormalize_fn)

        error_values_np = None
        if error_values is not None:
            if isinstance(error_values, torch.Tensor):
                error_values_np = error_values.detach().cpu().numpy()
            else:
                error_values_np = np.asarray(error_values)
            error_values_np = np.atleast_1d(error_values_np)

        relative_errors_np = None
        if relative_errors is not None:
            if isinstance(relative_errors, torch.Tensor):
                relative_errors_np = relative_errors.detach().cpu().numpy()
            else:
                relative_errors_np = np.asarray(relative_errors)
            relative_errors_np = np.atleast_1d(relative_errors_np)

        # Create figure with compact grid (aligned with sample_predictions
        # layout)
        import math

        n_cols = min(5, batch_size)
        n_rows = math.ceil(batch_size / n_cols) if batch_size > 0 else 1
        fig, axes = plt.subplots(
            n_rows,
            n_cols,
            figsize=(5.8 * n_cols, 6.0 * n_rows),
        )
        axes = np.atleast_1d(axes).reshape(n_rows, n_cols)

        true_forces_np = true_forces.cpu().numpy()
        pred_forces_np = pred_forces.cpu().numpy()
        mae_values = np.mean(np.abs(pred_forces_np - true_forces_np), axis=1)

        for i in range(n_rows * n_cols):
            row = i // n_cols
            col = i % n_cols
            ax = axes[row, col]

            if i < batch_size:
                ax.imshow(cam_images[i])
                sample_label = (
                    sample_ids[i]
                    if sample_ids and i < len(sample_ids)
                    else i
                )
                mae_value = mae_values[i]
                true_vec = true_forces_np[i]
                pred_vec = pred_forces_np[i]
                info_lines = [
                    f"ID: {sample_label}",
                    f"MAE: {mae_value:.3f} N",
                ]
                if error_values_np is not None and i < len(error_values_np):
                    info_lines.append(f"L2: {float(error_values_np[i]):.3f} N")
                if (
                    relative_errors_np is not None
                    and i < len(relative_errors_np)
                ):
                    info_lines.append(
                        f"Rel: {float(relative_errors_np[i]) * 100:.2f}%"
                    )
                info_lines.extend([
                    (
                        f"T: [{true_vec[0]:.2f}, {true_vec[1]:.2f}, "
                        f"{true_vec[2]:.2f}]"
                    ),
                    (
                        f"P: [{pred_vec[0]:.2f}, {pred_vec[1]:.2f}, "
                        f"{pred_vec[2]:.2f}]"
                    ),
                ])
                info_text = "\n".join(info_lines)
                ax.set_title("")
                ax.text(
                    0.02,
                    1.02,
                    info_text,
                    transform=ax.transAxes,
                    fontsize=16,
                    ha='left',
                    va='bottom',
                    clip_on=False,
                    bbox=dict(
                        facecolor='white',
                        alpha=0.75,
                        edgecolor='none',
                        pad=0.3,
                    )
                )
                ax.axis('off')
            else:
                ax.axis('off')

        fig.subplots_adjust(hspace=0.75, wspace=0.35, top=0.88, bottom=0.08)

        # Save figure if directory provided
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, filename)
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved Grad-CAM visualization to {save_path}")

        plt.close(fig)

    def cleanup(self):
        """Release Grad-CAM hooks and buffers."""
        cam = getattr(self, "cam", None)
        if cam is None:
            return

        activations_and_grads = getattr(cam, "activations_and_grads", None)
        if (
            activations_and_grads is not None
            and hasattr(activations_and_grads, "release")
        ):
            activations_and_grads.release()
        self.cam = None


def _save_gradcam_basic_metrics_summary(
    save_path: str,
    sample_ids: list[Any] | None,
    true_forces: torch.Tensor,
    pred_forces: torch.Tensor,
    cam_mag_mean: np.ndarray,
    cam_mag_max: np.ndarray,
    cam_eq_mean: np.ndarray,
    cam_abs_mean: np.ndarray,
    cam_proj_mean: np.ndarray,
    relative_errors: torch.Tensor | np.ndarray | None = None,
) -> None:
    """Save per-sample Grad-CAM basic metrics to a text report."""
    true_np = true_forces.detach().cpu().numpy()
    pred_np = pred_forces.detach().cpu().numpy()

    mae = np.mean(np.abs(pred_np - true_np), axis=1)
    l2 = np.linalg.norm(pred_np - true_np, axis=1)
    true_norm = np.linalg.norm(true_np, axis=1)
    pred_norm = np.linalg.norm(pred_np, axis=1)

    if relative_errors is None:
        rel = (l2 / np.clip(true_norm, 1e-8, None)) * 100.0
    else:
        if isinstance(relative_errors, torch.Tensor):
            rel = relative_errors.detach().cpu().numpy()
        else:
            rel = np.asarray(relative_errors)
        rel = np.atleast_1d(rel) * 100.0

    n = len(mae)
    if sample_ids is None:
        sample_ids = list(range(n))

    headers = [
        "Idx",
        "SampleID",
        "MAE",
        "L2",
        "RelErr(%)",
        "|T|",
        "|P|",
        "CAMmag_mean",
        "CAMmag_max",
        "CAMeq_mean",
        "CAMabs_mean",
        "CAMproj_mean",
    ]

    rows: list[list[str]] = []
    for i in range(n):
        sid = sample_ids[i] if i < len(sample_ids) else i
        rows.append(
            [
                str(i),
                str(sid),
                _fmt(float(mae[i]), 6, 4),
                _fmt(float(l2[i]), 6, 4),
                _fmt(float(rel[i]), 8, 3),
                _fmt(float(true_norm[i]), 6, 4),
                _fmt(float(pred_norm[i]), 6, 4),
                _fmt(float(cam_mag_mean[i]), 8, 5),
                _fmt(float(cam_mag_max[i]), 8, 5),
                _fmt(float(cam_eq_mean[i]), 8, 5),
                _fmt(float(cam_abs_mean[i]), 8, 5),
                _fmt(float(cam_proj_mean[i]), 8, 5),
            ]
        )

    lines = [
        "Grad-CAM Basic Metrics Summary",
        "Definition",
        "- MAE: mean absolute error across x/y/z components per sample.",
        "- L2: Euclidean norm ||pred - target||_2 per sample.",
        "- RelErr(%): 100 * ||pred - target||_2 / max(||target||_2, 1e-8).",
        "- CAM* values: statistics from grayscale CAM maps (range typically [0,1]).",
        "",
        _render_table(headers, rows),
        "",
        "Aggregate",
        f"- MAE mean/std: {np.mean(mae):.4f} / {np.std(mae):.4f}",
        f"- L2 mean/std: {np.mean(l2):.4f} / {np.std(l2):.4f}",
        f"- RelErr(%) mean/std: {np.mean(rel):.3f} / {np.std(rel):.3f}",
        f"- CAMmag_mean mean/std: {np.mean(cam_mag_mean):.5f} / {np.std(cam_mag_mean):.5f}",
        f"- CAMmag_max mean/std: {np.mean(cam_mag_max):.5f} / {np.std(cam_mag_max):.5f}",
    ]

    with open(save_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Saved Grad-CAM basic metrics summary to %s", save_path)


def export_gradcam_basic_metrics_csv_for_loader(
    model: nn.Module,
    config: dict[str, Any],
    test_loader: Any,
    output_dir: str,
    device: torch.device,
    max_samples: int = 0,
    cam_method: str = "gradcam",
    cam_batch_size: int = 16,
    csv_filename: str = "gradcam_basic_metrics_full_test.csv",
    export_sample_visualizations: bool = False,
    image_mean: list[float] | None = None,
    image_std: list[float] | None = None,
) -> str:
    """Export per-sample Grad-CAM basic metrics as CSV over a loader.

    Args:
        model: Trained model in eval mode.
        config: Evaluation config.
        test_loader: Loader used for test evaluation (shuffle=False).
        output_dir: Evaluation output directory.
        device: CUDA device.
        max_samples: Max number of samples to export; 0 means full loader.
        cam_method: CAM backend name.
        cam_batch_size: CAM compute sub-batch size used to control GPU memory.
        csv_filename: Output CSV filename under gradcam_analysis/.
        export_sample_visualizations: Whether to export per-sample overlays for
            vecfusion_abs and vecproj_gt variants.
        image_mean: Optional image mean used for denormalization.
        image_std: Optional image std used for denormalization.

    Returns:
        Absolute path to the saved CSV file.
    """
    if max_samples < 0:
        raise ValueError(f"max_samples must be >= 0, got {max_samples}")
    if cam_batch_size <= 0:
        raise ValueError(f"cam_batch_size must be > 0, got {cam_batch_size}")

    backbone_type = config["model"]["backbone"]["name"]
    gradcam_dir = os.path.join(output_dir, "gradcam_analysis")
    os.makedirs(gradcam_dir, exist_ok=True)
    csv_path = os.path.join(gradcam_dir, csv_filename)

    visualizer = GradCAMVisualizer(
        model=model,
        backbone_type=backbone_type,
        cam_method=cam_method,
        target_component="magnitude",
    )

    denormalize_fn = _make_denormalize_fn(image_mean, image_std)

    abs_dir = os.path.join(gradcam_dir, "gradcam_visualization_vecfusion_abs")
    proj_dir = os.path.join(gradcam_dir, "gradcam_visualization_vecproj_gt")
    abs_records: list[dict[str, Any]] = []
    proj_records: list[dict[str, Any]] = []
    if export_sample_visualizations:
        os.makedirs(abs_dir, exist_ok=True)
        os.makedirs(proj_dir, exist_ok=True)

    header = [
        "idx",
        "sample_id",
        "mae",
        "l2",
        "relative_error_pct",
        "target_norm",
        "pred_norm",
        "pred_x",
        "pred_y",
        "pred_z",
        "true_x",
        "true_y",
        "true_z",
        "cam_mag_mean",
        "cam_mag_max",
        "cam_eq_mean",
        "cam_abs_mean",
        "cam_proj_mean",
    ]

    processed = 0
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)

            for batch in test_loader:
                if max_samples > 0 and processed >= max_samples:
                    break

                images = batch["image"].to(device, non_blocking=True).float()
                targets = batch["force"].to(device, non_blocking=True).float()
                ids = batch.get("id")

                keep = images.size(0)
                if max_samples > 0:
                    keep = min(keep, max_samples - processed)
                if keep <= 0:
                    break

                images = images[:keep]
                targets = targets[:keep]

                normalized_ids: list[Any] = []
                for i in range(keep):
                    if ids is None:
                        sid = processed + i
                    else:
                        sid_raw = ids[i]
                        if isinstance(sid_raw, torch.Tensor):
                            sid = (
                                sid_raw.item()
                                if sid_raw.numel() == 1
                                else sid_raw.detach().cpu().tolist()
                            )
                        else:
                            sid = sid_raw
                    normalized_ids.append(sid)

                with torch.inference_mode():
                    preds = model(images).detach().cpu().float()
                pred_np = preds.numpy()
                true_np = targets.detach().cpu().numpy()

                mae = np.mean(np.abs(pred_np - true_np), axis=1)
                l2 = np.linalg.norm(pred_np - true_np, axis=1)
                true_norm = np.linalg.norm(true_np, axis=1)
                pred_norm = np.linalg.norm(pred_np, axis=1)
                rel = (l2 / np.clip(true_norm, 1e-8, None)) * 100.0

                # Keep only per-sample statistics to reduce peak memory.
                cam_mag_mean = np.empty((keep,), dtype=np.float64)
                cam_mag_max = np.empty((keep,), dtype=np.float64)
                cam_eq_mean = np.empty((keep,), dtype=np.float64)
                cam_abs_mean = np.empty((keep,), dtype=np.float64)
                cam_proj_mean = np.empty((keep,), dtype=np.float64)

                for start_idx in range(0, keep, cam_batch_size):
                    end_idx = min(start_idx + cam_batch_size, keep)
                    images_chunk = images[start_idx:end_idx]
                    targets_chunk = targets[start_idx:end_idx]
                    chunk_size = end_idx - start_idx

                    with torch.enable_grad():
                        cam_mag = visualizer.generate_cam_maps(
                            images_chunk,
                            targets=[
                                ForceRegressionTarget("magnitude")
                                for _ in range(chunk_size)
                            ],
                        )
                        cam_x = visualizer.generate_cam_maps(
                            images_chunk,
                            targets=[
                                ForceRegressionTarget("x")
                                for _ in range(chunk_size)
                            ],
                        )
                        cam_y = visualizer.generate_cam_maps(
                            images_chunk,
                            targets=[
                                ForceRegressionTarget("y")
                                for _ in range(chunk_size)
                            ],
                        )
                        cam_z = visualizer.generate_cam_maps(
                            images_chunk,
                            targets=[
                                ForceRegressionTarget("z")
                                for _ in range(chunk_size)
                            ],
                        )

                        projection_targets: list[nn.Module] = [
                            ForceVectorProjectionTarget(targets_chunk[i].detach().cpu())
                            for i in range(chunk_size)
                        ]
                        cam_proj = visualizer.generate_cam_maps(
                            images_chunk,
                            targets=projection_targets,
                        )

                    cam_eq = (cam_x + cam_y + cam_z) / 3.0
                    pred_abs_chunk = np.abs(pred_np[start_idx:end_idx])
                    pred_abs_sum = np.sum(pred_abs_chunk, axis=1, keepdims=True) + 1e-8
                    pred_weights = pred_abs_chunk / pred_abs_sum
                    cam_abs = (
                        pred_weights[:, 0, None, None] * cam_x
                        + pred_weights[:, 1, None, None] * cam_y
                        + pred_weights[:, 2, None, None] * cam_z
                    )

                    if export_sample_visualizations:
                        images_np = visualizer._prepare_images_for_overlay(
                            images_chunk,
                            denormalize_fn=denormalize_fn,
                        )
                        cam_abs_images = visualizer.overlay_cam_maps(
                            cam_abs,
                            images_np,
                        )
                        cam_proj_images = visualizer.overlay_cam_maps(
                            cam_proj,
                            images_np,
                        )
                        for local_idx in range(chunk_size):
                            global_idx = start_idx + local_idx
                            sample_idx = processed + global_idx
                            sample_id = normalized_ids[global_idx]
                            sanitized_id = _sanitize_sample_id(sample_id)
                            abs_file = f"{sanitized_id}.png"
                            proj_file = f"{sanitized_id}.png"
                            plt.imsave(
                                os.path.join(abs_dir, abs_file),
                                cam_abs_images[local_idx],
                            )
                            plt.imsave(
                                os.path.join(proj_dir, proj_file),
                                cam_proj_images[local_idx],
                            )

                            record_common = {
                                "idx": sample_idx,
                                "sample_id": sample_id,
                                "mae": float(mae[global_idx]),
                                "l2": float(l2[global_idx]),
                                "relative_error_pct": float(rel[global_idx]),
                                "target_norm": float(true_norm[global_idx]),
                                "pred_norm": float(pred_norm[global_idx]),
                                "pred_x": float(pred_np[global_idx, 0]),
                                "pred_y": float(pred_np[global_idx, 1]),
                                "pred_z": float(pred_np[global_idx, 2]),
                                "true_x": float(true_np[global_idx, 0]),
                                "true_y": float(true_np[global_idx, 1]),
                                "true_z": float(true_np[global_idx, 2]),
                            }
                            abs_records.append(
                                {
                                    **record_common,
                                    "image_file": abs_file,
                                    "cam_abs_mean": float(
                                        np.mean(cam_abs[local_idx])
                                    ),
                                }
                            )
                            proj_records.append(
                                {
                                    **record_common,
                                    "image_file": proj_file,
                                    "cam_proj_mean": float(
                                        np.mean(cam_proj[local_idx])
                                    ),
                                }
                            )

                    cam_mag_mean[start_idx:end_idx] = np.mean(cam_mag, axis=(1, 2))
                    cam_mag_max[start_idx:end_idx] = np.max(cam_mag, axis=(1, 2))
                    cam_eq_mean[start_idx:end_idx] = np.mean(cam_eq, axis=(1, 2))
                    cam_abs_mean[start_idx:end_idx] = np.mean(cam_abs, axis=(1, 2))
                    cam_proj_mean[start_idx:end_idx] = np.mean(cam_proj, axis=(1, 2))

                    if device.type == "cuda":
                        torch.cuda.empty_cache()

                for i in range(keep):
                    writer.writerow(
                        [
                            processed + i,
                            normalized_ids[i],
                            float(mae[i]),
                            float(l2[i]),
                            float(rel[i]),
                            float(true_norm[i]),
                            float(pred_norm[i]),
                            float(pred_np[i, 0]),
                            float(pred_np[i, 1]),
                            float(pred_np[i, 2]),
                            float(true_np[i, 0]),
                            float(true_np[i, 1]),
                            float(true_np[i, 2]),
                            float(cam_mag_mean[i]),
                            float(cam_mag_max[i]),
                            float(cam_eq_mean[i]),
                            float(cam_abs_mean[i]),
                            float(cam_proj_mean[i]),
                        ]
                    )

                processed += keep
                if processed % 500 == 0:
                    logger.info("Grad-CAM CSV export progress: %s samples", processed)

        if export_sample_visualizations:
            _write_cam_error_topk_csvs(
                records=abs_records,
                cam_key="cam_abs_mean",
                output_dir=abs_dir,
            )
            _write_cam_error_topk_csvs(
                records=proj_records,
                cam_key="cam_proj_mean",
                output_dir=proj_dir,
            )
            logger.info(
                "Saved per-sample Grad-CAM overlays and Top-K CSVs to: %s and %s",
                abs_dir,
                proj_dir,
            )
    finally:
        visualizer.cleanup()
    logger.info(
        "Saved Grad-CAM full-set basic metrics CSV to %s (samples=%s)",
        csv_path,
        processed,
    )
    return csv_path

def integrate_gradcam_to_evaluation(
    model: nn.Module,
    config: dict[str, Any],
    output_dir: str,
    device: torch.device,
    vis_images: torch.Tensor,
    vis_targets: torch.Tensor,
    vis_predictions: torch.Tensor,
    vis_errors: torch.Tensor | None = None,
    vis_relative_errors: torch.Tensor | None = None,
    vis_ids: list[Any] | None = None,
    image_mean: list[float] | None = None,
    image_std: list[float] | None = None,
    max_vis_samples: int = 20
) -> None:
    """
    Run Grad-CAM on evaluation samples and save visualizations.

    Args:
        model: Trained force prediction model.
        config: Model configuration.
        output_dir: Output directory for visualizations.
        device: Computing device.
        vis_images: Pre-collected visualization images to align with
            sample_predictions.png.
        vis_targets: Pre-collected target forces.
        vis_predictions: Pre-collected model predictions.
        vis_errors: Precomputed per-sample errors.
        vis_relative_errors: Precomputed per-sample relative errors from
            evaluation pipeline
        vis_ids: Pre-collected sample IDs.
        image_mean: Image mean for denormalization.
        image_std: Image std for denormalization.
        max_vis_samples: Maximum samples to visualize.
    """
    logger.info("Initializing Grad-CAM analysis for model interpretability")

    if len(vis_images) == 0:
        raise ValueError(
            "Grad-CAM requires at least one visualization sample; "
            "got empty vis_images."
        )

    # Determine backbone type from config
    backbone_type = config['model']['backbone']['name']

    if image_mean is None or image_std is None:
        logger.warning(
            "image_mean/image_std are not provided; "
            "falling back to ImageNet stats for visualization."
        )
    denormalize_fn = _make_denormalize_fn(image_mean, image_std)

    visualizer = GradCAMVisualizer(
        model=model,
        backbone_type=backbone_type,
        cam_method='gradcam',  # Can be configured
        target_component='magnitude',  # Visualize based on force magnitude
    )

    # Create output directory for Grad-CAM results
    gradcam_dir = os.path.join(output_dir, 'gradcam_analysis')
    os.makedirs(gradcam_dir, exist_ok=True)

    logger.info(
        "Using pre-collected samples to ensure consistency with "
        "sample_predictions.png"
    )
    n_samples = min(len(vis_images), max_vis_samples)
    vis_images = vis_images[:n_samples].to(device)
    vis_targets = vis_targets[:n_samples].to(device)
    vis_predictions = vis_predictions[:n_samples].to(device)
    if vis_errors is not None:
        vis_errors = vis_errors[:n_samples]
    if vis_relative_errors is not None:
        vis_relative_errors = vis_relative_errors[:n_samples]
    if vis_ids is not None:
        vis_ids = vis_ids[:n_samples]
    else:
        vis_ids = list(range(n_samples))

    logger.info(
        "Collected %s samples for Grad-CAM visualization",
        len(vis_images),
    )

    # 1. Generate detailed visualizations for all collected samples
    n_detailed_samples = len(vis_images)

    def _component_cam_maps(
        component: str,
        images_tensor: torch.Tensor,
    ) -> np.ndarray:
        targets = [
            ForceRegressionTarget(component)
            for _ in range(images_tensor.size(0))
        ]
        return visualizer.generate_cam_maps(images_tensor, targets=targets)

    images_np_for_overlay = visualizer._prepare_images_for_overlay(
        vis_images,
        denormalize_fn=denormalize_fn,
    )

    # 1-a. Baseline magnitude target
    cam_mag = _component_cam_maps("magnitude", vis_images)
    cam_mag_images = visualizer.overlay_cam_maps(cam_mag, images_np_for_overlay)
    visualizer.visualize_batch(
        images=vis_images,
        true_forces=vis_targets,
        pred_forces=vis_predictions,
        denormalize_fn=denormalize_fn,
        save_dir=gradcam_dir,
        sample_ids=vis_ids,
        error_values=vis_errors,
        relative_errors=vis_relative_errors,
        max_samples=n_detailed_samples,
        filename="gradcam_visualization.png",
        cam_images_override=cam_mag_images,
    )

    # 1-b. Vector fusion (equal weights): CAM_vec = (CAM_x + CAM_y + CAM_z) / 3
    cam_x = _component_cam_maps("x", vis_images)
    cam_y = _component_cam_maps("y", vis_images)
    cam_z = _component_cam_maps("z", vis_images)
    cam_vec_eq = (cam_x + cam_y + cam_z) / 3.0
    cam_vec_eq_images = visualizer.overlay_cam_maps(cam_vec_eq, images_np_for_overlay)
    visualizer.visualize_batch(
        images=vis_images,
        true_forces=vis_targets,
        pred_forces=vis_predictions,
        denormalize_fn=denormalize_fn,
        save_dir=gradcam_dir,
        sample_ids=vis_ids,
        error_values=vis_errors,
        relative_errors=vis_relative_errors,
        max_samples=n_detailed_samples,
        filename="gradcam_visualization_vecfusion_eq.png",
        cam_images_override=cam_vec_eq_images,
    )

    # 1-c. Vector fusion (abs-weighted by prediction components)
    pred_abs = torch.abs(vis_predictions.detach()).cpu().numpy()
    pred_abs_sum = np.sum(pred_abs, axis=1, keepdims=True) + 1e-8
    pred_weights = pred_abs / pred_abs_sum
    cam_vec_abs = (
        pred_weights[:, 0, None, None] * cam_x
        + pred_weights[:, 1, None, None] * cam_y
        + pred_weights[:, 2, None, None] * cam_z
    )
    cam_vec_abs_images = visualizer.overlay_cam_maps(
        cam_vec_abs, images_np_for_overlay
    )
    visualizer.visualize_batch(
        images=vis_images,
        true_forces=vis_targets,
        pred_forces=vis_predictions,
        denormalize_fn=denormalize_fn,
        save_dir=gradcam_dir,
        sample_ids=vis_ids,
        error_values=vis_errors,
        relative_errors=vis_relative_errors,
        max_samples=n_detailed_samples,
        filename="gradcam_visualization_vecfusion_abs.png",
        cam_images_override=cam_vec_abs_images,
    )

    # 1-d. Vector projection onto ground-truth unit direction.
    projection_targets: list[nn.Module] = [
        ForceVectorProjectionTarget(vis_targets[i].detach().cpu())
        for i in range(n_detailed_samples)
    ]
    cam_vec_proj_gt = visualizer.generate_cam_maps(
        vis_images,
        targets=projection_targets,
    )
    cam_vec_proj_gt_images = visualizer.overlay_cam_maps(
        cam_vec_proj_gt, images_np_for_overlay
    )
    visualizer.visualize_batch(
        images=vis_images,
        true_forces=vis_targets,
        pred_forces=vis_predictions,
        denormalize_fn=denormalize_fn,
        save_dir=gradcam_dir,
        sample_ids=vis_ids,
        error_values=vis_errors,
        relative_errors=vis_relative_errors,
        max_samples=n_detailed_samples,
        filename="gradcam_visualization_vecproj_gt.png",
        cam_images_override=cam_vec_proj_gt_images,
    )

    # Save per-sample numeric summary alongside Grad-CAM figures.
    cam_mag_mean = np.mean(cam_mag, axis=(1, 2))
    cam_mag_max = np.max(cam_mag, axis=(1, 2))
    cam_eq_mean = np.mean(cam_vec_eq, axis=(1, 2))
    cam_abs_mean = np.mean(cam_vec_abs, axis=(1, 2))
    cam_proj_mean = np.mean(cam_vec_proj_gt, axis=(1, 2))
    _save_gradcam_basic_metrics_summary(
        save_path=os.path.join(gradcam_dir, "gradcam_basic_metrics_summary.txt"),
        sample_ids=vis_ids,
        true_forces=vis_targets,
        pred_forces=vis_predictions,
        cam_mag_mean=cam_mag_mean,
        cam_mag_max=cam_mag_max,
        cam_eq_mean=cam_eq_mean,
        cam_abs_mean=cam_abs_mean,
        cam_proj_mean=cam_proj_mean,
        relative_errors=vis_relative_errors,
    )

    # 2. Component-wise analysis (if needed)
    component_dir = os.path.join(gradcam_dir, 'components')
    os.makedirs(component_dir, exist_ok=True)
    # Up to 8 samples for component analysis.
    n_component_samples = min(8, n_detailed_samples)
    original_component = visualizer.target_component
    for component in ("x", "y", "z", "magnitude"):
        visualizer.target_component = component
        cam_images = visualizer.generate_cam(
            vis_images[:n_component_samples],
            denormalize_fn=denormalize_fn,
        )

        # Save component visualization
        n_comp_cols = min(n_component_samples, 4)  # Maximum 4 columns
        n_comp_rows = (n_component_samples + n_comp_cols - 1) // n_comp_cols
        fig, axes = plt.subplots(
            n_comp_rows, n_comp_cols, figsize=(4 * n_comp_cols, 4 * n_comp_rows)
        )
        axes_array = np.atleast_2d(axes).reshape(n_comp_rows, n_comp_cols)
        for i in range(n_component_samples):
            row, col = divmod(i, n_comp_cols)
            ax = axes_array[row, col]
            ax.imshow(cam_images[i])
            ax.set_title(f"Sample {i+1}")
            ax.axis('off')

        # Hide unused subplots
        for i in range(n_component_samples, n_comp_rows * n_comp_cols):
            row, col = divmod(i, n_comp_cols)
            ax = axes_array[row, col]
            ax.axis('off')
        plt.suptitle(f"Grad-CAM for Force Component: {component.upper()}")
        plt.tight_layout()
        plt.savefig(
            os.path.join(component_dir, f'gradcam_{component}.png'),
            dpi=150,
            bbox_inches='tight',
        )
        plt.close()

    visualizer.target_component = original_component

    # Clean up main visualizer
    visualizer.cleanup()

    logger.info(f"Grad-CAM analysis completed. Results saved to {gradcam_dir}")
