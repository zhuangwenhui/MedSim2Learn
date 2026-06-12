"""Camera placement for sequence rendering.

Every renderer in this package consumes the same artifact: an Open3D
PinholeCameraParameters JSON (intrinsic + extrinsic). The submodules differ
only in where that camera comes from:

- geometry: look-at extrinsics and pinhole intrinsics from explicit vectors
- auto: deterministic placement around a contact point (config-driven)
- profile: contact-frame view profiles (user-picked once, follows the contact)
- picker: interactive windowed viewpoint picking

resolve_camera() is the single entry the pipeline uses: it dispatches on
CameraConfig.mode and always returns (cam_params, eye_world, info_dict).
"""

import os

import numpy as np
import open3d as o3d

from .auto import build_camera_params
from .geometry import intrinsic_matrix, look_at_extrinsic
from .profile import (
    camera_eye_and_up,
    decompose,
    fov_deg_from_intrinsic,
    instantiate,
    load_profile,
    resolve_profile_path,
    save_profile,
)

__all__ = [
    "build_camera_params",
    "camera_eye_and_up",
    "decompose",
    "fov_deg_from_intrinsic",
    "instantiate",
    "intrinsic_matrix",
    "load_profile",
    "look_at_extrinsic",
    "resolve_camera",
    "resolve_profile_path",
    "save_profile",
]


def resolve_camera(contact_point, contact_normal, cam_cfg, cameras_dir=None):
    """Produce the sequence camera according to cam_cfg.mode.

    Returns (PinholeCameraParameters, eye_world, info) where info is a JSON
    friendly dict describing the camera for the provenance record.
    """
    mode = getattr(cam_cfg, "mode", "auto") or "auto"
    p = np.asarray(contact_point, float)

    if mode == "auto":
        cam, eye = build_camera_params(p, cam_cfg)
        info = {
            "mode": "auto",
            "width": cam_cfg.width, "height": cam_cfg.height,
            "fov_deg": cam_cfg.fov_deg, "standoff_mm": cam_cfg.standoff_mm,
            "eye": [float(x) for x in eye],
            "center": [float(x) for x in p],
            "up": [float(x) for x in cam_cfg.up],
        }
        return cam, eye, info

    if mode == "profile":
        path = resolve_profile_path(cam_cfg.profile, cameras_dir or "")
        prof = load_profile(path)
        cam, eye = instantiate(prof, p, contact_normal)
        info = {
            "mode": "profile",
            "profile": os.path.abspath(path),
            "width": prof["width"], "height": prof["height"],
            "fov_deg": prof["fov_deg"], "standoff_mm": prof["standoff_mm"],
            "eye": [float(x) for x in eye],
            "center": [float(x) for x in p],
        }
        return cam, eye, info

    if mode == "absolute":
        if not os.path.isfile(cam_cfg.absolute):
            raise FileNotFoundError(f"absolute camera JSON not found: {cam_cfg.absolute}")
        cam = o3d.io.read_pinhole_camera_parameters(cam_cfg.absolute)
        eye, _up, _fwd = camera_eye_and_up(cam.extrinsic)
        info = {
            "mode": "absolute",
            "source": os.path.abspath(cam_cfg.absolute),
            "width": int(cam.intrinsic.width), "height": int(cam.intrinsic.height),
            "fov_deg": fov_deg_from_intrinsic(cam.intrinsic),
            "standoff_mm": float(np.linalg.norm(np.asarray(eye) - p)),
            "eye": [float(x) for x in eye],
            "center": [float(x) for x in p],
        }
        return cam, eye, info

    raise ValueError(f"unknown camera mode: {mode!r}")
