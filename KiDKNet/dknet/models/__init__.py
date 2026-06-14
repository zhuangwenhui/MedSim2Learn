"""
Models for KiDKNet.

This module provides the ConvNeXt-based force prediction model,
focusing on force vector prediction from images.
"""

import torch.nn as nn

from .force_net import ForceNet
from .sequence_force_net import SequenceForceNet
from .backbones import get_backbone, BACKBONE_REGISTRY
from .heads import get_head, HEADS_REGISTRY

from typing import Dict, Any


def build_model(config: Dict[str, Any]) -> nn.Module:
    """
    Build a model from a configuration dictionary.

    Args:
        config: Configuration dictionary with model specifications

    Returns:
        nn.Module: Configured model. ``forcenet`` -> single-image
        :class:`ForceNet`; ``sequence_forcenet`` -> clip-to-per-frame
        :class:`SequenceForceNet`.
    """
    model_name = config.get("name", "forcenet")

    if model_name == "forcenet":
        return ForceNet.from_config(config)
    if model_name == "sequence_forcenet":
        return SequenceForceNet.from_config(config)
    raise ValueError(f"Unknown model name: {model_name}")


__all__ = [
    "ForceNet",
    "SequenceForceNet",
    "get_backbone",
    "get_head",
    "build_model",
    "BACKBONE_REGISTRY",
    "HEADS_REGISTRY",
]
