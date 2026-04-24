"""
Models for KiDKNet.

This module provides the ConvNeXt-based force prediction model,
focusing on force vector prediction from images.
"""

from .force_net import ForceNet
from .backbones import get_backbone, BACKBONE_REGISTRY
from .heads import get_head, HEADS_REGISTRY

from typing import Dict, Any


def build_model(config: Dict[str, Any]) -> ForceNet:
    """
    Build a model from a configuration dictionary.
    
    Args:
        config: Configuration dictionary with model specifications
    
    Returns:
        ForceNet: Configured model
    """
    model_name = config.get("name", "forcenet")
    
    if model_name == "forcenet":
        return ForceNet.from_config(config)
    else:
        raise ValueError(f"Unknown model name: {model_name}")


__all__ = [
    "ForceNet",
    "get_backbone",
    "get_head",
    "build_model",
    "BACKBONE_REGISTRY",
    "HEADS_REGISTRY",
]
