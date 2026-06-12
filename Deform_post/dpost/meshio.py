"""Mesh loading and per-vertex contact queries shared across the pipeline."""

import numpy as np
import open3d as o3d


def load_mesh(ply_path):
    mesh = o3d.io.read_triangle_mesh(ply_path)
    mesh.compute_vertex_normals()
    mesh.compute_triangle_normals()
    return mesh


def contact_normal(mesh, seed):
    """Return (world_coords, outward_unit_normal) at the contact seed vertex."""
    mesh.compute_vertex_normals()
    verts = np.asarray(mesh.vertices)
    norms = np.asarray(mesh.vertex_normals)
    if not (0 <= seed < len(verts)):
        raise ValueError(f"contact seed {seed} out of range [0, {len(verts)})")
    p = verts[seed].astype(float)
    n = norms[seed].astype(float)
    nn = float(np.linalg.norm(n))
    if nn < 1e-12:
        raise ValueError(f"degenerate normal at seed {seed}")
    return p, n / nn
