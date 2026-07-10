"""
ForceNet model for predicting force vectors from images.

This module combines a backbone feature extractor with a regression head
to predict 3D force vectors from input images.
"""

import torch
import torch.nn as nn
from typing import cast, Dict, Any, Optional, List

from .backbones import get_backbone
from .heads import get_head


class ForceNet(nn.Module):
    """
    End-to-end model for predicting force vectors from images.

    This model combines a backbone feature extractor with a regression head
    to predict 3D force vectors from input images.
    
    Attributes:
        backbone (nn.Module): Backbone feature extractor
        head (nn.Module): Regression head for force prediction
        name (str): Model name
    """
    def __init__(
        self,
        backbone_name: str,
        backbone_config: Optional[Dict[str, Any]] = None,
        head_name: str = "force_regression",
        head_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize ForceNet model.

        Args:
            backbone_name: Name of the backbone to use
            backbone_config: Configuration for the backbone
            head_name: Name of the prediction head to use
            head_config: Configuration for the prediction head
        """
        super().__init__()

        self.backbone = get_backbone(backbone_name, backbone_config)

        if head_config is None:
            head_config = {}
        self.head = get_head(
            head_name,
            head_config,
            in_features=cast(int, self.backbone.out_features),
        )

        # Set model name
        self.name = f"forcenet_{backbone_name}"

    def forward(self, x: torch.Tensor, return_features: bool = False):
        """
        Forward pass for force prediction.

        Args:
            x: Input image tensor of shape (B, C, H, W)
            return_features: when True, also return the pre-head backbone feature
                (B, F) so a domain-adaptation term (e.g. CORAL) can reuse the same
                forward instead of running the encoder twice. Default False keeps
                the return type and the default training path byte-identical.

        Returns:
            torch.Tensor: Predicted force vector (B, 3); or (pred, feature) when
            ``return_features`` is True.
        """
        feat = self.backbone(x)
        pred = self.head(feat)
        if return_features:
            return pred, feat
        return pred

    def get_parameter_groups(self, weight_decay: float = 1e-4) -> List[Dict[str, Any]]:
        """
        Get parameter groups for optimizer configuration.

        This method separates parameters for weight decay optimization.

        Args:
            weight_decay: Weight decay factor

        Returns:
            List[Dict[str, Any]]: Parameter groups for optimizer
        """
        decay_params = []
        no_decay_params = []

        for module in self.modules():
            if list(module.children()):
                continue
            for name, param in module.named_parameters(recurse=False):
                if param.requires_grad:
                    # BatchNorm params and biases are excluded from weight decay
                    if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)) or name.endswith("bias"):
                        no_decay_params.append(param)
                    else:
                        decay_params.append(param)

        return [
            {"params": decay_params, "weight_decay": weight_decay},
            {"params": no_decay_params, "weight_decay": 0.0}
        ]

    @staticmethod
    def from_config(config: Dict[str, Any]) -> "ForceNet":
        """
        Create a ForceNet model from a configuration dictionary.

        Args:
            config: Configuration dictionary with keys:
                - backbone: Dict with 'name' and optional 'config' keys
                - head: Dict with optional 'name' and 'config' keys

        Returns:
            ForceNet: Configured ForceNet model
        """
        return ForceNet(
            backbone_name=config["backbone"]["name"],
            backbone_config=config["backbone"].get("config", {}),
            head_name=config["head"].get("name", "force_regression"),
            head_config=config["head"].get("config", {}),
        )
