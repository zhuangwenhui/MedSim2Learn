# dknet/utils/losses.py
import torch
import torch.nn as nn
import torch.nn.functional as F
import warnings
from typing import Any, Dict, Optional, Tuple


def _ensure_numeric(value: Any, default: float, name: str) -> float:
    """
    Safely convert value to float; fallback to default with warning on failure.
    """
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            warnings.warn(
                f"Invalid {name} value '{value}', using default {default}"
            )
            return default
    if isinstance(value, (int, float)):
        return float(value)
    warnings.warn(
        f"Unexpected {name} type {type(value)}, using default {default}"
    )

    return default


#==============================================================#
#                        Angle Distance                        #
#==============================================================#
class CosineDistance(nn.Module):
    """
    Cosine Similarity based Distance
    Distance = 1 - cosine_similarity(pred, target)
    """
    def __init__(self, epsilon: float = 1e-8, reduction: str = 'mean') -> None:
        super().__init__()
        # Make sure epsilon is a numeric value
        self.epsilon = _ensure_numeric(epsilon, default=1e-8, name="epsilon")
        self.reduction = reduction
    
    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            pred:  [batch_size, 3]
            target:  [batch_size, 3]
        """
        # Angle distances care about direction only, not magnitude.
        # L2-normalizing removes magnitude influence on gradients.
        # Cosine similarity is defined on unit vectors.
        pred_norm = F.normalize(pred, p=2, dim=1, eps=self.epsilon)
        target_norm = F.normalize(target, p=2, dim=1, eps=self.epsilon)
        cos_sim = (pred_norm * target_norm).sum(dim=1)
        cos_distance = 1.0 - cos_sim
        
        if self.reduction == 'mean':
            return cos_distance.mean()
        elif self.reduction == 'sum':
            return cos_distance.sum()
        elif self.reduction == 'none':
            # Return per-sample distances [batch_size]
            return cos_distance
        else:
            raise ValueError(f"Unsupported reduction: {self.reduction}")


class SineDistance(nn.Module):
    """
    Sine Similarity based Distance
    Distance = sin(theta) = sqrt(1 - cos^2(theta))
    theta = angle between pred and target
    """
    def __init__(self, epsilon: float = 1e-8, reduction: str = 'mean') -> None:
        super().__init__()
        self.epsilon = _ensure_numeric(epsilon, default=1e-8, name="epsilon")
        self.reduction = reduction

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        pred_norm = F.normalize(pred, p=2, dim=1, eps=self.epsilon)
        target_norm = F.normalize(target, p=2, dim=1, eps=self.epsilon)
        cos_sim = (pred_norm * target_norm).sum(dim=1)
        cos_sim = torch.clamp(cos_sim, -1.0 + self.epsilon, 1.0 - self.epsilon)
        sin_sq = torch.clamp(1.0 - cos_sim.pow(2), min=0.0)
        sin_distance = torch.sqrt(sin_sq + self.epsilon)

        if self.reduction == 'mean':
            return sin_distance.mean()
        elif self.reduction == 'sum':
            return sin_distance.sum()
        elif self.reduction == 'none':
            return sin_distance
        else:
            raise ValueError(f"Unsupported reduction: {self.reduction}")


class SquaredCosineDistance(nn.Module):
    """
    Squared Cosine Similarity based Distance
    Distance = (1 - cosine_similarity(pred, target))^2
    """
    def __init__(self, epsilon: float = 1e-8, reduction: str = 'mean') -> None:
        super().__init__()
        self.epsilon = _ensure_numeric(epsilon, default=1e-8, name="epsilon")
        self.reduction = reduction

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        pred_norm = F.normalize(pred, p=2, dim=1, eps=self.epsilon)
        target_norm = F.normalize(target, p=2, dim=1, eps=self.epsilon)
        cos_sim = (pred_norm * target_norm).sum(dim=1)
        cos_sim = torch.clamp(cos_sim, -1.0 + self.epsilon, 1.0 - self.epsilon)
        cos_distance = 1.0 - cos_sim
        squared_distance = cos_distance.pow(2)

        if self.reduction == 'mean':
            return squared_distance.mean()
        elif self.reduction == 'sum':
            return squared_distance.sum()
        elif self.reduction == 'none':
            return squared_distance
        else:
            raise ValueError(f"Unsupported reduction: {self.reduction}")


#==============================================================#
#                         Loss Factory                         #
#==============================================================#
class ForceLoss:
    """Factory for loss functions."""
    
    @staticmethod
    def get_loss(loss_type: str = 'COMBINED', **kwargs: Any) -> nn.Module:
        """
        Return the configured loss function with filtered parameters.
        
        Args:
            loss_type (str): Supported types:
                - 'MSE': standard MSE on 3D force vectors
                - 'COMBINED': magnitude + angle composite loss
            **kwargs: Additional loss parameters
        """
        loss_key = str(loss_type)

        if loss_key == 'MSE':
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in ['reduction']}
            return nn.MSELoss(**filtered_kwargs)

        if loss_key == 'COMBINED':
            return MagnitudeAngleLoss(**kwargs)

        if loss_key == 'SEQUENCE_COMBINED':
            return SequenceMagnitudeAngleLoss(**kwargs)

        raise ValueError(
            f"Unsupported loss type: {loss_type}. Use 'MSE', 'COMBINED', "
            "or 'SEQUENCE_COMBINED'."
        )


# Magnitude distance can be MSE, MAE, Huber, SmoothL1
# Not need to define separate classes for them 
# since they are standard losses
class MagnitudeAngleLoss(nn.Module):
    """
    Magnitude and Angle Combined Loss
    Loss = lambda * magnitude_distance + (1-lambda) * angle_distance
    """
    def __init__(
        self,
        magnitude_distance: str = 'mse',
        angle_distance: str = 'cosine',
        lambda_magnitude: float = 0.2,
        normalize_losses: bool = True,
        epsilon: float = 1e-8,
        reduction: str = 'mean',
        magnitude_kwargs: Optional[Dict[str, Any]] = None,
        angle_kwargs: Optional[Dict[str, Any]] = None,
        weighting: str = 'fixed',
        uncertainty_init: float = 0.0,
        uncertainty_clamp: float = 10.0,
    ) -> None:
        """
        Args:
            magnitude_distance: Magnitude distance type ('mse', 'mae',
                'huber', 'smooth_l1')
            angle_distance: Angle distance type ('cosine', 'sine',
                'cosine_squared')
            lambda_magnitude: Magnitude weight; angle weight is
                (1 - lambda_magnitude)
            normalize_losses: Normalize magnitude/angle scales
            epsilon: Numerical stability constant
            reduction: Reduction mode ('mean', 'sum', 'none')
            magnitude_kwargs: Extra params for magnitude distance
            angle_kwargs: Extra params for angle distance
        """
        super().__init__()
        self.magnitude_distance = str(magnitude_distance).lower()
        self.angle_distance = str(angle_distance).lower()
        # Ensure numeric parameters are valid
        self.lambda_magnitude = _ensure_numeric(
            lambda_magnitude, 0.2, "lambda_magnitude"
        )
        self.lambda_angle = 1.0 - self.lambda_magnitude
        self.normalize_losses = bool(normalize_losses)
        self.epsilon = _ensure_numeric(epsilon, 1e-8, "epsilon")
        self.reduction = reduction
        # Loss-weighting scheme: 'fixed' (lambda) or 'uncertainty' (Kendall).
        self.weighting = str(weighting).lower()
        if self.weighting not in ('fixed', 'uncertainty'):
            raise ValueError(
                "weighting must be 'fixed' or 'uncertainty', got "
                f"{weighting!r}"
            )
        self.use_uncertainty_weighting = (self.weighting == 'uncertainty')
        self.uncertainty_init = _ensure_numeric(
            uncertainty_init, 0.0, "uncertainty_init"
        )
        self.uncertainty_clamp = abs(
            _ensure_numeric(uncertainty_clamp, 10.0, "uncertainty_clamp")
        )
        
        if not isinstance(magnitude_kwargs, dict):
            magnitude_kwargs = {}
        if not isinstance(angle_kwargs, dict):
            angle_kwargs = {}
        
        self.magnitude_kwargs = magnitude_kwargs
        self.angle_kwargs = angle_kwargs
        
        self.angle_loss_fn = self._build_angle_loss_fn(
            self.angle_distance, self.angle_kwargs
        )
        
        # Track EMA stats for optional normalization
        if self.normalize_losses:
            self.register_buffer('magnitude_loss_ema', torch.tensor(1.0))
            self.register_buffer('angle_loss_ema', torch.tensor(1.0))
            self.ema_momentum = 0.99

        # Kendall homoscedastic uncertainty weighting: two learnable scalar
        # log-variances. Registered ONLY when enabled so the state_dict /
        # parameter list stay byte-identical for the default 'fixed' path.
        if self.use_uncertainty_weighting:
            self.log_var_magnitude = nn.Parameter(
                torch.tensor(float(self.uncertainty_init))
            )
            self.log_var_angle = nn.Parameter(
                torch.tensor(float(self.uncertainty_init))
            )
    
    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            pred: Predicted force vectors [batch_size, 3]
            target: Target force vectors [batch_size, 3]
        """
        # Per-sample losses shape: [batch_size]
        magnitude_loss = self._compute_magnitude_distance(pred, target)
        angle_loss = self.angle_loss_fn(pred, target)
        
        # Optionally normalize losses
        if self.normalize_losses:
            # Update EMA statistics during training
            if self.training:
                current_mag_loss = magnitude_loss.mean().detach()
                current_ang_loss = angle_loss.mean().detach()
                
                self.magnitude_loss_ema = (
                    self.ema_momentum * self.magnitude_loss_ema
                    + (1 - self.ema_momentum) * current_mag_loss
                )
                self.angle_loss_ema = (
                    self.ema_momentum * self.angle_loss_ema
                    + (1 - self.ema_momentum) * current_ang_loss
                )
            normalized_magnitude_loss = magnitude_loss / (
                self.magnitude_loss_ema + self.epsilon
            )
            normalized_angle_loss = angle_loss / (
                self.angle_loss_ema + self.epsilon
            )
            
            mag_term = normalized_magnitude_loss
            ang_term = normalized_angle_loss
        else:
            mag_term = magnitude_loss
            ang_term = angle_loss

        if self.use_uncertainty_weighting:
            # Kendall homoscedastic: exp(-s)*L + s, per task, summed. Scalars
            # broadcast over [B]; correct under reduction='mean' (the default
            # and the value SequenceMagnitudeAngleLoss forces).
            s_m = self.log_var_magnitude.clamp(
                -self.uncertainty_clamp, self.uncertainty_clamp
            )
            s_a = self.log_var_angle.clamp(
                -self.uncertainty_clamp, self.uncertainty_clamp
            )
            combined_loss = (
                torch.exp(-s_m) * mag_term + s_m
                + torch.exp(-s_a) * ang_term + s_a
            )
        else:
            combined_loss = (
                self.lambda_magnitude * mag_term
                + self.lambda_angle * ang_term
            )
        
        if self.reduction == 'mean':
            return combined_loss.mean()
        elif self.reduction == 'sum':
            return combined_loss.sum()
        elif self.reduction == 'none':
            return combined_loss
        else:
            raise ValueError(f"Unsupported reduction: {self.reduction}")
    
    def _build_angle_loss_fn(
        self, angle_distance: str, angle_kwargs: Dict[str, Any]
    ) -> nn.Module:
        """
        Build the angle distance loss module.
        
        Returns:
            nn.Module: Angle distance loss instance
        """
        angle_key = angle_distance.lower()
        filtered_kwargs = {
            k: v
            for k, v in angle_kwargs.items()
            if k in ['epsilon', 'reduction']
        }
        # Ensure 'reduction' is set to 'none' for per-sample loss
        filtered_kwargs['reduction'] = 'none'
        
        if angle_key == 'cosine':
            return CosineDistance(**filtered_kwargs)
        if angle_key == 'sine':
            return SineDistance(**filtered_kwargs)
        if angle_key == 'cosine_squared':
            return SquaredCosineDistance(**filtered_kwargs)
        
        raise ValueError(f"Unsupported angle_distance: {angle_distance}")
    
    def _compute_magnitude_distance(
        self, pred: torch.Tensor, target: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute magnitude distance.
        
        Returns:
            torch.Tensor: Per-sample magnitude distance [batch_size]
        """
        if self.magnitude_distance == 'mse':
            pred_mag = torch.norm(pred, dim=1)
            target_mag = torch.norm(target, dim=1)
            # Already reduced to [B]
            return (pred_mag - target_mag).pow(2)

        if self.magnitude_distance == 'vector_mse':
            # Per-sample vector MSE: mean squared error across x/y/z.
            component_mse = (pred - target).pow(2)  # [B, 3]
            return component_mse.mean(dim=1)
        
        if self.magnitude_distance == 'mae':
            return torch.abs(pred - target).mean(dim=1)
        
        if self.magnitude_distance == 'huber':
            delta = self.magnitude_kwargs.get('delta', 1.0)
            huber_raw = F.huber_loss(
                pred, target, reduction='none', delta=delta
            )  # [B, 3]
            return huber_raw.mean(dim=1)
        
        if self.magnitude_distance == 'smooth_l1':
            beta = self.magnitude_kwargs.get('beta', 1.0)
            smooth_raw = F.smooth_l1_loss(
                pred, target, reduction='none', beta=beta
            )  # [B, 3]
            return smooth_raw.mean(dim=1)
        
        raise ValueError(
            f"Unsupported magnitude_distance: {self.magnitude_distance}"
        )

    def get_component_losses(
        self, pred: torch.Tensor, target: torch.Tensor
    ) -> Tuple[float, float]:
        """
        Return magnitude and angle losses for monitoring/debugging.
        
        Returns:
            tuple: (magnitude_loss, angle_loss) in raw (unnormalized) scale
        """
        with torch.no_grad():
            magnitude_loss = self._compute_magnitude_distance(pred, target).mean()
            angle_loss = self.angle_loss_fn(pred, target).mean()
        return magnitude_loss.item(), angle_loss.item()
    
    def get_normalization_stats(self) -> Dict[str, float | bool | str]:
        """
        Return current normalization statistics.
        
        Returns:
            dict: Normalization statistics
        """
        stats: Dict[str, float | bool | str]
        if self.normalize_losses:
            stats = {
                'magnitude_loss_ema': self.magnitude_loss_ema.item(),
                'angle_loss_ema': self.angle_loss_ema.item(),
                'lambda_magnitude': self.lambda_magnitude,
                'lambda_angle': self.lambda_angle
            }
        else:
            stats = {
                'normalize_losses': False,
                'lambda_magnitude': self.lambda_magnitude,
                'lambda_angle': self.lambda_angle
            }
        if self.use_uncertainty_weighting:
            s_m = float(self.log_var_magnitude.detach().clamp(
                -self.uncertainty_clamp, self.uncertainty_clamp))
            s_a = float(self.log_var_angle.detach().clamp(
                -self.uncertainty_clamp, self.uncertainty_clamp))
            stats['weighting'] = 'uncertainty'
            stats['log_var_magnitude'] = s_m
            stats['log_var_angle'] = s_a
            stats['weight_magnitude'] = float(torch.exp(torch.tensor(-s_m)))
            stats['weight_angle'] = float(torch.exp(torch.tensor(-s_a)))
        return stats


#==============================================================#
#                   Sequence (per-frame) Loss                  #
#==============================================================#
class SequenceMagnitudeAngleLoss(nn.Module):
    """Per-frame magnitude+angle loss with deep supervision and smoothness.

    Wraps a :class:`MagnitudeAngleLoss` applied to every frame (the clip is
    flattened to ``(B*T, 3)``) and adds two sequence-specific terms:

    - Deep supervision: when ``pred`` is a list of per-stage outputs (MS-TCN),
      the frame loss is computed for each stage and averaged (``stage_weight_mode
      = 'uniform'``) or taken from the final stage only (``'last'``).
    - Temporal smoothness: ``lambda_smooth`` * a term on the FINAL stage's
      first differences. ``smoothness_mode='delta_match'`` matches the
      ground-truth temporal deltas ``mean((dpred - dtarget)**2)`` (rewards the
      true dynamics); ``'jitter'`` penalizes raw prediction jitter
      ``mean(dpred**2)`` (MS-TCN style, target-agnostic).

    ``forward`` accepts ``pred`` as a single ``(B, T, 3)`` tensor or a list of
    such tensors, and ``target`` as ``(B, T, 3)``.
    """

    def __init__(
        self,
        lambda_smooth: float = 0.1,
        smoothness_mode: str = 'delta_match',
        stage_weight_mode: str = 'uniform',
        **frame_loss_kwargs: Any,
    ) -> None:
        super().__init__()
        self.lambda_smooth = _ensure_numeric(
            lambda_smooth, 0.1, "lambda_smooth"
        )
        self.smoothness_mode = str(smoothness_mode).lower()
        if self.smoothness_mode not in ('delta_match', 'jitter'):
            raise ValueError(
                "smoothness_mode must be 'delta_match' or 'jitter', got "
                f"{smoothness_mode!r}"
            )
        self.stage_weight_mode = str(stage_weight_mode).lower()
        if self.stage_weight_mode not in ('uniform', 'last'):
            raise ValueError(
                "stage_weight_mode must be 'uniform' or 'last', got "
                f"{stage_weight_mode!r}"
            )
        # Per-frame loss reduces to a scalar over the flattened frames.
        frame_loss_kwargs.setdefault('reduction', 'mean')
        self.frame_loss = MagnitudeAngleLoss(**frame_loss_kwargs)

    @staticmethod
    def _as_stage_list(pred: Any) -> list:
        """Normalise ``pred`` to a list of ``(B, T, 3)`` stage tensors."""
        if isinstance(pred, (list, tuple)):
            return list(pred)
        return [pred]

    def _smoothness(
        self, pred: torch.Tensor, target: torch.Tensor
    ) -> torch.Tensor:
        """Temporal-smoothness term on the final-stage prediction."""
        if pred.size(1) < 2:
            return pred.new_zeros(())
        d_pred = pred[:, 1:] - pred[:, :-1]
        if self.smoothness_mode == 'jitter':
            return d_pred.pow(2).mean()
        d_target = target[:, 1:] - target[:, :-1]
        return (d_pred - d_target).pow(2).mean()

    def forward(self, pred: Any, target: torch.Tensor) -> torch.Tensor:
        """Combine deep-supervised per-frame loss with the smoothness term."""
        stages = self._as_stage_list(pred)
        flat_target = target.reshape(-1, target.shape[-1])
        stage_losses = [
            self.frame_loss(s.reshape(-1, s.shape[-1]), flat_target)
            for s in stages
        ]
        if self.stage_weight_mode == 'last':
            base = stage_losses[-1]
        else:
            base = torch.stack(stage_losses).mean()

        smooth = self._smoothness(stages[-1], target)
        return base + self.lambda_smooth * smooth

    def get_component_losses(
        self, pred: Any, target: torch.Tensor
    ) -> Tuple[float, float]:
        """Final-stage magnitude/angle losses (for monitoring)."""
        final = self._as_stage_list(pred)[-1]
        return self.frame_loss.get_component_losses(
            final.reshape(-1, final.shape[-1]),
            target.reshape(-1, target.shape[-1]),
        )

    def get_normalization_stats(self) -> Dict[str, float | bool | str]:
        """Delegate normalization stats to the per-frame loss."""
        stats = self.frame_loss.get_normalization_stats()
        stats['lambda_smooth'] = self.lambda_smooth
        return stats
