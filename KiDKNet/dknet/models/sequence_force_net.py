"""SequenceForceNet: per-frame force regression over a video clip.

Upgrades the single-image :class:`ForceNet` to a sequence-to-sequence model:
it consumes a clip and predicts one 3D force vector per frame. A shared frame
encoder (ConvNeXt) produces per-frame features that a temporal module
(:mod:`dknet.models.temporal`) refines into per-frame forces.

Two input modes keep the heavy frame encoder out of the training graph when
possible (the recommended, resource-safe path for long clips):

- ``feature`` (default): input is a precomputed feature sequence ``(B, T, F)``
  (ConvNeXt features cached once via the feature-precompute step). Only the
  temporal module trains. This avoids running ConvNeXt over ``B*T`` frames every
  step, which would otherwise dominate compute/memory for ``T`` in the hundreds.
- ``image``: input is raw frames ``(B, T, 3, H, W)``; the shared encoder runs
  over all ``B*T`` frames (under ``no_grad`` and in eval mode when frozen) and
  the temporal module trains on the resulting features. Used for optional
  end-to-end fine-tuning of the top encoder stages.

``forward`` returns a LIST of ``(B, T, 3)`` stage outputs (one per MS-TCN stage,
or a single element for GRU/LSTM/Transformer) so the sequence loss can apply
deep supervision uniformly.
"""

from typing import Any, Dict, List, Optional, cast

import torch
import torch.nn as nn

from .backbones import get_backbone
from .backbones.convnext import CONVNEXT_FEATURE_DIMS
from .temporal import build_temporal


class SequenceForceNet(nn.Module):
    """Sequence-to-sequence force regressor (clip -> per-frame force)."""

    def __init__(
        self,
        temporal_type: str,
        temporal_config: Optional[Dict[str, Any]] = None,
        input_mode: str = "feature",
        backbone_name: str = "convnext",
        backbone_config: Optional[Dict[str, Any]] = None,
        in_features: Optional[int] = None,
    ) -> None:
        """Initialize a SequenceForceNet.

        Args:
            temporal_type: Temporal module key (``tcn``/``gru``/``lstm``/
                ``transformer``).
            temporal_config: Keyword args for the temporal module.
            input_mode: ``feature`` (precomputed features) or ``image`` (raw
                frames through the shared encoder).
            backbone_name: Frame encoder name (image mode); also names the
                encoder whose feature dim is used in feature mode.
            backbone_config: Frame encoder config (``size``, ``pretrained``,
                ``freeze_backbone``).
            in_features: Per-frame feature dim. Required for non-ConvNeXt feature
                sources; otherwise derived from the ConvNeXt ``size``.
        """
        super().__init__()
        self.input_mode = str(input_mode).lower()
        if self.input_mode not in ("feature", "image"):
            raise ValueError(
                f"input_mode must be 'feature' or 'image', got {input_mode!r}"
            )

        backbone_config = dict(backbone_config or {})
        self.freeze_backbone = bool(backbone_config.get("freeze_backbone", False))
        self.backbone: Optional[nn.Module] = None

        if self.input_mode == "image":
            self.backbone = get_backbone(backbone_name, backbone_config)
            feat_dim = cast(int, self.backbone.out_features)
        else:
            feat_dim = self._infer_feature_dim(
                backbone_name, backbone_config, in_features
            )

        self.in_features = feat_dim
        self.temporal = build_temporal(
            temporal_type, feat_dim, temporal_config or {}
        )
        self.name = f"sequence_forcenet_{temporal_type}"

    @staticmethod
    def _infer_feature_dim(
        backbone_name: str,
        backbone_config: Dict[str, Any],
        in_features: Optional[int],
    ) -> int:
        """Resolve the per-frame feature dim for feature mode."""
        if in_features is not None:
            return int(in_features)
        if backbone_name == "convnext":
            size = backbone_config.get("size", "base")
            if size not in CONVNEXT_FEATURE_DIMS:
                raise ValueError(
                    f"Unknown ConvNeXt size {size!r}; cannot infer feature dim. "
                    f"Choices: {sorted(CONVNEXT_FEATURE_DIMS)}"
                )
            return CONVNEXT_FEATURE_DIMS[size]
        raise ValueError(
            "feature-mode SequenceForceNet needs 'in_features' for non-ConvNeXt "
            f"encoders (got backbone {backbone_name!r})."
        )

    def _encode_frames(self, frames: torch.Tensor) -> torch.Tensor:
        """Encode ``(B, T, 3, H, W)`` frames to features ``(B, T, F)``."""
        assert self.backbone is not None, "image mode requires a backbone"
        b, t = frames.shape[0], frames.shape[1]
        flat = frames.reshape(b * t, *frames.shape[2:])
        if self.freeze_backbone:
            with torch.no_grad():
                feats = self.backbone(flat)
        else:
            feats = self.backbone(flat)
        return feats.reshape(b, t, -1)

    def forward(self, x: torch.Tensor) -> List[torch.Tensor]:
        """Predict per-frame forces.

        Args:
            x: ``(B, T, F)`` in feature mode, or ``(B, T, 3, H, W)`` in image mode.

        Returns:
            List of ``(B, T, 3)`` per-stage predictions (last is the final one).
        """
        if self.input_mode == "image":
            if x.dim() != 5:
                raise ValueError(
                    f"image mode expects (B, T, 3, H, W), got {tuple(x.shape)}"
                )
            features = self._encode_frames(x)
        else:
            if x.dim() != 3:
                raise ValueError(
                    f"feature mode expects (B, T, F), got {tuple(x.shape)}"
                )
            features = x
        return self.temporal(features)

    def train(self, mode: bool = True) -> "SequenceForceNet":
        """Keep a frozen encoder in eval mode (disables stochastic depth)."""
        super().train(mode)
        if self.backbone is not None and self.freeze_backbone:
            self.backbone.eval()
        return self

    def get_parameter_groups(
        self, weight_decay: float = 1e-4
    ) -> List[Dict[str, Any]]:
        """Decay/no-decay parameter groups over the trainable parameters."""
        decay, no_decay = [], []
        for module in self.modules():
            if list(module.children()):
                continue
            for pname, param in module.named_parameters(recurse=False):
                if not param.requires_grad:
                    continue
                is_norm = isinstance(
                    module,
                    (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d,
                     nn.LayerNorm, nn.GroupNorm),
                )
                if is_norm or pname.endswith("bias"):
                    no_decay.append(param)
                else:
                    decay.append(param)
        return [
            {"params": decay, "weight_decay": weight_decay},
            {"params": no_decay, "weight_decay": 0.0},
        ]

    @staticmethod
    def from_config(config: Dict[str, Any]) -> "SequenceForceNet":
        """Build from a model config dict.

        Expected keys:
            - ``temporal``: ``{type, config}`` for the temporal module.
            - ``input_mode``: ``feature`` (default) or ``image``.
            - ``backbone``: ``{name, config}`` (config has ``size`` etc.).
            - ``in_features``: optional explicit feature dim.
        """
        temporal_cfg = config.get("temporal", {}) or {}
        backbone_cfg = config.get("backbone", {}) or {}
        return SequenceForceNet(
            temporal_type=temporal_cfg.get("type", "tcn"),
            temporal_config=temporal_cfg.get("config", {}),
            input_mode=config.get("input_mode", "feature"),
            backbone_name=backbone_cfg.get("name", "convnext"),
            backbone_config=backbone_cfg.get("config", {}),
            in_features=config.get("in_features"),
        )
