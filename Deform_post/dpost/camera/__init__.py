"""Camera placement for sequence rendering.

Every renderer in this package consumes the same artifact: an Open3D
PinholeCameraParameters JSON (intrinsic + extrinsic). The submodules differ
only in where that camera comes from:

- geometry: look-at extrinsics and pinhole intrinsics from explicit vectors
- auto: deterministic placement around a contact point (config-driven)
"""

from .auto import build_camera_params
from .geometry import intrinsic_matrix, look_at_extrinsic

__all__ = ["build_camera_params", "intrinsic_matrix", "look_at_extrinsic"]
