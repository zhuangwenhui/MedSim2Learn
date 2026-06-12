"""Deterministic camera placement around a contact point."""

import numpy as np
import open3d as o3d

from ..config import CameraConfig
from .geometry import intrinsic_matrix, look_at_extrinsic


def build_camera_params(center, cam_cfg=None):
    """Fixed oblique laparoscope PinholeCameraParameters centered on `center`.

    The eye sits `standoff_mm` away from the contact point along the
    configured eye direction; the look-at target is the contact point itself.
    Returns (PinholeCameraParameters, eye_world).
    """
    cfg = cam_cfg if cam_cfg is not None else CameraConfig()
    center = np.asarray(center, float)
    d = np.asarray(cfg.eye_dir, float)
    d = d / np.linalg.norm(d)
    eye = center + d * cfg.standoff_mm
    extr = look_at_extrinsic(eye, center, np.asarray(cfg.up, float))
    intr = intrinsic_matrix(cfg.width, cfg.height, cfg.fov_deg)
    cam = o3d.camera.PinholeCameraParameters()
    cam.intrinsic = intr
    cam.extrinsic = extr
    return cam, eye
