"""Training-independent measurements for synthetic-to-real feature gaps."""

from __future__ import annotations

import torch


def _validate_pair(
    source: torch.Tensor,
    target: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    if source.dim() != 2 or target.dim() != 2:
        raise ValueError(
            "expected 2-D feature matrices; "
            f"got {tuple(source.shape)} and {tuple(target.shape)}"
        )
    if source.size(1) != target.size(1):
        raise ValueError(
            "feature dimension mismatch: "
            f"{source.size(1)} and {target.size(1)}"
        )
    if source.size(0) < 2 or target.size(0) < 2:
        raise ValueError("each domain requires at least two feature rows")
    return source.float(), target.float()


def _covariance(features: torch.Tensor) -> torch.Tensor:
    centered = features - features.mean(dim=0, keepdim=True)
    return centered.t() @ centered / (features.size(0) - 1)


def _coral_distance_tensor(
    source: torch.Tensor,
    target: torch.Tensor,
) -> torch.Tensor:
    source, target = _validate_pair(source, target)
    feature_dim = source.size(1)
    covariance_delta = _covariance(source) - _covariance(target)
    return covariance_delta.square().sum() / (
        4 * feature_dim * feature_dim
    )


@torch.no_grad()
def coral_distance(source: torch.Tensor, target: torch.Tensor) -> float:
    """Return the Deep CORAL covariance distance between two feature sets."""
    return float(_coral_distance_tensor(source, target))


@torch.no_grad()
def _within_domain_floor(features: torch.Tensor, seed: int) -> float:
    if features.size(0) < 4:
        return 0.0
    generator = torch.Generator().manual_seed(seed)
    order = torch.randperm(features.size(0), generator=generator)
    order = order.to(features.device)
    half = features.size(0) // 2
    return coral_distance(
        features[order[:half]],
        features[order[half : 2 * half]],
    )


@torch.no_grad()
def domain_gap_report(
    source: torch.Tensor,
    target: torch.Tensor,
    seed: int = 0,
) -> dict[str, float | int]:
    """Report covariance, mean, spread, and sampling-floor gap measures."""
    source, target = _validate_pair(source, target)
    cross_domain = coral_distance(source, target)
    within_source = _within_domain_floor(source, seed)
    within_target = _within_domain_floor(target, seed + 1)
    within_mean = 0.5 * (within_source + within_target)
    source_rms = float(source.std(dim=0).mean())
    target_rms = float(target.std(dim=0).mean())
    return {
        "coral_distance": cross_domain,
        "within_source": within_source,
        "within_target": within_target,
        "within_mean": within_mean,
        "gap_ratio": (
            cross_domain / within_mean
            if within_mean > 0
            else float("inf")
        ),
        "mean_l2": float(
            (source.mean(dim=0) - target.mean(dim=0)).norm()
        ),
        "rms_source": source_rms,
        "rms_target": target_rms,
        "rms_ratio": (
            source_rms / target_rms
            if target_rms > 0
            else float("inf")
        ),
        "n_source": int(source.size(0)),
        "n_target": int(target.size(0)),
        "feature_dim": int(source.size(1)),
    }
