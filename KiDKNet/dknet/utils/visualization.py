# dknet/utils/visualization.py
from __future__ import annotations

import os
import numpy as np
import matplotlib.pyplot as plt
import torch
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EvaluateVisualizer:
    """Evaluation-stage visualizer for sample previews and residual analysis."""

    def __init__(
        self,
        output_dir: str,
        image_mean: Optional[List[float]] = None,
        image_std: Optional[List[float]] = None,
    ) -> None:
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        if image_mean is None or image_std is None:
            logger.warning(
                "image_mean/image_std are not provided; " \
                "falling back to ImageNet stats for visualization."
            )
        self.image_mean = np.array(image_mean or [0.485, 0.456, 0.406], dtype=np.float32)
        self.image_std = np.array(image_std or [0.229, 0.224, 0.225], dtype=np.float32)

    def visualize_predictions(
        self,
        images: torch.Tensor,
        true_forces: torch.Tensor,
        pred_forces: torch.Tensor,
        filename: str = "sample_predictions.png",
        max_samples: int = 10,
    ) -> None:
        """
        Visualize a deterministic subset of predictions with images.

        Layout: 2x5 grid. Each cell shows an image and True/Pred vectors plus
        per-sample relative error.
        """
        n_cols = 5
        n_rows = 2
        sample_count = int(min(max_samples, len(images), n_rows * n_cols))
        if sample_count <= 0:
            raise ValueError("No samples available for visualization")

        images_np = images.detach().cpu().numpy()
        true_np = true_forces.detach().cpu().numpy()
        pred_np = pred_forces.detach().cpu().numpy()

        abs_errors = np.abs(true_np - pred_np)
        true_norm = np.maximum(np.linalg.norm(true_np, axis=1), 1e-8)
        rel_errors = (np.linalg.norm(abs_errors, axis=1) / true_norm) * 100.0

        if len(images_np) <= sample_count:
            selected_indices = np.arange(len(images_np))
        else:
            step = max(len(images_np) // sample_count, 1)
            selected_indices = np.arange(0, len(images_np), step)[:sample_count]

        # Slice before denormalizing to avoid processing unused samples.
        images_np = images_np[selected_indices]
        true_np = true_np[selected_indices]
        pred_np = pred_np[selected_indices]
        rel_errors = rel_errors[selected_indices]

        mean = self.image_mean.reshape(1, 3, 1, 1)
        std = self.image_std.reshape(1, 3, 1, 1)
        images_np = np.clip(images_np * std + mean, 0, 1)

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 8))

        for idx in range(sample_count):
            row = idx // n_cols
            col = idx % n_cols
            ax = axes[row, col]

            img = images_np[idx].transpose(1, 2, 0)
            ax.imshow(img)

            true_str = (
                f"True: [{true_np[idx, 0]:.2f}, {true_np[idx, 1]:.2f}, {true_np[idx, 2]:.2f}]"
            )
            pred_str = (
                f"Pred: [{pred_np[idx, 0]:.2f}, {pred_np[idx, 1]:.2f}, {pred_np[idx, 2]:.2f}]"
            )
            err_str = f"Relative error: {rel_errors[idx]:.2f}%"

            ax.set_title(f"{true_str}\n{pred_str}\n{err_str}", fontsize=10)
            ax.axis("off")

        for idx in range(sample_count, n_rows * n_cols):
            row = idx // n_cols
            col = idx % n_cols
            axes[row, col].axis("off")

        save_path = os.path.join(self.output_dir, filename)
        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info("Sample prediction visualization saved to: %s", save_path)

    def plot_force_residual_scatter(
        self,
        true_forces: torch.Tensor,
        pred_forces: torch.Tensor,
        filename: str = "error_analysis.png",
        title: str = "Residual Analysis (Pred - True)",
        max_samples: int = 50000,
        seed: int = 42,
    ) -> None:
        """Plot residual scatter charts and save to `output_dir/filename`."""
        save_path = os.path.join(self.output_dir, filename)

        true_array = true_forces.detach().cpu().float().numpy()
        pred_array = pred_forces.detach().cpu().float().numpy()

        sample_count = len(true_array)
        if sample_count == 0:
            raise ValueError("Empty inputs for residual visualization")

        if max_samples is not None and sample_count > max_samples:
            rng = np.random.default_rng(seed)
            indices = rng.choice(sample_count, size=max_samples, replace=False)
            true_array = true_array[indices]
            pred_array = pred_array[indices]

        residuals = pred_array - true_array

        true_mag = np.linalg.norm(true_array, axis=1)
        pred_mag = np.linalg.norm(pred_array, axis=1)
        residual_mag = pred_mag - true_mag

        def _robust_limits(values: np.ndarray) -> tuple[float, float]:
            low, high = np.percentile(values, [1.0, 99.0])
            if not np.isfinite(low) or not np.isfinite(high):
                low, high = float(np.min(values)), float(np.max(values))
            if low == high:
                pad = 1.0
            else:
                pad = 0.05 * (high - low)
            return float(low - pad), float(high + pad)

        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        fig, axes = plt.subplots(1, 4, figsize=(22, 5))
        component_names = ["Force X", "Force Y", "Force Z"]

        for idx in range(3):
            ax = axes[idx]
            x = true_array[:, idx]
            y = residuals[:, idx]

            ax.scatter(x, y, alpha=0.25, s=6, edgecolors="none")
            ax.axhline(0.0, color="red", linestyle="--", linewidth=1)

            ax.set_title(component_names[idx])
            ax.set_xlabel(f"True {component_names[idx]}")
            ax.set_ylabel("Residual (Pred - True)")

            ax.set_xlim(*_robust_limits(x))
            ax.set_ylim(*_robust_limits(y))
            ax.grid(True, alpha=0.3)

        ax = axes[3]
        ax.scatter(true_mag, residual_mag, alpha=0.25, s=6, edgecolors="none")
        ax.axhline(0.0, color="red", linestyle="--", linewidth=1)
        ax.set_title("Force Magnitude")
        ax.set_xlabel("True Force Magnitude")
        ax.set_ylabel("Residual (Pred - True)")
        ax.set_xlim(*_robust_limits(true_mag))
        ax.set_ylim(*_robust_limits(residual_mag))
        ax.grid(True, alpha=0.3)

        fig.suptitle(title)
        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close()
        logger.info("Residual scatter chart saved to: %s", save_path)


class TrainingVisualizer:
    """Training visualizer with magnitude-angle separation metrics."""

    COMPONENT_MAPPING = {
        'loss_magnitude_component': 'magnitude_loss',
        'loss_angle_component': 'angle_loss',
        'magnitude_accuracy_10pct': 'magnitude_accuracy',
        'angle_accuracy_5deg': 'angle_accuracy',
    }

    DEFAULT_STYLE = {
        'loss_color': "#ffa510",
        'accuracy_color': "#002c53",
        'magnitude_color': "#0c84c6",
        'angle_color': "#f74d4d",
        'train_marker': 'o',
        'val_marker': 's',
    }

    def __init__(
        self,
        save_dir: str,
        experiment_name: str = "exp_",
        style_config: Optional[Dict[str, Any]] = None,
        auto_plot: bool = True,
        plot_interval: int = 5,
    ) -> None:
        self.save_dir = save_dir
        self.experiment_name = experiment_name
        self.auto_plot = auto_plot
        self.plot_interval = max(1, plot_interval)
        self.style = {**self.DEFAULT_STYLE, **(style_config or {})}
        os.makedirs(save_dir, exist_ok=True)

        self.history = {
            'train_loss': [],
            'val_loss': [],
            'train_accuracy': [],
            'val_accuracy': [],

            'train_magnitude_loss': [],
            'val_magnitude_loss': [],
            'train_angle_loss': [],
            'val_angle_loss': [],
            'train_magnitude_accuracy': [],
            'val_magnitude_accuracy': [],
            'train_angle_accuracy': [],
            'val_angle_accuracy': []
        }

        self.current_epoch = 0
        self.train_updated = False
        self.val_updated = False

    def _ensure_list_length(self, key: str, target_length: int) -> None:
        """Ensure the history list for a given key has the target length."""
        if key not in self.history:
            self.history[key] = []

        current_length = len(self.history[key])
        if current_length < target_length:
            # Extend the list with None values
            self.history[key].extend([None] * (target_length - current_length))

    def _record_metric(self, key: str, epoch: int, value: float) -> None:
        """Record a single metric value for the given epoch."""
        self._ensure_list_length(key, epoch + 1)
        self.history[key][epoch] = value

    def _filtered_history(self, key: str) -> List[float]:
        """Return history values with None entries removed."""
        return [v for v in self.history.get(key, []) if v is not None]

    def _plot_metric_pair(
        self,
        ax,
        train_key,
        val_key,
        ylabel,
        title,
        train_color=None,
        val_color=None,
        train_label: Optional[str] = None,
        val_label: Optional[str] = None,
    ) -> None:
        """Plot training-validation metric pair"""
        # Filter out None values to ensure data consistency
        train_data = self._filtered_history(train_key)
        val_data = self._filtered_history(val_key)

        train_color = train_color or self.style['loss_color']
        val_color = val_color or train_color
        train_marker = self.style['train_marker']
        val_marker = self.style['val_marker']

        if train_data:
            train_epochs = list(range(len(train_data)))
            ax.plot(
                train_epochs,
                train_data,
                label=train_label or f'Training {ylabel.lower()}',
                color=train_color,
                marker=train_marker,
                linestyle='-'
            )

        if val_data:
            val_epochs = list(range(len(val_data)))
            ax.plot(
                val_epochs,
                val_data,
                label=val_label or f'Validation {ylabel.lower()}',
                color=val_color,
                marker=val_marker,
                linestyle='--'
            )

        ax.set_xlabel('Epoch')
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if train_data or val_data:  # Only show legend if there is data
            ax.legend()
        ax.grid(True, linestyle='--', alpha=0.7)

    def _plot_magnitude_angle_accuracy_comparison(self, ax):
        """Plot magnitude vs angle accuracy comparison"""
        # Filter out None values to ensure data consistency
        train_mag_data = self._filtered_history('train_magnitude_accuracy')
        val_mag_data = self._filtered_history('val_magnitude_accuracy')
        train_ang_data = self._filtered_history('train_angle_accuracy')
        val_ang_data = self._filtered_history('val_angle_accuracy')

        mag_color = self.style['magnitude_color']
        ang_color = self.style['angle_color']
        train_marker = self.style['train_marker']
        val_marker = self.style['val_marker']
        if train_mag_data:
            epochs = list(range(len(train_mag_data)))
            ax.plot(
                epochs,
                train_mag_data,
                label='Magnitude Accuracy',
                color=mag_color,
                linestyle='-',
                marker=train_marker
            )

        if val_mag_data:
            epochs = list(range(len(val_mag_data)))
            ax.plot(
                epochs,
                val_mag_data,
                label='Magnitude Accuracy (Val)',
                color=mag_color,
                linestyle='--',
                marker=val_marker
            )

        if train_ang_data:
            epochs = list(range(len(train_ang_data)))
            ax.plot(
                epochs,
                train_ang_data,
                label='Angle Accuracy',
                color=ang_color,
                linestyle='-',
                marker=train_marker
            )

        if val_ang_data:
            epochs = list(range(len(val_ang_data)))
            ax.plot(
                epochs,
                val_ang_data,
                label='Angle Accuracy (Val)',
                color=ang_color,
                linestyle='--',
                marker=val_marker
            )

        ax.set_xlabel('Epoch')
        ax.set_ylabel('Accuracy')
        ax.set_title('Magnitude vs Angle Accuracy Comparison')

        # Only show legend if there is data
        if any([train_mag_data, val_mag_data, train_ang_data, val_ang_data]):
            ax.legend()
        ax.grid(True, linestyle='--', alpha=0.7)

    def _plot_loss_components_comparison(self, ax):
        """Plot magnitude vs angle loss comparison"""
        # Filter out None values to ensure data consistency
        train_mag_loss_data = self._filtered_history('train_magnitude_loss')
        val_mag_loss_data = self._filtered_history('val_magnitude_loss')
        train_ang_loss_data = self._filtered_history('train_angle_loss')
        val_ang_loss_data = self._filtered_history('val_angle_loss')

        mag_color = self.style['magnitude_color']
        ang_color = self.style['angle_color']
        train_marker = self.style['train_marker']
        val_marker = self.style['val_marker']
        if train_mag_loss_data:
            epochs = list(range(len(train_mag_loss_data)))
            ax.plot(
                epochs,
                train_mag_loss_data,
                label='Magnitude Loss',
                color=mag_color,
                linestyle='-',
                marker=train_marker
            )

        if val_mag_loss_data:
            epochs = list(range(len(val_mag_loss_data)))
            ax.plot(
                epochs,
                val_mag_loss_data,
                label='Magnitude Loss (Val)',
                color=mag_color,
                linestyle='--',
                marker=val_marker
            )

        if train_ang_loss_data:
            epochs = list(range(len(train_ang_loss_data)))
            ax.plot(
                epochs,
                train_ang_loss_data,
                label='Angle Loss',
                color=ang_color,
                linestyle='-',
                marker=train_marker
            )

        if val_ang_loss_data:
            epochs = list(range(len(val_ang_loss_data)))
            ax.plot(
                epochs,
                val_ang_loss_data,
                label='Angle Loss (Val)',
                color=ang_color,
                linestyle='--',
                marker=val_marker
            )

        ax.set_xlabel('Epoch')
        ax.set_ylabel('Loss Value')
        ax.set_title('Loss Components Comparison')

        if any([train_mag_loss_data, val_mag_loss_data, train_ang_loss_data, val_ang_loss_data]):
            ax.legend()
        ax.grid(True, linestyle='--', alpha=0.7)

    def _plot_component_loss(self, ax, component: str) -> None:
        component_key = component.lower().strip()
        if component_key not in {"magnitude", "angle"}:
            raise ValueError(f"Unsupported component: {component}")

        if component_key == "magnitude":
            train_key = "train_magnitude_loss"
            val_key = "val_magnitude_loss"
            color = self.style["magnitude_color"]
            title = "Magnitude Component Loss"
        else:
            train_key = "train_angle_loss"
            val_key = "val_angle_loss"
            color = self.style["angle_color"]
            title = "Angle Component Loss"

        train_data = self._filtered_history(train_key)
        val_data = self._filtered_history(val_key)

        train_marker = self.style["train_marker"]
        val_marker = self.style["val_marker"]

        if train_data:
            epochs = list(range(len(train_data)))
            ax.plot(
                epochs,
                train_data,
                label="Training dataset loss",
                color=color,
                linestyle="-",
                marker=train_marker,
            )

        if val_data:
            epochs = list(range(len(val_data)))
            ax.plot(
                epochs,
                val_data,
                label="Validation dataset loss",
                color=color,
                linestyle="--",
                marker=val_marker,
            )

        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss Value")
        ax.set_title(title)
        if train_data or val_data:
            ax.legend()
        ax.grid(True, linestyle="--", alpha=0.7)

    def update(
        self, 
        metrics: Dict[str, float], 
        epoch: int, 
        prefix: str
    ) -> None:
        """
        Update training history.

        Args:
            metrics: the metrics dictionary
            epoch: current epoch index
            prefix: metric prefix ('train_' or 'val_')
        """
        # Check if epoch has changed
        if epoch != self.current_epoch:
            self.current_epoch = epoch
            self.train_updated = False
            self.val_updated = False

        key_prefix = prefix.rstrip('_') if prefix else prefix

        if "loss" in metrics:
            loss_key = f"{key_prefix}_loss" if key_prefix else "loss"
            self._record_metric(loss_key, epoch, metrics["loss"])

        acc_value = metrics.get("magnitude_accuracy_10pct")
        if acc_value is not None:
            acc_key = f"{key_prefix}_accuracy" if key_prefix else "accuracy"
            self._record_metric(acc_key, epoch, acc_value)

        for metric_key, history_key in self.COMPONENT_MAPPING.items():
            # Check actual key names in metrics
            if metric_key in metrics:
                full_history_key = f"{key_prefix}_{history_key}" if key_prefix else history_key
                self._record_metric(full_history_key, epoch, metrics[metric_key])

        if prefix == "train_":
            self.train_updated = True
        elif prefix == "val_":
            self.val_updated = True

        self._maybe_plot(epoch)

    def _maybe_plot(self, epoch: int) -> None:
        """Trigger plotting based on update status and interval."""
        if not self.auto_plot:
            return
        if not (self.train_updated and self.val_updated):
            return
        if epoch == 0 or (epoch % self.plot_interval == 0):
            try:
                self.plot_comprehensive_training_progress()
            except Exception as exc:
                logger.warning(f"Failed to plot training progress at epoch {epoch}: {exc}")

    def plot_comprehensive_training_progress(self) -> None:
        """
        Plot comprehensive training progress chart, including 
        magnitude-angle separation visualization
        """
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # Top-left: Total Loss
        self._plot_metric_pair(
            axes[0, 0],
            'train_loss',
            'val_loss',
            'Training Loss',
            'Total Loss',
            train_color=self.style["loss_color"],
            val_color=self.style["accuracy_color"],
            train_label="Training dataset loss",
            val_label="Validation dataset loss",
        )

        # Top-right: Magnitude vs Angle Accuracy
        self._plot_magnitude_angle_accuracy_comparison(axes[0, 1])

        # Bottom-left: Magnitude Component Loss
        self._plot_component_loss(axes[1, 0], "magnitude")

        # Bottom-right: Angle Component Loss
        self._plot_component_loss(axes[1, 1], "angle")

        plt.tight_layout()
        save_path = os.path.join(self.save_dir, f"{self.experiment_name}_comprehensive_progress.png")
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"Comprehensive training progress chart saved to: {save_path}")


# Validation stage visualization function
def plot_force_distance_histogram(
    true_forces: torch.Tensor,
    pred_forces: torch.Tensor,
    save_path: str,
    title: str = "Force Prediction Distance Distribution",
    xlim: Optional[tuple[float, float]] = None,
    ylim: Optional[tuple[float, float]] = None,
    return_limits: bool = False,
) -> Optional[tuple[float, float]]:
    """
    Plot a histogram of Euclidean distances between true and predicted forces.

    Args:
        true_forces: Ground-truth force vectors [N, 3].
        pred_forces: Predicted force vectors [N, 3].
        save_path: Output path for the saved plot.
        title: Title for the histogram.
        xlim: Optional fixed x-axis limits to keep plots comparable across epochs.
        ylim: Optional fixed y-axis limits to keep plots comparable across epochs.
        return_limits: When True, returns the (xlim, ylim) used by the plot.
    """
    true_array = true_forces.detach().cpu().numpy()
    pred_array = pred_forces.detach().cpu().numpy()

    distances = np.linalg.norm(true_array - pred_array, axis=1)
    sample_count = max(len(distances), 1)
    weights = np.ones_like(distances, dtype=np.float64) / sample_count

    bin_count = 30
    if xlim is None:
        # Use data-driven range for the first plot.
        _, bin_edges = np.histogram(distances, bins=bin_count, weights=weights)
        xlim = (float(bin_edges[0]), float(bin_edges[-1]))

    # Use fixed bin edges once xlim is established, to make epoch-to-epoch
    # comparisons consistent.
    bin_edges = np.linspace(xlim[0], xlim[1], num=bin_count + 1, dtype=np.float64)
    hist_probs, _ = np.histogram(distances, bins=bin_edges, weights=weights)

    _, ax_hist = plt.subplots(figsize=(8, 6))
    ax_hist.hist(
        distances,
        bins=[float(e) for e in bin_edges],
        weights=weights,
        alpha=0.7,
        color='skyblue',
        edgecolor='black',
    )
    ax_hist.set_xlabel('Prediction Distance', fontsize=10)
    ax_hist.set_ylabel('Probability', fontsize=10)
    ax_hist.set_title(title, fontsize=11)
    ax_hist.grid(True, alpha=0.3)
    ax_hist.tick_params(axis='both', which='major', labelsize=9)

    ax_hist.set_xlim(*xlim)
    if ylim is None:
        y_max = float(np.max(hist_probs)) if hist_probs.size else 0.0
        # Ensure there is enough headroom for visual clarity.
        ylim = (0.0, max(y_max * 1.1, 1e-6))
    ax_hist.set_ylim(*ylim)

    ax_hist.axvline(
        distances.mean(),
        color='red',
        linestyle='--',
        linewidth=2,
        label=f'Mean: {distances.mean():.3f}'
    )
    ax_hist.legend()

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()

    if return_limits:
        # Only x-limits are meant to be re-used across epochs; y-limits are
        # intentionally dynamic to maximize plot utilization.
        return xlim

    return None
