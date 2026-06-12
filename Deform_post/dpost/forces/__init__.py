"""Force trajectory handling.

- real: load real sensor recordings and rotate them into the model frame
  (the exact-replay source for DeformSim's FORCE_LIST_CSV mode)
- gen: synthesize new sensor-frame trajectories anchored to a real recording
  (resample mode: scale/time-warp/jitter inside the real envelope)
"""

from .gen import generate_variants, resample_trajectory, validate_resample
from .real import (
    load_real_forces,
    map_forces,
    sample_id,
    sensor_to_model_rotation,
    subsample_indices,
)

__all__ = [
    "generate_variants",
    "load_real_forces",
    "map_forces",
    "resample_trajectory",
    "sample_id",
    "sensor_to_model_rotation",
    "subsample_indices",
    "validate_resample",
]
