"""Contact-frame view profiles: a user-picked viewpoint that follows the contact.

A view profile stores the camera pose RELATIVE to the contact point's local
frame ({dir, up} in contact coordinates plus standoff and intrinsics) instead
of an absolute world pose. Re-instantiating the same profile on another
sequence rebuilds the camera around that sequence's own contact point, so one
interactively chosen angle carries over to every contact site while still
framing the deformation. An absolute PinholeCameraParameters JSON remains the
right tool when the viewpoint must NOT follow the contact.
"""

import json
import os

import numpy as np
import open3d as o3d

from .geometry import intrinsic_matrix, look_at_extrinsic

PROFILE_SUFFIX = ".profile.json"


def contact_frame(normal):
    """Right-handed orthonormal frame at a contact: columns [t1 | t2 | n].

    Built with the same Gram-Schmidt recipe as the force mapping (world x
    projected into the tangent plane, world y as fallback), so the frame is
    deterministic and consistent across the pipeline. Maps local -> world.
    """
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    world_x = np.array([1.0, 0.0, 0.0])
    t1 = world_x - (world_x @ n) * n
    if np.linalg.norm(t1) < 1e-6:
        world_y = np.array([0.0, 1.0, 0.0])
        t1 = world_y - (world_y @ n) * n
    t1 = t1 / np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    t2 = t2 / np.linalg.norm(t2)
    F = np.stack([t1, t2, n], axis=1)
    assert np.abs(F.T @ F - np.eye(3)).max() < 1e-9, "contact frame not orthonormal"
    assert abs(np.linalg.det(F) - 1.0) < 1e-9, "contact frame det != +1"
    return F


def camera_eye_and_up(extrinsic):
    """Recover (eye_world, up_world, forward_world) from a world->camera extrinsic.

    Open3D's camera looks down +z with image y down, so world-up of the view
    is MINUS the camera-y row of the rotation.
    """
    E = np.asarray(extrinsic, float)
    R = E[:3, :3]
    t = E[:3, 3]
    eye = -R.T @ t
    up = -R[1, :]
    forward = R[2, :]
    return eye, up, forward


def fov_deg_from_intrinsic(intrinsic):
    """Vertical field of view implied by a PinholeCameraIntrinsic."""
    K = intrinsic.intrinsic_matrix
    fy = float(K[1][1])
    h = intrinsic.height
    return float(np.degrees(2.0 * np.arctan((h / 2.0) / fy)))


def decompose(cam_params, contact_point, contact_normal):
    """Express an absolute camera as a profile relative to the contact frame.

    The look-at target is taken to be the contact point: standoff is the
    eye-to-contact distance and dir is the unit eye offset, both expressed in
    the contact's local frame. The actual view direction the user chose is
    preserved exactly only when they orbited around the contact; that is the
    designed workflow (the picker starts from the contact-centered auto
    camera).
    """
    p = np.asarray(contact_point, float)
    F = contact_frame(contact_normal)
    eye, up_world, _fwd = camera_eye_and_up(cam_params.extrinsic)
    offset = eye - p
    standoff = float(np.linalg.norm(offset))
    if standoff < 1e-9:
        raise ValueError("camera eye coincides with the contact point")
    dir_world = offset / standoff
    return {
        "dir_local": [float(x) for x in (F.T @ dir_world)],
        "up_local": [float(x) for x in (F.T @ up_world)],
        "standoff_mm": standoff,
        "fov_deg": fov_deg_from_intrinsic(cam_params.intrinsic),
        "width": int(cam_params.intrinsic.width),
        "height": int(cam_params.intrinsic.height),
    }


def instantiate(profile, contact_point, contact_normal):
    """Rebuild PinholeCameraParameters from a profile at a (new) contact.

    Returns (cam, eye_world). Falls back to global +z (then +y) for the up
    vector if the profile's up degenerates against the view direction at this
    contact orientation.
    """
    p = np.asarray(contact_point, float)
    F = contact_frame(contact_normal)
    dir_world = F @ np.asarray(profile["dir_local"], float)
    dir_world = dir_world / np.linalg.norm(dir_world)
    eye = p + dir_world * float(profile["standoff_mm"])
    up_world = F @ np.asarray(profile["up_local"], float)

    forward = p - eye
    forward = forward / np.linalg.norm(forward)
    for candidate in (up_world, np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])):
        if np.linalg.norm(np.cross(forward, candidate)) > 1e-6:
            up_world = candidate
            break

    extr = look_at_extrinsic(eye, p, up_world)
    intr = intrinsic_matrix(int(profile["width"]), int(profile["height"]),
                            float(profile["fov_deg"]))
    cam = o3d.camera.PinholeCameraParameters()
    cam.intrinsic = intr
    cam.extrinsic = extr
    return cam, eye


def save_profile(profile, path):
    with open(path, "w") as fh:
        json.dump(profile, fh, indent=2)
    return path


def load_profile(path):
    with open(path, "r") as fh:
        profile = json.load(fh)
    required = {"dir_local", "up_local", "standoff_mm", "fov_deg", "width", "height"}
    missing = required - set(profile)
    if missing:
        raise ValueError(f"profile {path} missing fields: {sorted(missing)}")
    return profile


def resolve_profile_path(name_or_path, cameras_dir):
    """Accept a bare profile name (resolved in cameras_dir) or an explicit path."""
    if os.path.isfile(name_or_path):
        return name_or_path
    candidate = os.path.join(cameras_dir, name_or_path + PROFILE_SUFFIX)
    if os.path.isfile(candidate):
        return candidate
    raise FileNotFoundError(
        f"camera profile not found: neither {name_or_path!r} nor {candidate!r}")


def _self_test():
    """Round-trip and degeneracy checks; raises AssertionError on failure."""
    rng = np.random.default_rng(7)
    for _ in range(20):
        n = rng.normal(size=3)
        n = n / np.linalg.norm(n)
        p = rng.normal(scale=30.0, size=3)
        # A random profile with a non-degenerate up.
        d = rng.normal(size=3)
        d = d / np.linalg.norm(d)
        profile = {
            "dir_local": d.tolist(),
            "up_local": [0.0, 0.0, 1.0],
            "standoff_mm": float(rng.uniform(40.0, 120.0)),
            "fov_deg": 60.0,
            "width": 800,
            "height": 800,
        }
        cam, eye = instantiate(profile, p, n)
        # The camera must look at the contact point from the right distance.
        F = contact_frame(n)
        assert abs(np.linalg.norm(eye - p) - profile["standoff_mm"]) < 1e-9
        back = decompose(cam, p, n)
        assert abs(back["standoff_mm"] - profile["standoff_mm"]) < 1e-6
        assert np.allclose(back["dir_local"], profile["dir_local"], atol=1e-9)
        assert abs(back["fov_deg"] - 60.0) < 1e-6
        # Re-instantiating the decomposed profile reproduces the extrinsic.
        cam2, _eye2 = instantiate(back, p, n)
        assert np.allclose(np.asarray(cam2.extrinsic)[:3, :3],
                           np.asarray(cam.extrinsic)[:3, :3], atol=1e-6)

    # The auto camera expressed as a profile re-instantiates identically.
    from ..config import CameraConfig
    from .auto import build_camera_params

    cfg = CameraConfig()
    p = np.array([10.0, -5.0, 30.0])
    n = np.array([0.1, 0.2, 0.97])
    n = n / np.linalg.norm(n)
    cam, _eye = build_camera_params(p, cfg)
    prof = decompose(cam, p, n)
    assert abs(prof["standoff_mm"] - cfg.standoff_mm) < 1e-6
    cam2, _ = instantiate(prof, p, n)
    assert np.allclose(np.asarray(cam2.extrinsic), np.asarray(cam.extrinsic), atol=1e-6)

    # Degenerate up (parallel to view dir) must fall back, not crash.
    prof_deg = {
        "dir_local": [0.0, 0.0, 1.0],  # straight along the normal
        "up_local": [0.0, 0.0, 1.0],   # parallel to the view direction
        "standoff_mm": 70.0,
        "fov_deg": 60.0,
        "width": 800,
        "height": 800,
    }
    cam3, _ = instantiate(prof_deg, np.zeros(3), np.array([0.0, 0.0, 1.0]))
    E = np.asarray(cam3.extrinsic)
    assert np.isfinite(E).all(), "degenerate-up fallback produced non-finite extrinsic"
    print("camera.profile self-test PASS")
