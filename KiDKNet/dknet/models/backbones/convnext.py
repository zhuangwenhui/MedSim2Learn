"""
ConvNeXt backbone implementation for KiDKNet.

This module provides ConvNeXt models of various sizes that can be used as
feature extractors for the force prediction task.
"""

import torch
import torch.nn as nn
import torchvision.models as models
from typing import Dict, Any


# Pooled feature dimensionality per ConvNeXt size. Exposed so the sequence path
# can size a temporal module's input without instantiating (and downloading the
# pretrained weights of) the backbone when training on precomputed features.
CONVNEXT_FEATURE_DIMS = {
    "tiny": 768,
    "small": 768,
    "base": 1024,
    "large": 1536,
}


class ConvNeXtBackbone(nn.Module):
    """
    ConvNeXt backbone for force prediction from images.
    
    This class wraps PyTorch's pre-implemented ConvNeXt models, removing the
    classification head and exposing the feature extractor.
    
    Attributes:
        name (str): Name of the backbone
        size (str): Size of the ConvNeXt model ('tiny', 'small', 'base', 'large')
        pretrained (bool): Whether to use pre-trained weights
        model (nn.Module): The backbone ConvNeXt model
        out_features (int): Number of output features
    """
    
    def __init__(
        self, 
        size: str = "base", 
        pretrained: bool = True,
        freeze_backbone: bool = False,
    ) -> None:
        """
        Initialize ConvNeXt backbone.
        
        Args:
            size (str): ConvNeXt size - one of 'tiny', 'small', 'base', 'large'
            pretrained (bool): Whether to use pre-trained weights
            freeze_backbone (bool): Whether to freeze the backbone parameters
        
        Raises:
            ValueError: If size is not one of the supported ConvNeXt sizes
        """
        super().__init__()
        
        self.name = f"convnext_{size}"
        self.size = size
        self.pretrained = pretrained
        
        convnext_registry = {
            "tiny":  (models.convnext_tiny,  models.ConvNeXt_Tiny_Weights.DEFAULT),
            "small": (models.convnext_small, models.ConvNeXt_Small_Weights.DEFAULT),
            "base":  (models.convnext_base,  models.ConvNeXt_Base_Weights.DEFAULT),
            "large": (models.convnext_large, models.ConvNeXt_Large_Weights.DEFAULT),
        }

        if size not in convnext_registry:
            raise ValueError(f"ConvNeXt size must be one of {list(convnext_registry.keys())}")

        model_fn, default_weights = convnext_registry[size]
        self.out_features = CONVNEXT_FEATURE_DIMS[size]

        weights = default_weights if pretrained else None
        self.model = model_fn(weights=weights)

        # Replace classifier with identity; ConvNeXt adaptive pool outputs [B, C, 1, 1]
        # which the original classifier flattens — Identity preserves that flatten step
        self.model.classifier = nn.Sequential(nn.Identity())

        if freeze_backbone:
            for param in self.model.parameters():
                param.requires_grad = False
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass for feature extraction.

        Args:
            x: Input image tensor of shape (B, C, H, W).

        Returns:
            Feature tensor of shape (B, out_features).
        """
        features = self.model(x)
        if features.ndim > 2:
            features = features.flatten(1)
        return features
    
    def get_output_shape(self) -> tuple:
        """Return the backbone feature dimensionality."""
        return (self.out_features,)
    
    @staticmethod
    def from_config(config: Dict[str, Any]) -> "ConvNeXtBackbone":
        return ConvNeXtBackbone(
            size=config.get("size", "base"),
            pretrained=config.get("pretrained", True),
            freeze_backbone=config.get("freeze_backbone", False),
        )
