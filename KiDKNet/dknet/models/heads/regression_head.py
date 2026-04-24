"""
Regression head for force prediction in KiDKNet.

This module provides a regression head that takes features from a backbone
and predicts force vectors.
"""

import torch
import torch.nn as nn
from typing import Dict, Any, List


class ForceRegressionHead(nn.Module):
    """
    Regression head for predicting force vectors from image features.
    
    This module takes features from a backbone model and outputs a 3D force vector
    (force_x, force_y, force_z).
    
    Attributes:
        in_features (int): Number of input features from the backbone
        hidden_dims (List[int]): Dimensions of hidden layers
        dropout_rate (float): Dropout rate for regularization
        layers (nn.Sequential): Sequential container of the regression layers
    """
    def __init__(
        self,
        in_features: int,
        hidden_dims: List[int] = [1024, 512, 256],
        dropout_rate: float = 0.1,
        normalize_output: bool = False,
    ) -> None:
        """
        Initialize ForceRegressionHead.

        Args:
            in_features (int): Number of input features from the backbone
            hidden_dims (List[int]): Dimensions of hidden layers
            dropout_rate (float): Dropout rate for regularization
            normalize_output (bool): Whether to normalize the output force vector
        """
        super().__init__()

        self.in_features = in_features
        self.hidden_dims = hidden_dims
        self.dropout_rate = dropout_rate
        self.normalize_output = normalize_output

        layers = []
        prev_dim = in_features
        for dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, dim),
                nn.BatchNorm1d(dim),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout_rate),
            ])
            prev_dim = dim
        layers.append(nn.Linear(prev_dim, 3))

        self.layers = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass for force regression.
        
        Args:
            x (torch.Tensor): Input feature tensor of shape (B, in_features)
        
        Returns:
            torch.Tensor: Predicted force vector of shape (B, 3)
        """
        force = self.layers(x)
        if self.normalize_output:
            force = force / (torch.norm(force, dim=1, keepdim=True) + 1e-8)

        return force

    @staticmethod
    def from_config(config: Dict[str, Any], in_features: int) -> "ForceRegressionHead":
        return ForceRegressionHead(
            in_features=in_features,
            hidden_dims=config.get("hidden_dims", [1024, 512, 256]),
            dropout_rate=config.get("dropout_rate", 0.1),
            normalize_output=config.get("normalize_output", False),
        )
