from .convnext import ConvNeXtBackbone

from typing import Dict, Any, Optional
from torch import nn


BACKBONE_REGISTRY = {
    "convnext": ConvNeXtBackbone,
}


def get_backbone(name: str, config: Optional[Dict[str, Any]] = None) -> nn.Module:
    """
    Factory function to create a backbone model by name.
    
    Args:
        name: Backbone name. KiDKNet supports only 'convnext'.
        config: Configuration dictionary for the backbone
    
    Returns:
        nn.Module: Instantiated backbone model
    
    Raises:
        ValueError: If the backbone name is not recognized
    """
    if name not in BACKBONE_REGISTRY:
        raise ValueError(
            f"Backbone '{name}' is not supported. "
            f"Available backbones: {list(BACKBONE_REGISTRY.keys())}"
        )
    
    backbone_cls = BACKBONE_REGISTRY[name]
    
    if config is None:
        config = {}
    
    return backbone_cls.from_config(config)


__all__ = [
    "ConvNeXtBackbone",
    "get_backbone",
    "BACKBONE_REGISTRY",
]
