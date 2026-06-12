"""Real sensor force recordings: loading and sensor->model mapping.

The sensor->model rotation R is derived authoritatively and reproducibly from
the mesh + contact seed: it maps a +Fx sensor push onto pressing into the
surface (-n) and lateral sensor components onto tangential shear. R preserves
magnitude, so |F_model| == |F_sensor|; the label remains the raw sensor force.
"""

import numpy as np


def sensor_to_model_rotation(normal):
    """Fixed sensor->model rotation R (columns [press | t1 | t2]).

    press = -n maps sensor +Fx into pressing into the surface; t1/t2 span the
    tangent plane so lateral sensor components become tangential shear. R is
    right-handed and orthonormal; F_model = R @ F_sensor preserves magnitude.
    """
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    press = -n
    world_x = np.array([1.0, 0.0, 0.0])
    t1 = world_x - (world_x @ n) * n
    if np.linalg.norm(t1) < 1e-6:
        world_y = np.array([0.0, 1.0, 0.0])
        t1 = world_y - (world_y @ n) * n
    t1 = t1 / np.linalg.norm(t1)
    t2 = np.cross(press, t1)
    t2 = t2 / np.linalg.norm(t2)
    R = np.stack([press, t1, t2], axis=1)
    # Self-checks: orthonormal, proper rotation, presses along -n.
    assert np.abs(R.T @ R - np.eye(3)).max() < 1e-9, "R not orthonormal"
    assert abs(np.linalg.det(R) - 1.0) < 1e-9, "det(R) != +1"
    assert np.allclose(R @ np.array([1.0, 0.0, 0.0]), -n, atol=1e-9), "R@x != -n"
    return R


def map_forces(F_sensor, R):
    """F_model = (R @ F_sensor.T).T. Magnitude-preserving by construction."""
    F_sensor = np.asarray(F_sensor, float).reshape(-1, 3)
    return (R @ F_sensor.T).T


def sample_id(seed, frame_index):
    """SampleID matching the exe's deformed_s%04d_v%04d filename stem."""
    return f"deformed_s{int(seed):04d}_v{int(frame_index):04d}"


def load_real_forces(real_csv):
    """Load a bare 'Fx,Fy,Fz' Newton CSV (no header, CRLF tolerated) -> (N, 3)."""
    rows = []
    with open(real_csv, "r", newline="") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            parts = s.split(",")
            if len(parts) < 3:
                raise ValueError(f"malformed force row in {real_csv}: {line!r}")
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    if not rows:
        raise ValueError(f"no force rows in {real_csv}")
    return np.asarray(rows, dtype=float)


def subsample_indices(n_total, n_keep):
    """Evenly-spaced indices across [0, n_total) (inclusive endpoints when possible)."""
    if n_keep >= n_total:
        return np.arange(n_total)
    return np.linspace(0, n_total - 1, n_keep).round().astype(int)


def _self_test():
    """Rotation/mapping invariants; raises AssertionError on failure."""
    n = np.array([0.2, -0.3, 0.93])
    n = n / np.linalg.norm(n)
    R = sensor_to_model_rotation(n)
    assert np.abs(R.T @ R - np.eye(3)).max() < 1e-9, "R not orthonormal"
    assert abs(np.linalg.det(R) - 1.0) < 1e-9, "det(R) != +1"
    assert np.allclose(R @ np.array([1.0, 0.0, 0.0]), -n, atol=1e-9), "R@x != -n"

    # Degenerate +z normal must fall back cleanly (t1 not collinear with n).
    Rz = sensor_to_model_rotation(np.array([0.0, 0.0, 1.0]))
    assert np.abs(Rz.T @ Rz - np.eye(3)).max() < 1e-9, "R(+z) not orthonormal"
    assert abs(np.linalg.det(Rz) - 1.0) < 1e-9, "R(+z) det != +1"

    rng = np.random.default_rng(0)
    F = rng.normal(size=(50, 3))
    Fm = map_forces(F, R)
    assert np.allclose(
        np.linalg.norm(Fm, axis=1), np.linalg.norm(F, axis=1), atol=1e-9
    ), "|F_model| != |F_sensor|"

    assert sample_id(521, 7) == "deformed_s0521_v0007"
    assert sample_id(521, 29) == "deformed_s0521_v0029"

    assert subsample_indices(10, 20).tolist() == list(range(10))
    idx = subsample_indices(100, 5)
    assert idx[0] == 0 and idx[-1] == 99 and len(idx) == 5
    print("forces.real self-test PASS")
