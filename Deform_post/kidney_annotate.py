"""Kidney pose snapshot + DeformSim annotation generator.

Loads a canonical (lying-flat) PLY, renders verification snapshots, and emits a
DeformSim annotation JSON (z-threshold freeze + farthest-point contact seeds).
"""
import os
import json
import argparse
import numpy as np
import open3d as o3d


def load_mesh(ply_path):
    mesh = o3d.io.read_triangle_mesh(ply_path)
    mesh.compute_vertex_normals()
    mesh.compute_triangle_normals()
    return mesh


def flatness_metric(mesh, angle_deg=30.0):
    """Fraction of faces whose normal aligns with +z (top) and -z (bottom)."""
    cos_t = float(np.cos(np.deg2rad(angle_deg)))
    n = np.asarray(mesh.triangle_normals)
    if n.size == 0:
        return 0.0, 0.0
    nz = n[:, 2]
    top = float(np.mean(nz > cos_t))
    bottom = float(np.mean(nz < -cos_t))
    return top, bottom


def render_views(mesh, out_dir, size=800):
    """Render top / side / isometric snapshots of the (centered) mesh to PNG."""
    os.makedirs(out_dir, exist_ok=True)
    views = {
        "top":  ([0.0, 0.0, 1.0], [0.0, 1.0, 0.0]),
        "side": ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0]),
        "iso":  ([1.0, 1.0, 1.0], [0.0, 0.0, 1.0]),
    }
    for name, (front, up) in views.items():
        vis = o3d.visualization.Visualizer()
        vis.create_window(visible=False, width=size, height=size)
        vis.add_geometry(mesh)
        ctr = vis.get_view_control()
        ctr.set_lookat([0.0, 0.0, 0.0])
        ctr.set_front(front)
        ctr.set_up(up)
        ctr.set_zoom(0.7)
        vis.poll_events()
        vis.update_renderer()
        vis.capture_screen_image(os.path.join(out_dir, f"pose_{name}.png"))
        vis.destroy_window()


def _make_slab():
    """Synthetic thin axis-aligned slab (thin along z) for self-test."""
    mesh = o3d.geometry.TriangleMesh.create_box(width=8.0, height=8.0, depth=0.4)
    mesh.translate(-mesh.get_center())
    mesh.compute_triangle_normals()
    return mesh


def _self_test():
    # Flat slab: only the top/bottom faces align with +/-z; both positive and symmetric.
    mesh = _make_slab()
    top, bottom = flatness_metric(mesh, angle_deg=30.0)
    assert top > 0.0 and bottom > 0.0, f"flat slab faces should align with +/-z: {top},{bottom}"
    assert abs(top - bottom) < 1e-6, f"top/bottom should be symmetric: {top},{bottom}"
    # Tilt 45 deg about x: no face should align with +/-z within 30 deg.
    a = np.deg2rad(45.0)
    R = np.array([[1.0, 0.0, 0.0],
                  [0.0, np.cos(a), -np.sin(a)],
                  [0.0, np.sin(a),  np.cos(a)]])
    tilted = _make_slab()
    tilted.rotate(R, center=(0.0, 0.0, 0.0))
    tilted.compute_triangle_normals()
    tt, tb = flatness_metric(tilted, angle_deg=30.0)
    assert tt < 1e-9 and tb < 1e-9, f"tilted slab should have no +/-z-aligned faces: {tt},{tb}"
    print(f"flatness self-test PASS: flat top={top:.3f} bottom={bottom:.3f}; tilted top={tt:.3f} bottom={tb:.3f}")
