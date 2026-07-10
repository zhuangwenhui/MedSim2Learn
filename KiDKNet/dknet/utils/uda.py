"""Unsupervised domain-adaptation primitives (Track B, 2026-07-03 redirection).

Standalone, dependency-light building blocks for the synth->real gap in the
zero-real-label setting (train on labeled synthetic, adapt to unlabeled real; inference
stays image->3D force). Two roles share the SAME second-order-statistic math:

  1. Training loss -- ``coral_loss`` is wired (config-gated, default OFF, byte-identical
     when off) into the trainer as an optional alignment term. The Track B experiment
     (2026-07-03) found CORAL@w=1.0 does NOT reliably close the gap at the current
     measurement fidelity (null result, mean magMAE 1.42 vs baseline 1.23, paired
     t=-0.70); the wiring stays gated OFF pending a measurement overhaul.
  2. Gap METRIC -- ``coral_distance`` / ``domain_gap_report`` reuse the exact same
     covariance discrepancy as a MEASUREMENT (no gradients) to quantify how far a
     synthetic image set sits from the real one on frozen ConvNeXt features. This is the
     retained, fossilised tool: after data-side appearance work we re-measure and check
     the gap shrank. Driver: ``scripts/eval_domain_gap.py``.

The math lives here (unit-tested on CPU) so correctness is verified independently of I/O.

Applicability (verified against the codebase, 2026-07-03):
  - CORAL / DANN operate on the 1536-d ConvNeXt feature and therefore apply to the
    single-frame conditions c1-c4 (backbone fine-tuned end-to-end). For the sequence
    conditions c5-c8 the backbone is frozen and features are precomputed, so aligning the
    cached features is a no-op for learning; those need a trainable temporal-head tap
    (out of scope for the first increment).
  - Tent-style BatchNorm test-time adaptation is NOT applicable: ConvNeXt uses LayerNorm,
    and the temporal head has no BatchNorm; the only BatchNorm is in the c1-c4 regression
    head, which is not a legitimate Tent target. It is intentionally omitted here.
"""

from __future__ import annotations

import torch
import torch.nn as nn


def coral_loss(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Deep CORAL alignment loss (Sun & Saenko, ECCV 2016, Eq. 1).

    Aligns the second-order statistics of two feature batches:
        L = ||C_s - C_t||_F^2 / (4 * d * d)
    where C is the unbiased covariance and d is the feature dimension. The 1/(4 d^2)
    normalisation is what makes the loss magnitude comparable across feature dimensions
    (a bare 1/(4 d) leaves a residual factor of d and inflates the term ~d-fold).

    Args:
        source: (n_s, d) source-domain (labeled synthetic) features.
        target: (n_t, d) target-domain (unlabeled real) features.

    Returns:
        Scalar alignment loss (>= 0). Gradients flow to whichever inputs require them,
        so the caller controls which domain pulls toward the other.
    """
    if source.dim() != 2 or target.dim() != 2:
        raise ValueError(f"expected 2-D (batch, feat); got {tuple(source.shape)} / {tuple(target.shape)}")
    if source.size(1) != target.size(1):
        raise ValueError(f"feature dim mismatch: {source.size(1)} vs {target.size(1)}")

    d = source.size(1)
    src_c = source - source.mean(dim=0, keepdim=True)
    tgt_c = target - target.mean(dim=0, keepdim=True)
    cov_s = src_c.t() @ src_c / max(source.size(0) - 1, 1)
    cov_t = tgt_c.t() @ tgt_c / max(target.size(0) - 1, 1)
    return (cov_s - cov_t).pow(2).sum() / (4 * d * d)


@torch.no_grad()
def coral_distance(source: torch.Tensor, target: torch.Tensor) -> float:
    """CORAL distance as a *measurement* of the gap between two feature sets.

    Numerically identical to :func:`coral_loss` but detached and returned as a Python
    float: the same ``||C_s - C_t||_F^2 / (4 d^2)`` covariance discrepancy, used here to
    quantify a domain gap rather than to backpropagate through it. Because the features
    always come from the SAME frozen ConvNeXt under fixed ImageNet normalisation, the
    number is comparable across datasets/runs, so a drop after data-side appearance work
    is a real reduction of the synthetic->real gap. NOTE (second-order only): CORAL is
    invariant to the feature MEAN, so it sees a covariance/correlation mismatch but not a
    pure mean shift -- read it alongside ``mean_l2`` in :func:`domain_gap_report`.
    """
    return float(coral_loss(source, target))


@torch.no_grad()
def _within_domain_floor(feats: torch.Tensor, seed: int) -> float:
    """CORAL distance between two disjoint random halves of ONE domain.

    This is the sampling-noise FLOOR: the CORAL distance you measure between two samples
    of the *same* distribution at this sample size. A cross-domain distance is only
    meaningful relative to this floor (see ``gap_ratio``).
    """
    n = feats.size(0)
    if n < 4:
        return 0.0
    g = torch.Generator().manual_seed(seed)
    perm = torch.randperm(n, generator=g).to(feats.device)
    half = n // 2
    return coral_distance(feats[perm[:half]], feats[perm[half:2 * half]])


@torch.no_grad()
def domain_gap_report(source: torch.Tensor, target: torch.Tensor, seed: int = 0) -> dict:
    """Quantify the source(synthetic)->target(real) gap on cached deep features.

    Returns a dict combining the headline CORAL distance with the context needed to read
    it honestly:
      - ``coral_distance``   : cross-domain second-order gap (the headline number).
      - ``within_source`` / ``within_target`` / ``within_mean`` : same-distribution floors
        (random-half split), i.e. how much CORAL distance is pure sampling noise.
      - ``gap_ratio``        : ``coral_distance / within_mean``. >>1 means the domains are
        far apart beyond sampling noise; ~1 means indistinguishable at this fidelity.
      - ``mean_l2``          : L2 distance between per-feature means (FIRST-order gap that
        CORAL itself cannot see).
      - ``rms_source`` / ``rms_target`` / ``rms_ratio`` : mean per-feature std (feature
        spread); ``rms_ratio`` = source/target < 1 means the synthetic set is less diverse.

    Inputs are ``(n, d)`` feature matrices; source and target need not share ``n``.
    """
    if source.dim() != 2 or target.dim() != 2:
        raise ValueError(
            f"expected 2-D (n, d) feature matrices; got {tuple(source.shape)} / {tuple(target.shape)}"
        )
    src = source.float()
    tgt = target.float()
    cross = coral_distance(src, tgt)
    floor_s = _within_domain_floor(src, seed)
    floor_t = _within_domain_floor(tgt, seed + 1)
    floor = 0.5 * (floor_s + floor_t)
    mean_l2 = float((src.mean(dim=0) - tgt.mean(dim=0)).norm())
    rms_s = float(src.std(dim=0).mean())
    rms_t = float(tgt.std(dim=0).mean())
    return {
        "coral_distance": cross,
        "within_source": floor_s,
        "within_target": floor_t,
        "within_mean": floor,
        "gap_ratio": (cross / floor) if floor > 0 else float("inf"),
        "mean_l2": mean_l2,
        "rms_source": rms_s,
        "rms_target": rms_t,
        "rms_ratio": (rms_s / rms_t) if rms_t > 0 else float("inf"),
        "n_source": int(src.size(0)),
        "n_target": int(tgt.size(0)),
        "feature_dim": int(src.size(1)),
    }


class GradientReversalFunction(torch.autograd.Function):
    """Gradient-reversal layer for adversarial domain adaptation (DANN).

    Identity on the forward pass; multiplies the incoming gradient by ``-lambda`` on the
    backward pass, so a domain classifier stacked on top drives the shared feature
    extractor toward domain-invariant features.
    """

    @staticmethod
    def forward(ctx, x: torch.Tensor, lambda_: float) -> torch.Tensor:
        ctx.lambda_ = lambda_
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output: torch.Tensor):
        # One gradient per forward input; lambda_ is a plain float -> None.
        return -ctx.lambda_ * grad_output, None


def grad_reverse(x: torch.Tensor, lambda_: float = 1.0) -> torch.Tensor:
    """Convenience wrapper around :class:`GradientReversalFunction`."""
    return GradientReversalFunction.apply(x, lambda_)


class DomainClassifier(nn.Module):
    """Binary domain discriminator for DANN (source=0 vs target=1).

    Has trainable parameters, so it can never be byte-identical: the trainer must
    instantiate it ONLY when DANN is enabled (mirroring the conditional registration of
    the uncertainty-weighting params in ``losses.py``), and fold its parameters into the
    optimizer via the existing ``list(loss_fn.parameters())`` path.
    """

    def __init__(self, feature_dim: int, hidden_dim: int = 256, dropout: float = 0.5) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """Return per-sample domain logits, shape (batch,)."""
        return self.net(features).squeeze(-1)
