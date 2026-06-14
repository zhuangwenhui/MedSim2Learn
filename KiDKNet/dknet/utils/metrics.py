# dknet/utils/metrics.py
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, Optional, Union
from .losses import MagnitudeAngleLoss, SequenceMagnitudeAngleLoss


DEFAULT_EPSILON = 1e-8
#==============================================================#
#                       Magnitude Metrics                      #
#==============================================================#
def _relative_error(
    pred: torch.Tensor,
    target: torch.Tensor,
    eps: float = DEFAULT_EPSILON,
    mode: str = "vector",
) -> torch.Tensor:
    """Compute per-sample relative error.

    Args:
        pred: Predicted force vectors [batch_size, 3].
        target: Target force vectors [batch_size, 3].
        eps: Numerical stability constant.
        mode: ``"vector"`` — ‖pred-target‖/‖target‖;
              ``"magnitude"`` — |‖pred‖-‖target‖|/‖target‖.
    """
    target_norm = torch.norm(target, dim=1)
    if mode == "vector":
        return torch.norm(pred - target, dim=1) / (target_norm + eps)
    return torch.abs(torch.norm(pred, dim=1) - target_norm) / (target_norm + eps)


def _magnitude_relative_error(
    pred: torch.Tensor, target: torch.Tensor, eps: float = DEFAULT_EPSILON
) -> torch.Tensor:
    """Compute per-sample relative error on vector magnitude."""
    return _relative_error(pred, target, eps, mode="magnitude")


def _vector_relative_error(
    pred: torch.Tensor, target: torch.Tensor, eps: float = DEFAULT_EPSILON
) -> torch.Tensor:
    """Compute per-sample relative error on the vector prediction."""
    return _relative_error(pred, target, eps, mode="vector")


def _magnitude_absolute_error(
    pred: torch.Tensor, target: torch.Tensor
) -> torch.Tensor:
    """Compute per-sample absolute error on vector magnitude."""
    pred_mag = torch.norm(pred, dim=1)
    target_mag = torch.norm(target, dim=1)

    return torch.abs(pred_mag - target_mag)


def _magnitude_accuracy_under_threshold(
    pred: torch.Tensor, 
    target: torch.Tensor, 
    threshold: float = 0.05, 
    eps: float = DEFAULT_EPSILON
) -> float:
    """
    Ratio of samples whose magnitude relative error is below the given threshold
    (default 5%). Errors below the threshold are treated as correct.
    """
    rel_errors = _magnitude_relative_error(pred, target, eps)
    accuracy = (rel_errors < threshold).float().mean().item()

    return accuracy


#==============================================================#
#                        Angle Metrics                         #
#==============================================================#
def _angle_error_degrees(
    pred: torch.Tensor, target: torch.Tensor, eps: float = DEFAULT_EPSILON
) -> torch.Tensor:
    """Compute angle error between force vectors in degrees."""
    # Normalize vectors
    pred_norm = F.normalize(pred, p=2, dim=1, eps=eps)
    target_norm = F.normalize(target, p=2, dim=1, eps=eps)
    cos_sim = torch.clamp((pred_norm * target_norm).sum(dim=1), -1.0 + eps, 1.0 - eps)
    return torch.acos(cos_sim) * (180.0 / np.pi)


def _angle_accuracy_under_threshold(
    pred: torch.Tensor, 
    target: torch.Tensor, 
    threshold_degrees: float = 5.0, 
    eps: float = DEFAULT_EPSILON
) -> float:
    """
    Ratio of samples with angle error below the given threshold in degrees
    (default 5°).
    """
    angles = _angle_error_degrees(pred, target, eps)
    accuracy = (angles < threshold_degrees).float().mean().item()

    return accuracy


def compute_loss_component_metrics(
    pred: torch.Tensor, 
    target: torch.Tensor, 
    loss_fn: Optional[nn.Module] = None, 
    eps: float = DEFAULT_EPSILON
) -> Dict[str, Union[float, bool]]:
    """
    Compute metrics aligned with loss components for detailed analysis.

    Args:
        pred: Predicted force vectors [batch_size, 3]
        target: Target force vectors [batch_size, 3]
        loss_fn: Loss module that can expose component losses
        eps: Numerical stability constant

    Returns:
        dict: Metrics related to loss components
    """
    metrics = {}
    # Calculate magnitude-related metrics
    mag_rel_errors = _magnitude_relative_error(pred, target, eps)
    metrics['magnitude_mean_relative_error'] = mag_rel_errors.mean().item()
    # Calculate defined accuracy
    metrics['magnitude_accuracy_10pct'] = _magnitude_accuracy_under_threshold(
        pred, target, threshold=0.1
    )
    metrics['magnitude_accuracy_5pct'] = _magnitude_accuracy_under_threshold(
        pred, target, threshold=0.05
    )
    metrics['magnitude_mean_absolute_error'] = _magnitude_absolute_error(pred, target).mean().item()
    metrics['vector_mean_relative_error'] = _vector_relative_error(pred, target, eps).mean().item()
    component_mae = torch.abs(pred - target).mean(dim=0)
    metrics['x_mae'] = component_mae[0].item()
    metrics['y_mae'] = component_mae[1].item()
    metrics['z_mae'] = component_mae[2].item()
    # Calculate angle-related metrics
    angles = _angle_error_degrees(pred, target, eps)
    metrics['mean_angle_error'] = angles.mean().item()
    metrics['angle_accuracy_5deg'] = _angle_accuracy_under_threshold(
        pred, target, threshold_degrees=5.0
    )
    
    # Add loss components when available (single-image or sequence loss). The
    # sequence loss's get_component_losses accepts already-flattened (N, 3)
    # tensors here, so the same call works for both.
    if isinstance(loss_fn, (MagnitudeAngleLoss, SequenceMagnitudeAngleLoss)):
        mag_loss, ang_loss = loss_fn.get_component_losses(pred, target)
        metrics['loss_magnitude_component'] = mag_loss
        metrics['loss_angle_component'] = ang_loss
        
        # Record normalization stats when supported
        norm_stats = loss_fn.get_normalization_stats()
        metrics.update({f"loss_{k}": v for k, v in norm_stats.items()})
    
    return metrics


def denormalize_forces(
    forces: torch.Tensor,
    normalization_params: Optional[Dict[str, float]] = None
) -> torch.Tensor:
    """
    Convert normalized force vectors back to the original scale.

    Args:
        forces: Normalized force vectors [batch_size, 3]
        normalization_params: Dict with x_scale, y_scale, z_scale factors

    Returns:
        torch.Tensor: Denormalized force vectors [batch_size, 3]
    """
    if forces is None or normalization_params is None:
        return forces
        
    denorm_forces = forces.clone()
    denorm_forces[:, 0] = forces[:, 0] * normalization_params['x_scale']
    denorm_forces[:, 1] = forces[:, 1] * normalization_params['y_scale']
    denorm_forces[:, 2] = forces[:, 2] * normalization_params['z_scale']
    
    return denorm_forces


def compute_all_metrics(
    pred: torch.Tensor, 
    target: torch.Tensor, 
    force_normalization: Optional[Dict[str, float]] = None,
    include_denormalized: bool = False,
    loss_fn: Optional[nn.Module] = None
) -> Dict[str, Union[float, bool]]:
    """
    Compute all evaluation metrics: base + loss components + denormalized.

    Args:
        pred: Predicted force vectors [batch_size, 3]
        target: Target force vectors [batch_size, 3]
        force_normalization: Force normalization parameters
        include_denormalized: Whether to include denormalized metrics
        loss_fn: Loss module used for component metrics

    Returns:
        dict: Aggregated metrics
    """
    pred = torch.as_tensor(pred)
    target = torch.as_tensor(target).to(pred.device)

    metrics = {}
    metrics.update(
        compute_loss_component_metrics(pred, target, loss_fn=loss_fn)
    )
    
    # Denormalized metrics if requested
    if include_denormalized and force_normalization is not None:
        denorm_pred = denormalize_forces(pred, force_normalization)
        denorm_target = denormalize_forces(target, force_normalization)

        denorm_loss_metrics = compute_loss_component_metrics(
            denorm_pred, denorm_target
        )
        metrics.update(
            {f"denorm_{k}": v for k, v in denorm_loss_metrics.items()}
        )

    return metrics


def compute_sequence_metrics(
    pred: Union[torch.Tensor, list, tuple],
    target: torch.Tensor,
    force_normalization: Optional[Dict[str, float]] = None,
    include_denormalized: bool = False,
    loss_fn: Optional[nn.Module] = None,
    eps: float = DEFAULT_EPSILON,
) -> Dict[str, Union[float, bool]]:
    """Compute metrics for per-frame sequence predictions.

    The per-frame quality metrics reuse :func:`compute_all_metrics` over the
    clip flattened to ``(B*T, 3)``; two temporal-consistency metrics are added
    on top:

    - ``temporal_delta_rmse``: RMSE between predicted and ground-truth first
      differences (how well the predicted dynamics track the true dynamics).
    - ``temporal_jitter_rmse``: RMSE of the predicted first differences alone
      (raw prediction smoothness, target-agnostic).

    Args:
        pred: Final-stage ``(B, T, 3)`` tensor, or a list/tuple of per-stage
            tensors (the last element is used).
        target: Ground-truth ``(B, T, 3)`` tensor.
        force_normalization: Optional per-axis scale factors.
        include_denormalized: Whether to add denormalized per-frame metrics.
        loss_fn: Loss module exposing component losses (optional).
        eps: Numerical stability constant.

    Returns:
        dict: Per-frame metrics plus temporal-consistency metrics.
    """
    if isinstance(pred, (list, tuple)):
        pred = pred[-1]
    pred = torch.as_tensor(pred)
    target = torch.as_tensor(target).to(pred.device)
    if pred.dim() != 3 or target.dim() != 3:
        raise ValueError(
            "compute_sequence_metrics expects (B, T, 3) tensors, got "
            f"pred={tuple(pred.shape)} target={tuple(target.shape)}"
        )

    metrics = compute_all_metrics(
        pred.reshape(-1, pred.shape[-1]),
        target.reshape(-1, target.shape[-1]),
        force_normalization=force_normalization,
        include_denormalized=include_denormalized,
        loss_fn=loss_fn,
    )

    if pred.size(1) >= 2:
        d_pred = pred[:, 1:] - pred[:, :-1]
        d_target = target[:, 1:] - target[:, :-1]
        metrics['temporal_delta_rmse'] = torch.sqrt(
            (d_pred - d_target).pow(2).mean() + eps
        ).item()
        metrics['temporal_jitter_rmse'] = torch.sqrt(
            d_pred.pow(2).mean() + eps
        ).item()
    else:
        metrics['temporal_delta_rmse'] = 0.0
        metrics['temporal_jitter_rmse'] = 0.0

    return metrics
