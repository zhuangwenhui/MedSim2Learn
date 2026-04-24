"""
Prediction heads for KiDKNet.

This module provides various prediction heads that can be attached to backbone
models for specific tasks, such as force vector regression.
"""

from .regression_head import ForceRegressionHead

from typing import Dict, Any, Optional

HEADS_REGISTRY = {
    "force_regression": ForceRegressionHead,
}


def get_head(
    name: str, 
    config: Optional[Dict[str, Any]] = None, 
    in_features: int = 0
) -> ForceRegressionHead:
    """
    Factory function to create a prediction head by name.

    Args:
        name: Head name (e.g., 'force_regression')
        config: Configuration dictionary for the head
        in_features: Number of input features from the backbone

    Returns:
        ForceRegressionHead: Instantiated prediction head

    Raises:
        ValueError: If the head name is not recognized
    """
    if name not in HEADS_REGISTRY:
        raise ValueError(
            f"Head '{name}' not found. \n"
            f"Available heads: {list(HEADS_REGISTRY.keys())}"
        )

    head_cls = HEADS_REGISTRY[name]

    if config is None:
        config = {}

    return head_cls.from_config(config, in_features)


__all__ = ["ForceRegressionHead", "get_head", "HEADS_REGISTRY"]
