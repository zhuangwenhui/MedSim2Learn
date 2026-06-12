"""Camera math: look-at extrinsics and pinhole intrinsics for Open3D."""

import numpy as np
import open3d as o3d


def look_at_extrinsic(eye, center, up):
    """World->camera 4x4 extrinsic (open3d convention: camera looks down +z,
    image y is down). Returns the matrix expected by PinholeCameraParameters."""
    eye = np.asarray(eye, float)
    center = np.asarray(center, float)
    up = np.asarray(up, float)
    f = center - eye
    f /= np.linalg.norm(f)            # forward (camera +z)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)            # right (camera +x)
    # open3d image-y points DOWN, so camera +y (down) = cross(f, s).
    u = np.cross(f, s)                # down (camera +y)
    R = np.stack([s, u, f], axis=0)   # rows = camera axes in world
    t = -R @ eye
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    return M


def intrinsic_matrix(w, h, fov_deg):
    f = (h / 2.0) / np.tan(np.deg2rad(fov_deg) / 2.0)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    K = o3d.camera.PinholeCameraIntrinsic()
    K.set_intrinsics(w, h, f, f, cx, cy)
    return K
